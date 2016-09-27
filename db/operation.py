from db.model import *
from os.path import basename, dirname, normpath
import os
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import create_engine


class Operation:
    Session = None
    @classmethod
    def prepare(cls, db_path='memory'):
        engine = create_engine('sqlite:///' + db_path, strategy='threadlocal', echo=False)
        if not os.path.exists(db_path):
            Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        cls.Session = scoped_session(session_factory)

    def __init__(self):
        self._session = Operation.Session()
        self._file = None
        self._tags = []

    def add_compilation_unit(self, filename):
        cu = CompileUnit()
        path = normpath(filename)
        cu.object_name = path
        self._session.add(cu)
        return cu

    def add_tag(self, tag):
        self._session.add(tag)
        return tag

    def add_file(self, filepath):
        file = File()
        path = normpath(filepath)
        file.file_name = basename(path)
        file.file_directory = dirname(path)
        self._session.add(file)
        return file

    def commit(self):
        self._session.commit()

    def session(self):
        return self._session
