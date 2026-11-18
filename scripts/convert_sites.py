#!/usr/bin/env python3
"""Convert a site contact sheet (xlsx) to the JSON list the app loads.

  python scripts/convert_sites.py SRC.xlsx data/centers.json --key centers --min-rows 10 --require name,license,capacity,email
  python scripts/convert_sites.py SRC.xlsx data/homes.json   --key homes   --min-rows 1  --require name

Columns are found by header name (case/space/punctuation-insensitive, with common synonyms).
ONLY these columns are exported: name, address, cityState, phone, contact, email, license, capacity.
Anything else in the sheet (e.g. child or enrollment data) is ignored.
Exits non-zero and leaves the existing JSON untouched if the input isn't a valid xlsx
or doesn't look like the expected sheet, so a revoked share link can't wipe the list.
"""
import argparse, json, os, re, sys, tempfile, zipfile

SYNONYMS = {
    'name': ['name', 'center', 'center name', 'facility', 'facility name', 'provider name', 'provider', 'home', 'home name', 'site', 'site name'],
    'businessName': ['provider business name', 'business name', 'dba', 'business'],
    'address': ['address', 'street', 'street address', 'address 1'],
    'cityState': ['city/state', 'city state', 'city, state', 'city/st', 'city st zip', 'city/state/zip', 'city, state zip', 'city'],
    'phone': ['phone no', 'phone', 'phone number', 'phone #', 'telephone', 'tel', 'cell'],
    'contact': ['contact', 'contact name', 'director', 'contact person'],
    'email': ['email', 'e-mail', 'email address', 'e-mail address', 'e mail', 'provider email'],
    'license': ['lic', 'license', 'license #', 'lic #', 'license no', 'license number', 'lic no', 'provider license #', 'provider license', 'provider license number'],
    'capacity': ['cap', 'capacity', 'license capacity', 'licensed capacity', 'lic cap'],
}
OPTIONAL = {'businessName'}  # exported only when the sheet has the column (keeps centers.json unchanged)
EXTRA = {'state': ['state', 'st'], 'zip': ['zip', 'zip code', 'zipcode', 'postal code']}  # used to build cityState


def norm_header(h):
    h = '' if h is None else str(h)
    h = re.sub(r'\s+', ' ', h.replace('\u00a0', ' ')).strip().lower()
    return h.rstrip('.:').strip()


def fail(msg):
    print(f'::error::{msg}', file=sys.stderr)
    sys.exit(1)


def clean(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = re.sub(r'\s+', ' ', str(v).replace('\u00a0', ' ')).strip()
    return s.rstrip(',').strip()


def find_columns(header):
    idx = {}
    normed = [norm_header(h) for h in header]
    for key, names in list(SYNONYMS.items()) + list(EXTRA.items()):
        for cand in names:  # first synonym that matches wins (synonyms are in priority order)
            hits = [i for i, h in enumerate(normed) if h == cand or h.replace('.', '') == cand]
            if hits:
                idx[key] = hits[0]
                break
    return idx, normed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--key', default='centers')
    ap.add_argument('--min-rows', type=int, default=10)
    ap.add_argument('--require', default='name')
    ap.add_argument('--source-name', default='')
    a = ap.parse_args()

    if not os.path.exists(a.src) or os.path.getsize(a.src) < 1000:
        fail(f'{a.src} is missing or too small; the share link may be revoked.')
    if not zipfile.is_zipfile(a.src):
        with open(a.src, 'rb') as f:
            head = f.read(120)
        fail(f'Download is not an xlsx file (starts with {head[:60]!r}). The share link may be revoked or need sign-in.')
    import openpyxl
    try:
        wb = openpyxl.load_workbook(a.src, read_only=True, data_only=True)
    except Exception as e:
        fail(f'Could not open workbook: {e}')

    # pick the first sheet (Sheet1 preferred) whose header row has a name column
    sheets = (['Sheet1'] if 'Sheet1' in wb.sheetnames else []) + [n for n in wb.sheetnames if n != 'Sheet1']
    chosen = None
    for sn in sheets:
        rows = list(wb[sn].iter_rows(values_only=True))
        for hr in range(min(5, len(rows))):  # header may not be on row 1
            idx, normed = find_columns(rows[hr])
            if 'name' in idx:
                chosen = (sn, rows, hr, idx, normed)
                break
        if chosen:
            break
    if not chosen:
        fail('No sheet with a Name/Provider column was found.')
    sn, rows, hr, idx, normed = chosen
    required = [r for r in a.require.split(',') if r]
    missing = [r for r in required if r not in idx]
    if missing:
        fail(f'Sheet "{sn}" is missing expected columns {missing}. Headers found: {normed}')
    print(f'Sheet "{sn}", header row {hr + 1}: ' + ', '.join(f'{k}<-"{normed[i]}"' for k, i in idx.items()))

    out_rows = []
    for r in rows[hr + 1:]:
        raw = lambda k: r[idx[k]] if k in idx and idx[k] < len(r) else None
        rec = {k: clean(raw(k)) for k in SYNONYMS if k not in OPTIONAL or k in idx}
        rec['name'] = re.sub(r'\s+,', ',', rec['name'])  # 'Waits , Teresa' -> 'Waits, Teresa'
        # separate City / State / Zip columns -> 'City, ST 12345'
        if 'cityState' in idx and normed[idx['cityState']] == 'city' and ('state' in idx or 'zip' in idx):
            city, st, z = clean(raw('cityState')), clean(raw('state')).upper(), clean(raw('zip'))
            rec['cityState'] = ', '.join(p for p in [city, ' '.join(p for p in [st, z] if p)] if p)
        # multi-line / multi-value phones and emails -> '; ' and ', '
        ph = '' if raw('phone') is None else str(raw('phone'))
        rec['phone'] = '; '.join(p for p in (clean(x) for x in re.split(r'[\n;]+', ph)) if p)
        em = '' if raw('email') is None else str(raw('email'))
        ems = [re.sub(r'^mailto:', '', e, flags=re.I).strip('<>;,. ') for e in re.split(r'[\s;,]+', em)]
        rec['email'] = ', '.join(e for e in ems if e)
        if not rec['name']:
            continue  # blank or stray rows
        out_rows.append(rec)
    if len(out_rows) < a.min_rows:
        fail(f'Only {len(out_rows)} rows found (expected at least {a.min_rows}); refusing to overwrite {a.dst}.')
    out_rows.sort(key=lambda c: c['name'].lower())
    data = {'source': a.source_name or os.path.basename(a.dst), 'count': len(out_rows), a.key: out_rows}
    text = json.dumps(data, ensure_ascii=False, indent=1) + '\n'
    d = os.path.dirname(os.path.abspath(a.dst)); os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, a.dst)
    print(f'Wrote {len(out_rows)} rows to {a.dst}')


if __name__ == '__main__':
    main()
