#!/usr/bin/env python3
"""Refresh the offline fallback copies of data/*.json embedded in index.html.

Each list is embedded between /*<NAME>_EMBED_START*/ ... /*<NAME>_EMBED_END*/ markers.
A missing or empty JSON file embeds null / an empty list; the app then relies on typing.
"""
import json, os, re, sys

html_path = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
base = os.path.dirname(os.path.abspath(html_path))
LISTS = [('CENTERS', 'data/centers.json', 'centers', 10), ('HOMES', 'data/homes.json', 'homes', 0)]
html = open(html_path, encoding='utf-8').read()
for marker, rel, key, min_rows in LISTS:
    path = os.path.join(base, rel)
    data = None
    if os.path.exists(path):
        data = json.load(open(path, encoding='utf-8'))
        if not isinstance(data.get(key), list) or len(data[key]) < min_rows:
            sys.exit(f'::error::{rel} looks wrong; not embedding')
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    pat = re.compile(r'/\*' + marker + r'_EMBED_START\*/.*?/\*' + marker + r'_EMBED_END\*/', re.S)
    if not pat.search(html):
        sys.exit(f'::error::{marker} embed markers not found in {html_path}')
    html = pat.sub(lambda m: f'/*{marker}_EMBED_START*/{blob}/*{marker}_EMBED_END*/', html, count=1)
    print(f'Embedded {rel}: {len(data[key]) if data else "none"}')
open(html_path, 'w', encoding='utf-8').write(html)
