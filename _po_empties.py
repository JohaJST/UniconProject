# -*- coding: utf-8 -*-
"""Полный список EMPTY (или fuzzy) записей во всех трёх .po."""
import re


def parse_po(path):
    """Возвращает [(msgid, msgstr, raw_block)] в порядке следования."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\n+", content)
    entries = []
    for block in blocks:
        mid = re.search(r'^msgid (.*?)(?=\nmsgstr)', block, re.S | re.M)
        if not mid:
            continue
        msgid = mid.group(1)
        mstr = re.search(r'^msgstr (.*?)$', block, re.M)
        msgstr = mstr.group(1) if mstr else ""
        # флаг fuzzy в комментарии блока (до msgid)
        fuzzy = bool(re.search(r"^#,.*\bfuzzy\b", block, re.M))
        entries.append((msgid, msgstr, fuzzy))
    return entries


def clean(s):
    return s.strip().replace('"', "")


for lang in ("ru", "uz", "en"):
    path = f"locale/{lang}/LC_MESSAGES/django.po"
    entries = parse_po(path)
    print(f"\n=== {lang} ===")
    for msgid, msgstr, fuzzy in entries:
        mid = clean(msgid)
        if not mid:
            continue
        empty = clean(msgstr) == ""
        if empty or fuzzy:
            flag = "FUZZY " if fuzzy else ""
            print(f"  [{flag}{'EMPTY' if empty else 'fill'}] {mid[:80]!r}")
  