from elftools.construct.lib.container import Container
from elftools.dwarf.structs import DWARFStructs, Enum, Struct
from elftools.dwarf.dwarfinfo import DwarfConfig
from elftools.construct.macros import CString
from elftools.common.utils import struct_parse
from elftools.elf.elffile import ELFFile
from elftools.common.py3compat import *
from collections import namedtuple
from io import BytesIO
import os


TypeCodeMap = dict(
    DW_MACINFO_define=0x01,
    DW_MACINFO_undef=0x02,
    DW_MACINFO_start_file=0x03,
    DW_MACINFO_end_file=0x04,
    DW_MACINFO_vendor_ext=0xff,
    NULL=0x00
)

MacroInfoTuple = namedtuple('MacroInfoTuple',
                            'macro_name macro_full_name macro_content line_num file_idx')


class Macro(object):
    def __init__(self, stream, struct):
        """
        :type struct DWARFStructs
        :type stream BytesIO
        """
        self.stream = stream
        self.struct = struct
        self._macro_list = None

    @staticmethod
    def get_macro_info_from_elffile(elffile):
        """
        :type elffile ELFFile
        """
        section_name = '.debug_macinfo'
        compressed = bool(elffile.get_section_by_name('.zdebug_info'))
        if compressed:
            section_name = '.z' + section_name[1:]
        section = elffile.get_section_by_name(section_name)

        if section is None:
            return None
        else:
            dwarf_section = elffile._read_dwarf_section(
                section,
                True
            )
            if compressed:
                dwarf_section = elffile._decompress_dwarf_section(dwarf_section)

        config = DwarfConfig(
            little_endian=elffile.little_endian,
            default_address_size=elffile.elfclass // 8,
            machine_arch=elffile.get_machine_arch())

        structs = DWARFStructs(
            little_endian=config.little_endian,
            dwarf_format=32,
            address_size=config.default_address_size)
        return Macro(dwarf_section.stream, structs)

    def get_macro_list(self):
        if self._macro_list is not None:
            return self._macro_list

        result = list()
        curr_file_stack = [-1]
        curr_cu_macro_info = list()
        i = 1
        for entry in self.iter_macro_info():
            if entry['type'] == 'NULL':
                result.append(curr_cu_macro_info)
                curr_file_stack = [-1]
                curr_cu_macro_info = list()
                continue
            elif entry['type'] == 'DW_MACINFO_start_file':
                curr_file_stack.append(entry.file_idx)
            elif entry['type'] == 'DW_MACINFO_end_file':
                curr_file_stack.pop()
            elif entry['type'] == 'DW_MACINFO_define':
                str = bytes2str(entry.string)
                macro_part = str.split(' ')
                macro_part.append('')
                macro_name_part = macro_part[0].split('(')
                macro_name_part.append('')
                curr_cu_macro_info.append(
                    MacroInfoTuple(
                        macro_name=macro_name_part[0],
                        macro_full_name=macro_part[0],
                        macro_content=macro_part[1],
                        line_num=entry.line_num,
                        file_idx=curr_file_stack[-1]
                    )
                )
            else:
                continue
        self._macro_list = result
        return result

    def iter_macro_info(self):
        self.stream.seek(0, os.SEEK_END)
        endpos = self.stream.tell()

        self.stream.seek(0, os.SEEK_SET)
        while self.stream.tell() < endpos:
            entry = self._parse_macro_info()
            yield entry

    def _parse_macro_info(self):
        e = Container()
        type_name = struct_parse(Enum(self.struct.Dwarf_uint8(''), **TypeCodeMap), self.stream)
        if type_name == 'DW_MACINFO_define':
            entry = Struct(
                'entry',
                self.struct.Dwarf_uleb128('line_num'),
                CString('string')
            )
        elif type_name == 'DW_MACINFO_undef':
            entry = Struct(
                'entry',
                self.struct.Dwarf_uleb128('line_num'),
                CString('string')
            )
        elif type_name == 'DW_MACINFO_start_file':
            entry = Struct(
                'entry',
                self.struct.Dwarf_uleb128('line_num'),
                self.struct.Dwarf_uleb128('file_idx'),
            )
        elif type_name == 'DW_MACINFO_vendor_ext':
            entry = Struct(
                'entry',
                self.struct.Dwarf_uleb128('constant'),
                self.struct.Dwarf_uleb128('string'),
            )
        elif type_name == 'DW_MACINFO_end_file' or type_name == 'NULL':
            entry = None
            pass
        else:
            raise Exception('Unknown type')

        if entry is not None:
            e = struct_parse(entry, self.stream)
        e['type'] = type_name
        return e
