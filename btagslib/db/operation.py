from os.path import basename, dirname, normpath
import os
from threading import Lock
from sqlalchemy import event
from .model import *


class Operation:
    engine = None
    file_id_counter = 0
    file_id_lock = Lock()
    @classmethod
    def prepare(cls, db_path):
        if cls.engine is None:
            cls.engine = create_engine('sqlite:///' + db_path, echo=False, connect_args={'timeout': 3600})
            if db_path == ':memory:' or not os.path.exists(db_path):
                Base.metadata.create_all(cls.engine)
        event.listen(cls.engine, 'connect', Operation._set_no_synchronous)

    @staticmethod
    def _set_no_synchronous(dbapi_con, con_record):
        dbapi_con.execute('PRAGMA synchronous=OFF')
        dbapi_con.execute('PRAGMA journal_mode=OFF')
        dbapi_con.execute('PRAGMA temp_store=MEMORY')

    def __init__(self):
        self._scoped_session = scoped_session(sessionmaker(bind=self.engine))
        self._session = self._scoped_session()
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
        with Operation.file_id_lock:
            Operation.file_id_counter += 1
            file.id = Operation.file_id_counter
        file.file_name = basename(path)
        file.file_directory = dirname(path)
        file.file_dir_rel_to_comp_dir = dir_reltocompdir
        self._session.add(file)
        return file

    def commit(self):
        self._session.commit()

    def close(self):
        self._scoped_session.remove()

    def session(self):
        return self._session
