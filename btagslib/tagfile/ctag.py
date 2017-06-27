from btagslib.db.model import *
from btagslib.db.operation import Operation
from btagslib.terminal.statusbar import MultiProgressBar, get_status_bar_decorator
import os


class LackInfoException(Exception):
    pass


class CtagFormat():
    def __init__(self, db_path, status_bar: MultiProgressBar):
        """
        :type op: Operation
        """
        Operation.prepare(db_path)
        self._op = Operation()
        self._session = self._op.session()
        self._curr_tag_line = None
        self._status_bar = status_bar
        self._status_bar_index = status_bar.get_an_index()
        self._status_bar_decorator = get_status_bar_decorator(status_bar, self._status_bar_index)
        self._work_dir = os.curdir
        self._comp_dir = None
        self.type_kind_mapper = {
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
        self.type_field_mapper = {
            TagType.Class: 'class',
            TagType.Enumeration: 'enum',
            TagType.Union: 'union',
            TagType.Structure: 'struct',
            TagType.Function: 'function',
        }

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
        fields = dict()
        assoc_type = None
        if tag.type in [TagType.Member, TagType.FormalParameter, TagType.EnumerationMember]:
            if tag.assoc_to_tag is not None and int(tag.assoc_to_tag.type) in self.type_field_mapper:
                assoc_type = self.type_field_mapper[int(tag.assoc_to_tag.type)]
        if assoc_type is not None:
            fields[assoc_type] = tag.assoc_to_tag.name

        if tag.type == TagType.Function:
            fields['arity'] = len(tag.assoc_from_tags)

        if tag.type in self.type_kind_mapper:
            fields['kind'] = self.type_kind_mapper[tag.type]

        fields['file'] = ''

        for k in fields:
            if k == 'kind':
                self._curr_tag_line += '\t%s' % (fields[k])
            else:
                self._curr_tag_line += '\t%s:%s' % (k, fields[k])

    def get_tag_file(self, stream, work_dir=os.curdir, comp_dir=None):
        self._work_dir = work_dir
        self._comp_dir = comp_dir
        tag_len = self._session.query(Tag).count()
        all_tags = self._session.query(Tag).join(File).join(CompileUnit).order_by(Tag.name, File.file_name, Tag.line_no).all()
        prev_tag = None

        @self._status_bar_decorator(0, 1, tag_len, "Generating tags {0}/{1}")
        def gen_tag(cur_tag):
            cur_tag.type = int(cur_tag.type)
            self._curr_tag_line = ""
            try:
                self._get_vi_field(cur_tag)
                self._get_extra_fields(cur_tag)
            except LackInfoException:
                pass
            else:
                stream.write('%s\n' % self._curr_tag_line)

        for tag in all_tags:
            if prev_tag is not None and \
                            prev_tag.name == tag.name and \
                            prev_tag.file.file_name == tag.file.file_name and \
                            prev_tag.file.file_directory == tag.file.file_directory and \
                            prev_tag.line_no == tag.line_no:
                continue
            else:
                gen_tag(tag)
                prev_tag = tag
