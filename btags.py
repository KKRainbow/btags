#!/usr/bin/env python3
import os
from os.path import dirname

from debuginfo.dwarfformat import DwarfFormat
from tagfile.ctag import CtagFormat
import argparse as ap

if __name__ == '__main__':
    debug_info_mapper = {
        'dwarf': DwarfFormat
    }
    tag_format_mapper = {
        'ctag': CtagFormat
    }
    parser = ap.ArgumentParser(
        prog='Binary tag file generator.',
        description='Generate kinds of tag files from binary object file with debug information.',
    )
    parser.\
        add_argument('-s', '--project-dir', help='The path in tag file will be relative to this')
    parser. \
        add_argument('-t', '--tag-file', default='./ctags', help='Save path of generated tag file')
    parser. \
        add_argument('-d', '--database-file', default='./btag.sqlite',
                     help='The directory where the tag info database will be placed')
    parser.\
        add_argument('-o', '--only-database', help='Only generate tag info database, do not generate tag file',
                     action='store_true')
    parser. \
        add_argument('-j', '--jobs', help='Number of work threads', default=1, type=int)

    db_group = parser.add_mutually_exclusive_group()
    db_group. \
        add_argument('-A', '--append-db', help='Do not remove existed database, append info to it',
                     action='store_true')
    db_group. \
        add_argument('-n', '--new-db', help='If database exists, remove it and generate a new one',
                     action='store_true')

    parser. \
        add_argument('-a', '--append-tag', help='Do not remove existed tag file, append info to it',
                     action='store_true')
    parser. \
        add_argument('-f', '--debug-info-format', help='The debug info format in binary file',
                     default='dwarf', choices=debug_info_mapper.keys())
    parser. \
        add_argument('-F', '--tag-file-format', help='The debug info format in binary file',
                     default='ctag', choices=tag_format_mapper.keys())

    parser. \
        add_argument('binary_file', nargs=1, help='The path of the binary file with debug info',
                     type=ap.FileType('rb'))

    bin_path = '/home/sunsijie/Project/barrelfish/build/x86_64/sbin/cpu'
    db_path = '/home/sunsijie/test.sqlite'
    tag_path = '/home/sunsijie/tags'

    nb = parser.parse_args()
    bin_path = nb.binary_file[0].name
    db_path = nb.database_file
    tag_path = nb.tag_file
    project_path = dirname(nb.tag_file) if nb.project_dir is None else nb.project_dir

    if not nb.append_tag:
        if os.path.exists(tag_path):
            os.remove(tag_path)
    if nb.new_db:
        if os.path.exists(db_path):
            os.remove(db_path)

    df = debug_info_mapper[nb.debug_info_format](bin_path, db_path)
    if not df.has_debug_info():
        print('No debug info found in binary file.')
        exit()
    df.parse(nb.jobs)
    if nb.only_database:
        exit()
    ct = tag_format_mapper[nb.tag_file_format](db_path)
    ct.get_tag_file(open(tag_path, 'a+'), project_path)
