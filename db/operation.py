from db.model import *
from os.path import basename, dirname, normpath
import os
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import create_engine


class Operation:
    Session = None
    engine = None
    @classmethod
    def prepare(cls, db_path):
        if cls.engine is None:
            cls.engine = create_engine('sqlite:///' + db_path, echo=False)
            if db_path == ':memory:' or not os.path.exists(db_path):
                Base.metadata.create_all(cls.engine)
        session_factory = sessionmaker(bind=cls.engine)
        cls.Session = scoped_session(session_factory)

    def __init__(self):
        self._session = Operation.Session()
        self._file = None
        self._tags = []

    def add_compilation_unit(self, comp_dir, comp_file, index):
        cu = CompileUnit()
        path = normpath(comp_dir.strip() + os.path.sep + comp_file.strip())
        cu.comp_dir = comp_dir
        cu.comp_file = comp_file
        cu.object_name = path
        cu.id = index
        self._session.add(cu)
        return cu

    def add_tag(self, tag):
        self._session.add(tag)
        return tag

    def add_file(self, filename, dir_reltocompdir):
        file = File()
        file_path = "{}/{}".format(dir_reltocompdir, filename)
        path = normpath(file_path)
        file.file_name = basename(path)
        file.file_directory = dirname(path)
        file.file_dir_rel_to_comp_dir = dir_reltocompdir
        self._session.add(file)
        return file

    def commit(self):
        self._session.commit()

    def session(self):
        return self._session
