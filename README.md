# 简介
ctags程序生成tag文件时，不会做语义分析，可能从未编译的源码文件中提取tag，导致同名tag，
无法精确定位到想要的tag。

本程序从带有DWARF调试信息的ELF文件中，提取出Tag文件，便于编辑器浏览源码。

objdump的--debugging-tags选项做的是类似的事，但是这个选项只有在调试信息格式是STABS和
IEEE时才可用，却无法根据DWARF这么强大的调试格式生成tag文件，于是只好自己做一个了。

# TODO
[ ]setup.py文件
[ ]性能优化
