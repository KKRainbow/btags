from elftools.elf.elffile import ELFFile
from os.path import sep, normpath
from elftools.dwarf.descriptions import describe_attr_value
from elftools.common.py3compat import bytes2str
from db.operation import *
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor as PoolExecutor
from concurrent.futures import as_completed
from elftoolsext.macro import Macro
from .runner import Task

import sys


class TagMapperError(Exception):
    pass


class DwarfInfoCache(object):
    def __init__(self, file_path):
        """
        :type elffile ELFFile
        :param elffile:
        """
        self._elffile = ELFFile(open(file_path, 'rb'))
        self._file_path = file_path
        self._dwarf_info = self._get_new_dwarf_info()
        self._cu_list = None
        self._macro_list = None
        self.get_cu_list()
        self._get_macro_list()
        self._cu_macinfo_mapper = None
        self.get_macro_info_of_cu_idx(0)

    def _get_new_dwarf_info(self):
        return self._elffile.get_dwarf_info()

    def get_cu_list(self):
        if self._cu_list is None:
            self._cu_list = list(self._dwarf_info.iter_CUs())
        return self._cu_list

    def get_cu_with_new_stream(self, idx):
        self._elffile = ELFFile(open(self._file_path, 'rb'))
        cu = self.get_cu_list()[idx]
        cu.dwarfinfo = self._get_new_dwarf_info()
        return cu

    def get_elf_file(self):
        return self._elffile

    def _get_macro_list(self):
        if self._macro_list is None:
            macro = Macro.get_macro_info_from_elffile(self._elffile)
            if macro is not None:
                self._macro_list = macro.get_macro_list()
        return self._macro_list

    def get_macro_info_of_cu_idx(self, cu_idx):
        if self._cu_macinfo_mapper is None:
            self._cu_macinfo_mapper = dict()
            l = self._get_macro_list()
            icu = 0
            imac = 0
            for cu in self.get_cu_list():
                if 'DW_AT_macro_info' in cu.get_top_DIE().attributes:
                    self._cu_macinfo_mapper[icu] = l[imac]
                    imac += 1
                else:
                    self._cu_macinfo_mapper[icu] = None
                icu += 1
        if cu_idx < 0 or cu_idx >= len(self._cu_macinfo_mapper):
            return None
        else:
            return self._cu_macinfo_mapper[cu_idx]



class DwarfFormatParser:
    def __init__(self, cache, cu_numbers, op):
        self.cache = cache
        self._op = op
        self._cu_number_list = cu_numbers
        self._cu_number = 0
        self._elffile = cache.get_elf_file()
        self._dwarfinfo = cache._dwarf_info
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

        macinfo = self.cache.get_macro_info_of_cu_idx(self._cu_number)
        if len(abs_path) == 0:
            raise Exception('Compile Unit has incomplete information')
        else:
            self._current_cu = self._op.add_compilation_unit(file_directory, file_name)
            self._tag_stack = [(compile_unit_die, Tag())]
            self._tag_to_add = []
            for other_die in dies:
                self._parse_tags(other_die)
            if macinfo is not None:
                self._parse_macro_info(macinfo)

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
            file = self._op.add_file(file_name, bytes2str(dir))
            self._file_map[index] = file
            index += 1

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
            DW_TAG_union_type=TagType.Union,
            DW_TAG_subprogram=TagType.Function,
            DW_TAG_class_type=TagType.Class,
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
            self._op.add_tag(tag)

    def _parse_macro_info(self, macinfo):
        for item in macinfo:
            if item.file_idx <= 0:
                continue
            tag = Tag()
            tag.file = self._file_map[item.file_idx]
            tag.compile_unit = self._current_cu
            tag.line_no = item.line_num
            tag.name = item.macro_name
            tag.type = TagType.Macro
            self._tag_to_add.append(tag)

    def parse(self):
        self._macro_section_counter = 0
        for cu_num in self._cu_number_list:
            cu = self.cache.get_cu_with_new_stream(cu_num)
            self._cu_number = cu_num
            self._tag_mapper = dict()
            self._parse_compilation_unit(cu)
            self._fold_assoc_tag()


class DwarfFormat:
    def __init__(self, file_path, db_path):
        self._elffile = ELFFile(open(file_path, 'rb'))
        self._file_path = file_path
        self._dwarfinfo = None
        self.db_path = db_path
        self.cache = DwarfInfoCache(file_path)
        self.prepare()
        self._op_list = list()

    def has_debug_info(self):
        return self._elffile.has_dwarf_info()

    def prepare(self):
        if self._dwarfinfo is None:
            self._dwarfinfo = self._elffile.get_dwarf_info()

    def _parser_helper(self, num):
        op = Operation()
        self._op_list.append(op)
        parser = DwarfFormatParser(self.cache, num, op)
        return parser.parse()

    def parse(self, concurrency_level=2):
        Operation.prepare(self.db_path)
        cus = list(self.cache.get_cu_list())
        self.cache.get_cu_list()
        i = len(cus)
        with PoolExecutor(max_workers=concurrency_level) as executor:
            mapper = {executor.submit(self._parser_helper, [n]): n for n in range(len(cus))}
            for f in as_completed(mapper):
                try:
                    f.result()
                except Exception as e:
                    raise
                else:
                    sys.stdout.write('\r                                                            \r')
                    sys.stdout.write('%d unit processed, %d remained, progress:%d%%' %
                                     (mapper[f], i, 100 - (i * 100 / len(cus))))
                    sys.stdout.flush()
                finally:
                    i -= 1
            print('')
        i = len(self._op_list)
        sys.stdout.write('Committing to database!\n')
        for op in self._op_list:
            sys.stdout.write('\r                                                            \r')
            sys.stdout.write('%d unit committed, %d remained, progress: %d%% ' %
                             (len(self._op_list) - i, i, 100 - (i * 100 / len(self._op_list))))
            i -= 1
            sys.stdout.flush()
            op.commit()
        print('')


class DwarfInfoParseError(Exception):
    pass


class DwarfInfoParseTask(Task):
    def __init__(self, cu,  op, file_path, comp_path = None):
        super(DwarfInfoParseTask, self).__init__()
        self.cu = cu
        self.comp_path = comp_path
        self.op = op
        self.file_path = file_path
        self.file_mapper = None
        self.elf_file = None

    def _before_run(self):
        if not os.path.exists(self.file_path):
            raise DwarfInfoParseError("Binary file not found")

