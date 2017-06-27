# Introduction
Generating tags file according to the DWARF debug information in the binary file.

# Prerequisites
- SQLAlchemy
- SQLite3

# Installation
```
# Ubuntu
apt install sqlite3 
# ArchLinux
pacman -S sqlite3
pip install btags
```

# Usage
```
btags.py -j 2 -c /dir/to/the/build/root /path/to/the/binary
```
* -j max worker threads
* -c specify the directory under which the binary is compiled

After, you will get a tags file under current working directory.

It can be used as following
```
vim -t main
```

For examples
Assume there is a autoconf project under dir /tmp/project, and you use the following
command to build it.
```
cd /tmp/project
mkdir build
cd build
../configure
make
```
Then, ``/tmp/project/build`` will be the build root, because the project is compiled
under this directory.

# TODO
- [] Replace sqlite with other faster data store mean
- [] Add test cases
- [] Add Travis CI support
