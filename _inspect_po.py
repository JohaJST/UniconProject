# -*- coding: utf-8 -*-
"""Инспекция .po словарей: список msgid и заполненность переводов."""
import re
import sys

for lang in ("ru", "uz", "en"):
    path = f"locale/{lang}/LC_MESSAGES/django.po"
    data = open(path, encoding="utf-8").read()
    entries = re.findall(
        r"^msgid (.*?)\nmsgstr (.*?)(?=\n(?:#|\nmsgid|\Z))",
        data,
        re.S | re.M,
    )
    filled = [t for m, t in entries if t.strip() not in ("", '""')]
    print(f"=== {lang}: {len(entries)} entries, filled={len(filled)}")
    for m, t in entries:
        m = m.strip().replace('"', "")
        t = t.strip().replace('"', "")
        flag = "OK " if t else "EMPTY"
        print(f"  [{flag}] {m[:70]!r} -> {t[:50]!r}")
