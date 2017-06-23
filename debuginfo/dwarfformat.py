from elftools.elf.elffile import ELFFile, DWARFInfo
from elftools.common.py3compat import BytesIO
from elftools.dwarf.compileunit import CompileUnit
from os.path import sep, normpath
from elftools.dwarf.descriptions import describe_attr_value
from elftools.common.py3compat import bytes2str
from db.operation import *
from collections import defaultdict, namedtuple
from elftoolsext.macro import Macro
from .runner import Task

import sys


class TagMapperError(Exception):
    pass


class DwarfInfoBeforeParseError(Exception):
    pass


class DwarfInfoParseError(Exception):
    pass


class DwarfInfoParseAfterError(Exception):
    pass


class DwarfInfoParseTask(Task):
    _dwarf_info_bytes = None
    _dwarf_line_bytes = None

    @staticmethod
    def _get_die_attributes_dict(die, global_offset):
        res = defaultdict()
        for attr in iter(die.attributes.values()):
            name = attr.name
            if isinstance(name, int):
                continue
            else:
                try:
                    description = str(describe_attr_value(attr, die, global_offset)).strip()
                except KeyError:
                    pass
                else:
                    if len(description) == 0:
                        continue
                    else:
                        res[name] = description
        return res

    @classmethod
    def set_dwarf_info_buffer(cls, dwarf_info : DWARFInfo):
        dwarf_info.debug_info_sec.stream.seek(0, os.SEEK_SET)
        dwarf_info.debug_line_sec.stream.seek(0, os.SEEK_SET)
        cls._dwarf_info_bytes = dwarf_info.debug_info_sec.stream.getvalue()
        cls._dwarf_line_bytes = dwarf_info.debug_line_sec.stream.getvalue()

    @classmethod
    def clear_dwarf_buffer(cls):
        cls._dwarf_info_bytes = None
        cls._dwarf_line_bytes = None

    __slots__ = ["_cu", "_op", "_dwarf_info", "_file_id_map", "_cu_db_item"]

    def __init__(self, cu: CompileUnit, file_id_map: dict, index: int):
        super(DwarfInfoParseTask, self).__init__()
        self._cu = cu
        self._op = Operation()
        self._dwarf_info = None
        self.index = index
        self._file_id_map = file_id_map
        self._cu_db_item = None

    def _before_run(self):
        super(DwarfInfoParseTask, self)._before_run()
        if len(DwarfInfoParseTask._dwarf_info_bytes) == 0:
            raise DwarfInfoBeforeParseError("Bytes of info section is empty")
        if len(DwarfInfoParseTask._dwarf_line_bytes) == 0:
            raise DwarfInfoBeforeParseError("Bytes of line section is empty")
        if self._file_id_map is None:
            raise DwarfInfoBeforeParseError("No file map found")

        self._cu.dwarfinfo.debug_info_sec = \
            self._cu.dwarfinfo.debug_info_sec._replace(stream=BytesIO(DwarfInfoParseTask._dwarf_info_bytes))
        self._cu.dwarfinfo.debug_line_sec = \
            self._cu.dwarfinfo.debug_line_sec._replace(stream=BytesIO(DwarfInfoParseTask._dwarf_line_bytes))

        global_offset = self._cu.dwarfinfo.debug_info_sec.global_offset
        if global_offset == 0:
            raise DwarfInfoBeforeParseError("Global offset is zero")

        self._dwarf_info = self._cu.dwarfinfo
        if self._dwarf_info is None:
            raise DwarfInfoBeforeParseError("Dwarf info object should not be None")

        top_die = self._cu.get_top_DIE()
        assert not top_die.is_null() and top_die.tag == 'DW_TAG_compile_unit'

        attributes = self._get_die_attributes_dict(top_die, global_offset)

        pair = attributes['DW_AT_name'].strip().split('): ')
        cu_file_name = (pair[0] if len(pair) == 1 else pair[1]) if len(pair) != 0 else None

        pair = attributes['DW_AT_comp_dir'].strip().split('): ')
        cu_file_directory = (pair[0] if len(pair) == 1 else pair[1]) if len(pair) != 0 else None

        file_full_path = cu_file_directory.strip() + sep + cu_file_name.strip()
        if not os.path.exists(file_full_path):
            sys.stderr.write("Warning: file {} doesn't exist!\n".format(file_full_path))

        self._cu_db_item = self._op.add_compilation_unit(cu_file_directory, cu_file_name, self.index)

    def _run(self):
        file_id_map = self._file_id_map
        tag_stack = [(self._cu.get_top_DIE(), Tag())]
        tag_to_add = []
        tag_map = dict()

        def parse_tags(die):
            tag_mapper_key = '<0x%x>' % die.offset
            try:
                tag = tag_map[tag_mapper_key]
            except KeyError:
                tag = Tag()
                tag_map[tag_mapper_key] = tag

            tag_type_map = dict(
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
            attributes = self._get_die_attributes_dict(die, self._cu.dwarfinfo.debug_line_sec.global_offset)
            tag_type = die.tag
            try:
                tag.type = tag_type_map[tag_type]
                pair = attributes['DW_AT_name'].strip().split('):')

                tag.name = pair[0] if len(pair) == 1 else pair[1]
                tag.name = tag.name.strip()

                if tag.type != TagType.EnumerationMember:
                    tag.line_no = int(attributes['DW_AT_decl_line']) if tag.type != TagType.BaseType else None
                    tag.file_id = file_id_map[int(attributes['DW_AT_decl_file'])] \
                        if tag.type != TagType.BaseType else file_id_map[1]

                if tag.type in [TagType.Typedef] and 'DW_AT_type' in attributes.keys():
                    to_type = attributes['DW_AT_type']
                    if to_type not in tag_map.keys():
                        tag_map[to_type] = Tag()
                    tag.tmp_assoc_to_tag = tag_map[to_type]
            except KeyError:
                tag.name = None
            except TagMapperError:
                tag.name = None
            else:
                i = len(tag_stack) - 1
                while i > 0:
                    (parent_die, parent_tag) = tag_stack[i]
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
                        tmp_tag = tmp_tag.parent_tag
                    if tmp_tag is not None:
                        tag.file = tmp_tag.file

                tag.compile_unit = self._cu_db_item
                tag_to_add.append(tag)
            finally:
                # 处理栈
                if die.has_children:
                    tag_stack.append((die, tag))
                elif die.is_null():
                    tag_stack.pop()
        die_iter = self._cu.iter_DIEs()
        top = True
        for cur_die in die_iter:
            if top:
                top = False
                continue
            else:
                parse_tags(cur_die)

        # fold the tags
        for tag in tag_to_add:
            tmp_tag = tag.tmp_assoc_to_tag
            while tmp_tag is not None:
                if tmp_tag.name is not None:
                    break
                else:
                    tmp_tag = tmp_tag.assoc_to_tag
            tag.assoc_to_tag = tmp_tag
            self._op.add_tag(tag)

    def _after_run(self):
        try:
            self._op.commit()
        except:
            raise DwarfInfoParseAfterError("Error when commit {}")
        self._op.close()
        super(DwarfInfoParseTask, self)._after_run()


class DwarfMacroBeforeParseError(Exception):
    pass


class DwarfMacroParseError(Exception):
    pass


class DwarfMacroParseAfterError(Exception):
    pass


class DwarfMacroParseTask(Task):
    def __init__(self, macro: Macro, cu_index_list: list, file_id_map_list: list):
        self._macro = macro
        self._op = Operation()
        self._cu_id_list = cu_index_list
        self._file_id_map_list = file_id_map_list

    def _before_run(self):
        super(DwarfMacroParseTask, self)._before_run()
        pass

    def _run(self):
        macro_list = self._macro.get_macro_list()
        cu_list_index = 0
        for macro_list_item in macro_list:
            assert cu_list_index < len(self._cu_id_list)
            cu_id = self._cu_id_list[cu_list_index]
            file_id_map = self._file_id_map_list[cu_list_index]
            for item in macro_list_item:
                if item.file_idx <= 0:
                    continue
                tag = Tag()
                tag.file_id = file_id_map[item.file_idx]
                tag.compile_unit_id = cu_id
                tag.line_no = item.line_num
                tag.name = item.macro_name
                tag.type = TagType.Macro
                self._op.add_tag(tag)
            cu_list_index += 1
            self._op.commit()

    def _after_run(self):
        self._op.close()
        super(DwarfMacroParseTask, self)._after_run()


class DwarfParseTaskGenerateError(Exception):
    pass


FileMapTuple = namedtuple('FileMapTuple', 'dir_rel_path file_rel_path')


class DwarfParseTaskGenerator:
    def __init__(self, file_path):
        self._file_path = file_path
        self._elf_file = ELFFile(open(file_path, 'rb'))

    @staticmethod
    def _get_file_id_map(cu: CompileUnit, op: Operation):
        line_program = cu.dwarfinfo.line_program_for_CU(cu)
        index = 1
        file_map = dict()
        for file_entry in line_program['file_entry']:
            file_name = bytes2str(file_entry.name)
            dir_index = file_entry.dir_index
            if dir_index > 0:
                dir_path = line_program['include_directory'][dir_index - 1]
            else:
                dir_path = b'.'
            file_map[index] = op.add_file(file_name, bytes2str(dir_path))
            index += 1
        file_id_map = dict()
        for key in file_map:
            file_id_map[key] = file_map[key].id
        return file_id_map

    def has_debug_info(self):
        return self._elf_file.has_dwarf_info()

    def iter_tasks(self):
        if not self.has_debug_info():
            raise DwarfParseTaskGenerateError("Cannot find debug info")

        dwarf_info = self._elf_file.get_dwarf_info()
        DwarfInfoParseTask.set_dwarf_info_buffer(dwarf_info)

        macro_cu_list = list()
        macro_file_id_map_list = list()
        cu_id = 0

        op = Operation()
        cus = list(dwarf_info.iter_CUs())
        file_id_maps = [DwarfParseTaskGenerator._get_file_id_map(cu, op) for cu in cus]
        op.commit()
        op.close()
        for cu, file_id_map in zip(cus, file_id_maps):
            yield DwarfInfoParseTask(cu, file_id_map, cu_id)
            if 'DW_AT_macro_info' in cu.get_top_DIE().attributes:
                macro_cu_list.append(cu_id)
                macro_file_id_map_list.append(file_id_map)
            cu_id += 1

        yield DwarfMacroParseTask(
            Macro.get_macro_info_from_elffile(self._elf_file), macro_cu_list, macro_file_id_map_list
        )
