"""
คลีนชื่อ master fund และจัดชื่อที่เป็นกองเดียวกันให้อยู่กลุ่มเดียวกัน

ทุกแถวจะได้ 2 คอลัมน์:
  Master_Fund_Key     คีย์สำหรับจัดกลุ่ม (ตัวพิมพ์เล็ก ตัดคำฟุ่มเฟือย)  — หน้าเว็บใช้คีย์นี้
  Master_Fund_Search  ชื่อที่แสดง (ชื่อที่ บลจ. ใช้บ่อยที่สุดในกลุ่มนั้น)

ชื่อที่กฎอัตโนมัติจับไม่ได้ ให้เพิ่มใน master_aliases.csv (variant,canonical)

รันเดี่ยวเพื่อคลีน funds_data.json ใหม่โดยไม่ต้องดึง API:
    python master_names.py
"""
import collections
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ALIAS_FILE = os.path.join(HERE, "master_aliases.csv")

# ---------- 1. clean one raw value into a readable name ----------

PREFIX = re.compile(
    r"^\s*((ชื่อ\s*)?กองทุน\s*(หลัก)?\s*[:：]\s*"
    r"|(name\s+of\s+)?master\s*fund\s*(name)?\s*[:：]\s*"
    r"|กองทุนเปิด\s+|กองทุน\s+)",
    re.I,
)
CLASS_WORD = re.compile(r"(\s*\(\s*Class\b.*|,\s*Class\b.*|-+\s*Class\b.*|\s+Class\b.*)", re.I)
CCY = r"(?:USD|EUR|SGD|S\$|RMB|JPY|HKD|GBP)"
# share-class / currency tails, peeled off the end repeatedly
TAILS = [
    re.compile(r"\s*\(\s*Master\s+Fund\s*\)?\s*$", re.I),
    re.compile(r"[\s,\-]*\(?\s*" + CCY + r"\s*\)?\s*\(?\s*(acc|dist|mth)\s*\)?\s*$", re.I),  # USD (Acc
    re.compile(r"[\s,\-]*\(\s*(acc|dist|mth)\s*\)?\s*$", re.I),                              # (Acc
    re.compile(r"[\s,\-]+(acc|dist)\s*$", re.I),                                              # - Acc
    re.compile(r"[\s,\-]*\(\s*" + CCY + r"\s*\)?\s*$"),                                      # (USD
    re.compile(r",\s*" + CCY + r"\b.*(Accumulating|Distributing).*$", re.I),                  # , USD S Accumulating Unhedged
    re.compile(r"\s*-\s*Select\s+Accumulating\s*$", re.I),
    re.compile(r"\s+[A-Z]{1,2}\d?(-[A-Za-z0-9]+)*\s+" + CCY + r"\s*$"),                       # I USD, IL USD
    re.compile(r"\s+" + CCY + r"\s*\)?\s+[A-Z]\d?(-[A-Za-z0-9]+)+\s*$"),                      # (USD) I-A1-acc
    re.compile(r"\s+[A-Z]\d?(-[A-Za-z0-9]+)*-acc\s*$", re.I),                                 # I-96-ACC
    re.compile(r"\s+[A-Z]-ACC-" + CCY + r"\s*$", re.I),                                       # Y-ACC-USD
    re.compile(r"\s+[A-Z]\s*\(\s*(acc|dist|mth)\s*\)\s*-\s*" + CCY + r"\s*$", re.I),          # C (acc) - USD
    re.compile(r"\s*-?\s*[A-Z]\s*\(\s*mth\s*\)\s*-\s*" + CCY + r"\s*$", re.I),                # A (mth) - USD
    re.compile(r"\s+\(\s*J\d\s+" + CCY + r"\s*\)?\s*$", re.I),                                # (J2 USD
    re.compile(r",?\s*\(\s*" + CCY + r"\s*\)\s*,?\s*[A-Z][A-Za-z0-9\-]{0,5}\s*$"),              # (USD) I-A1 / , (USD), IA
    re.compile(r"\s+[A-Z]-\d+\s*$"),                                                           # I-96
    re.compile(r",\s*[A-Z]\d\s*$"),                                                            # , X1
    re.compile(r"\s+" + CCY + r"\s*\(\s*(acc|dist)\s*\)?\s*$", re.I),                          # EUR (Dist
]


def balance_parens(s):
    """close a '(' the source left open, drop a stray ')'"""
    depth = 0
    out = []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                continue
            depth -= 1
        out.append(ch)
    return "".join(out) + ")" * depth


def clean_name(val):
    if val is None:
        return ""
    s = str(val)
    if s.strip().lower() in ("", "none", "nan", "null"):
        return ""
    s = s.replace("\xa0", " ").replace("​", "")
    s = re.sub(r"[–—]", "-", s)
    s = re.sub(r"[®™©]", "", s)
    s = PREFIX.sub("", s)
    s = CLASS_WORD.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(3):
        before = s
        for p in TAILS:
            s = p.sub("", s).strip()
        if s == before:
            break
    s = s.strip(" :：-,")
    s = re.sub(r"\s*-\s*", " - ", s) if re.search(r"\w-\s|\s-\w", s) else s   # "Fund- All" -> "Fund - All"
    s = re.sub(r"\s+", " ", s)
    return balance_parens(s).strip()


# ---------- 2. grouping key ----------

# abbreviations / typos -> the long form, applied to the lowercase text
REWRITES = [
    (r"\bishare\b", "ishares"),
    (r"\bpmorgan\b", "jpmorgan"),
    (r"\bjpm\b", "jpmorgan"),
    (r"\bj\.?p\.? morgan\b", "jpmorgan"),
    (r"\bbgf\b", "blackrock global"),
    (r"\baxa wf\b", "axa world"),
    (r"\bglobal investors series\b", "gis"),
    (r"\beastspring investment\b", "eastspring investments"),
    (r"\bt\.\s*rowe\b", "t rowe"),
    (r"\bs&p\s*500\b", "s p 500"),
    (r"\bschroders?\b", "schroder"),
]
# words that never tell two funds apart
DROP = {
    "fund", "funds", "the", "plc", "sicav", "icav", "lux", "ireland", "sa",
    "portfolio", "usd", "and", "inc", "ltd", "trust",
}


def group_key(name):
    s = name.lower()
    for pat, rep in REWRITES:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\(\s*lux\.?\s*\)", " ", s)
    toks = re.findall(r"[^\W_]+", s)
    seen, out = set(), []
    for t in toks:
        if t in DROP or t in seen:   # "Polar Capital Funds plc - Polar Capital Global ..." -> brand once
            continue
        seen.add(t)
        out.append(t)
    return " ".join(sorted(out))


# ---------- 3. manual merges ----------

def load_aliases():
    """master_aliases.csv: variant,canonical  (either side may be any spelling)"""
    m = {}
    if not os.path.exists(ALIAS_FILE):
        return m
    with open(ALIAS_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            v, c = (row.get("variant") or "").strip(), (row.get("canonical") or "").strip()
            if v and c:
                m[group_key(clean_name(v))] = group_key(clean_name(c))
    return m


def is_shouty(s):
    letters = [c for c in s if c.isalpha() and c.isascii()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def annotate(rows, raw_field="feederfund_master_fund"):
    """add Master_Fund_Key / Master_Fund_Search to every row (in place)"""
    aliases = load_aliases()
    names = {}
    for r in rows:
        n = clean_name(r.get(raw_field))
        k = group_key(n) if n else ""
        k = aliases.get(k, k)
        r["Master_Fund_Key"] = k
        names.setdefault(k, collections.Counter())[n] += 1
    display = {}
    for k, c in names.items():
        # most used spelling; avoid ALL CAPS; on a tie the shorter one (usually no umbrella repeat)
        display[k] = sorted(c.items(), key=lambda kv: (is_shouty(kv[0]), -kv[1], len(kv[0])))[0][0]
    for r in rows:
        r["Master_Fund_Search"] = display[r["Master_Fund_Key"]]
    return rows


if __name__ == "__main__":
    path = os.path.join(HERE, "funds_data.json")
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    before = len({r.get("Master_Fund_Search") for r in rows})
    annotate(rows)
    after = len({r["Master_Fund_Key"] for r in rows})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    print(f"master fund names: {before} -> {after} groups")
