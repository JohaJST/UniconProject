# -*- coding: utf-8 -*-
"""Полный список msgid текущего словаря + где встречаются спорные TextID."""
import re

data = open("locale/ru/LC_MESSAGES/django.po", encoding="utf-8").read()
msgids = [
    m.strip().replace('"', "").replace("\\n", " ")
    for m in re.findall(r"^msgid (.*?)\nmsgstr", data, re.S | re.M)
]
msgids = [m for m in msgids if m]
print("Всего msgid:", len(msgids))
for m in sorted(msgids):
    print(" -", m[:90])
