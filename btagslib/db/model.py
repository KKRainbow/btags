from sqlalchemy import *
from sqlalchemy.orm import *
from sqlalchemy.ext.declarative import declared_attr, declarative_base


class Model(object):
    @declared_attr
    def __tablename__(self):
        return self.__name__


Base = declarative_base(cls=Model)


class File(Base):
    id = Column(Integer, Sequence('fild_id_seq'), primary_key=True)
    file_name = Column(Text, nullable=False)
    file_directory = Column(Text, nullable=False)
    file_dir_rel_to_comp_dir = Column(Text, nullable=False)


class CompileUnit(Base):
    id = Column(Integer, Sequence('compile_unit_seq'), primary_key=True)
    comp_dir = Column(String, nullable=False)
    comp_file = Column(String, nullable=False)
    object_name = Column(Text, nullable=False)


class CompileUnitFile(Base):
    id = Column(Integer, Sequence('compile_unit_file_seq'), primary_key=True)
    compile_unit_id = Column(Integer, ForeignKey('CompileUnit.id'), nullable=False)
    file_id = Column(Integer, ForeignKey('File.id'), nullable=False)


class TagType:
    Variable = 1
    Function = 2
    EnumerationMember = 3
    Macro = 4
    Structure = 5
    Class = 6
    Union = 7
    Typedef = 8
    Type = 9
    Enumeration = 10
    Member = 11
    BaseType = 12
    FormalParameter = 13


class Tag(Base):
    id = Column(Integer, Sequence('fild_id_seq'), primary_key=True)
    name = Column(String, nullable=False)
    file_id = Column(Integer, ForeignKey('File.id'), nullable=True)
    compile_unit_id = Column(Integer, ForeignKey('CompileUnit.id'), nullable=True)
    line_no = Column(Integer, nullable=True)
    column_no = Column(Integer, nullable=True)
    parent_tag_id = Column(Integer, ForeignKey('Tag.id'), nullable=True)
    assoc_to_tag_id = Column(Integer, ForeignKey('Tag.id'), nullable=True)
    type = Column(String, nullable=True)

    compile_unit = relation("CompileUnit", backref="tags")
    file = relation("File", backref="tags")
    parent_tag = relation("Tag", backref=backref("children_tags"), foreign_keys=[parent_tag_id], remote_side=[id])
    assoc_to_tag = relation("Tag", backref=backref("assoc_from_tags"), foreign_keys=[assoc_to_tag_id], remote_side=[id])

    def __init__(self,*args):
        self.tmp_assoc_to_tag = None
        super().__init__(*args)
