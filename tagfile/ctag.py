from db.model import *
from db.operation import Operation
import os


class LackInfoException(Exception):
    pass


class CtagFormat():
    def __init__(self, db_path):
        """
        :type op: Operation
        """
        Operation.prepare(db_path)
        self._op = Operation()
        self._session = self._op.session()
        self._curr_tag_line = None
        self._work_dir = os.curdir
        self._comp_dir = None

    def _get_vi_field(self, tag):
        if tag.file is None:
            raise LackInfoException
        #根据编译目录计算实际的绝对路径
        if self._comp_dir is not None:
            file_path = os.path.abspath(
                os.path.join(self._comp_dir, tag.file.file_dir_rel_to_comp_dir, tag.file.file_name)
            )
        else:
            file_path = os.path.join(tag.file.file_directory, tag.file.file_name)
        rel_path = os.path.relpath(file_path, self._work_dir)

        tmp_tag = tag
        while tmp_tag.line_no is None and tmp_tag.parent_tag is not None:
            tmp_tag = tmp_tag.parent_tag
        line_no = tmp_tag.line_no

        if line_no is None:
            raise LackInfoException
        else:
            if tag.type == TagType.EnumerationMember:
                self._curr_tag_line = "%s\t%s\t%d;/%s/;\"" % (tag.name, rel_path, line_no, tag.name)
            else:
                self._curr_tag_line = "%s\t%s\t/\\%%%dl%s/;\"" % (tag.name, rel_path, line_no, tag.name)

    def _get_extra_fields(self, tag):
        type_field_mapper = {
            TagType.Class: 'class',
            TagType.Enumeration: 'enum',
            TagType.Union: 'union',
            TagType.Structure: 'struct',
            TagType.Function: 'function',
        }
        fields = dict()
        assoc_type = None
        if tag.type in [TagType.Member, TagType.FormalParameter, TagType.EnumerationMember]:
            if tag.assoc_to_tag is not None and int(tag.assoc_to_tag.type) in type_field_mapper:
                assoc_type = type_field_mapper[int(tag.assoc_to_tag.type)]
        if assoc_type is not None:
            fields[assoc_type] = tag.assoc_to_tag.name

        if tag.type == TagType.Function:
            fields['arity'] = len(tag.assoc_from_tags)

        type_kind_mapper = {
            TagType.Class: 'c',
            TagType.Macro: 'd',
            TagType.EnumerationMember: 'e',
            TagType.Enumeration: 'g',
            TagType.Member: 'm',
            TagType.Function: 'p',
            TagType.Structure: 's',
            TagType.Typedef: 't',
            TagType.Union: 'u',
            TagType.Variable: 'v',
        }
        if tag.type in type_kind_mapper:
            fields['kind'] = type_kind_mapper[tag.type]

        fields['file'] = ''

        for k in fields:
            if k == 'kind':
                self._curr_tag_line += '\t%s' % (fields[k])
            else:
                self._curr_tag_line += '\t%s:%s' % (k, fields[k])


    def get_tag_file(self, stream, work_dir=os.curdir, comp_dir=None):
        self._work_dir = work_dir
        self._comp_dir = comp_dir
        prev_tag = None
        for tag in self._session.query(Tag).join(File).join(CompileUnit).order_by(Tag.name, File.file_name, Tag.line_no).all():
            tag.type = int(tag.type)
            if prev_tag is not None and \
                            prev_tag.name == tag.name and \
                            prev_tag.file.file_name == tag.file.file_name and \
                            prev_tag.file.file_directory == tag.file.file_directory and \
                    prev_tag.line_no == tag.line_no:
                continue
            else:
                self._curr_tag_line = ""
                try:
                    self._get_vi_field(tag)
                    self._get_extra_fields(tag)
                except LackInfoException:
                    pass
                else:
                    stream.write('%s\n' % self._curr_tag_line)
                finally:
                    prev_tag = tag
