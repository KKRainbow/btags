from elftools.elf.elffile import ELFFile
from elftools.dwarf.dwarfinfo import DWARFInfo
from os.path import sep, normpath
from elftools.dwarf.descriptions import describe_attr_value
from elftools.common.py3compat import bytes2str
from elftools.dwarf.die import DIE
from db.model import *
from db.operation import *
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor as PoolExecutor
from concurrent.futures import as_completed
from multiprocessing.dummy import Pool


class TagMapperError(Exception):
    pass

class DwarfFormatParser:
    def __init__(self, file_path, cu_number, op):
        self._op = op
        self._cu_number = cu_number
        self._elffile = ELFFile(open(file_path, 'rb'))
        self._dwarfinfo = self._elffile.get_dwarf_info()
        self._section_offset = self._dwarfinfo.debug_info_sec.global_offset
        self._file_map = None
        self._current_cu = None
        self._tag_stack = None
        self._tag_mapper = None
        self._tag_to_add = None

    def _get_die_attributes_dict(self, die):
        res = defaultdict()
        for attr in iter(die.attributes.values()):
            name = attr.name
            if isinstance(name, int):
                continue
            else:
                try:
                    description = str(describe_attr_value(attr, die, self._section_offset)).strip()
                except Exception:
                    pass
                else:
                    if (len(description) == 0):
                        continue
                    else:
                        res[name] = description
        return res

    def _parse_compilation_unit(self, cu):
        die_iter = cu.iter_DIEs()
        dies = list(die_iter)

        compile_unit_die = dies.pop(0)
        assert not compile_unit_die.is_null() and self._get_die_tag(compile_unit_die) == 'DW_TAG_compile_unit'

        attrs = self._get_die_attributes_dict(compile_unit_die)

        pair = attrs['DW_AT_name'].strip().split('): ')
        file_name = (pair[0] if len(pair) == 1 else pair[1]) if len(pair) != 0 else None

        pair = attrs['DW_AT_comp_dir'].strip().split('): ')
        file_directory = (pair[0] if len(pair) == 1 else pair[1]) if len(pair) != 0 else None

        self._get_file_mapper(cu, file_directory)

        abs_path = file_directory.strip() + sep + file_name.strip()
        if len(abs_path) == 0:
            raise Exception('Compile Unit has incomplete information')
        else:
            self._current_cu = self._op.add_compilation_unit(abs_path)
            self._tag_stack = [(compile_unit_die, Tag())]
            self._tag_to_add = []
            for other_die in dies:
                self._parse_tags(other_die)

    def _get_file_mapper(self, cu, comp_dir):
        lineprogram = self._dwarfinfo.line_program_for_CU(cu)
        index = 1
        self._file_map = dict()
        for file_entry in lineprogram['file_entry']:
            file_name = bytes2str(file_entry.name)
            dir_index = file_entry.dir_index
            if dir_index > 0:
                dir = lineprogram['include_directory'][dir_index - 1]
            else:
                dir = b'.'
            file_name = '%s/%s/%s' % (comp_dir, bytes2str(dir), file_name)
            file_name = normpath(file_name)
            file = self._op.add_file(file_name)
            self._file_map[index] = file
            index += 1
        self._op.commit()

    def _parse_tags(self, die):
        tag_mapper_key = '<0x%x>' % die.offset
        try:
            tag = self._tag_mapper[tag_mapper_key]
        except KeyError:
            tag = Tag()
            self._tag_mapper[tag_mapper_key] = tag

        tag_type_mapper = dict(
            DW_TAG_variable=TagType.Variable,
            DW_TAG_base_type=TagType.BaseType,
            DW_TAG_typedef=TagType.Typedef,
            DW_TAG_member=TagType.Member,
            DW_TAG_structure_type=TagType.Structure,
            DW_TAG_union=TagType.Union,
            DW_TAG_subprogram=TagType.Function,
            DW_TAG_class=TagType.Class,
            DW_TAG_enumeration_type=TagType.Enumeration,
            DW_TAG_enumerator=TagType.EnumerationMember,
            DW_TAG_formal_parameter=TagType.FormalParameter
        )
        attrs = self._get_die_attributes_dict(die)
        tag_type = self._get_die_tag(die)
        try:
            tag.type = tag_type_mapper[tag_type]
            pair = attrs['DW_AT_name'].strip().split('):')

            tag.name = pair[0] if len(pair) == 1 else pair[1]
            tag.name = tag.name.strip()

            if tag.type != TagType.EnumerationMember:
                tag.line_no = int(attrs['DW_AT_decl_line']) if tag.type != TagType.BaseType else None
                tag.file = self._file_map[int(attrs['DW_AT_decl_file'])] \
                    if tag.type != TagType.BaseType else self._file_map[1]

            if tag.type in [TagType.Typedef] and 'DW_AT_type' in attrs.keys():
                to_type = attrs['DW_AT_type']
                if to_type not in self._tag_mapper.keys():
                    self._tag_mapper[to_type] = Tag()
                tag.tmp_assoc_to_tag = self._tag_mapper[to_type]
        except KeyError:
            tag.name = None
        except TagMapperError:
            tag.name = None
        else:
            i = len(self._tag_stack) - 1
            while i > 0:
                (parent_die, parent_tag) = self._tag_stack[i]
                if parent_tag.name is not None:
                    tag.parent_tag = parent_tag
                i -= 1
            if tag.name is None:
                raise Exception
            if tag.type in [TagType.EnumerationMember, TagType.FormalParameter, TagType.Member] \
                    and tag.parent_tag is not None \
                    and tag.parent_tag.type in \
                            [TagType.Enumeration, TagType.Function, TagType.Structure, TagType.Class]:
                tag.tmp_assoc_to_tag = tag.parent_tag

            if tag.type == TagType.EnumerationMember:
                """
                find a parent with file field
                """
                tmp_tag = tag.tmp_assoc_to_tag
                while tmp_tag is not None and tmp_tag.file is None:
                    tmp_tag = tag.parent_tag
                if tmp_tag is not None:
                    tag.file = tmp_tag.file

            tag.compile_unit = self._current_cu
            self._tag_to_add.append(tag)
        finally:
            # 处理栈
            if die.has_children:
                self._tag_stack.append((die, tag))
            elif die.is_null():
                self._tag_stack.pop()

    @staticmethod
    def _get_die_tag(die):
        return die.tag

    def _fold_assoc_tag(self):
        for tag in self._tag_to_add:
            tmp_tag = tag.tmp_assoc_to_tag
            while tmp_tag is not None:
                if tmp_tag.name is not None:
                    break
                else:
                    tmp_tag = tmp_tag.assoc_to_tag
            tag.assoc_to_tag = tmp_tag

    def parse(self):
        cus = list(self._dwarfinfo.iter_CUs())
        self._tag_mapper = dict()
        self._parse_compilation_unit(cus[self._cu_number])
        self._fold_assoc_tag()
        self._op.commit()


class DwarfFormat:
    def __init__(self, file_path, db_path):
        self._elffile = ELFFile(open(file_path, 'rb'))
        self._file_path = file_path
        self._dwarfinfo = None
        self.db_path = db_path
        self.prepare()

    def has_debug_info(self):
        return self._elffile.has_dwarf_info()

    def prepare(self):
        if self._dwarfinfo is None:
            self._dwarfinfo = self._elffile.get_dwarf_info()

    def _parser_helper(self, num):
        parser = DwarfFormatParser(self._file_path, num, Operation())
        return parser.parse()

    def parse(self, concurrency_level=2):
        Operation.prepare(self.db_path)
        cus = list(self._dwarfinfo.iter_CUs())
        i = len(cus)
        with PoolExecutor(max_workers=concurrency_level) as executor:
            mapper = {executor.submit(self._parser_helper, n): n for n in range(len(cus))}
            for f in as_completed(mapper):
                try:
                    f.result()
                except Exception as e:
                    raise
                else:
                    print('%d finished, %d remained' % (mapper[f], i))
                finally:
                    i -= 1
