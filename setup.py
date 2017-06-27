from setuptools import setup, find_packages
from os import path
from btagslib.version import __version__

with open(path.join(path.dirname(__file__), 'README.rst')) as f:
    long_description = f.read()

setup(
    name='btags',
    version=__version__,
    description='Generate tag file according to the debug information such as DWARF including in the binary file',
    long_description=long_description,
    url='https://github.com/KKRainbow/btagslib',
    author='KKRainbow',
    author_email='sunsijie@buaa.edu.cn',
    license='MIT',
    platforms='Cross Platform',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    keywords='dwarf ctags tag binary',
    packages=find_packages(exclude=['tests*']),
    install_requires=['SQLAlchemy', 'pyelftools'],
    python_requires='>=3',
    entry_points={
        'console_scripts': [
            'btags=btagslib.cli.btags:main'
        ],
    }
)
