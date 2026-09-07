#!/usr/bin/env python3
"""Regional Center vendor lists — the autism-relevance signal.

NPPES says what a provider's profession is. It cannot say whether they work
with autistic people. California's regional centres can: they publish their
vendor lists (Welf. & Inst. Code, the SB 74 transparency requirement), and each
vendor row carries the DDS service code the state actually pays that vendor
under. That is a spending record, not a self-description, which is why it is
worth more than any directory's "specialties" field.

    python3 autism/scripts/parse_rc_vendors.py --fetch
    python3 autism/scripts/parse_rc_vendors.py --parse
    python3 autism/scripts/parse_rc_vendors.py --status

Nothing here scrapes a private directory. Every file below is a document a
regional centre publishes because it is required to.
"""
import argparse, csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

def repo_root():
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / ".git").exists():
            return parent
    return p.parent

ROOT = repo_root()
WORK = ROOT / "autism" / "data" / "providers" / "rc"
WORK.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# ---------------------------------------------------------------- service codes
# Verified against the DDS Rate Reform Service Code Crosswalk dated 2026-02-05.
# Not typed from memory: a wrong code here would silently mislabel thousands of
# vendors, and nothing downstream would notice.
SERVICE_CODES = {
    "055": "Community Integration Training Program",
    "062": "Personal Assistance",
    "091": "In-home/Mobile Day Program",
    "109": "Supplemental Residential Program Support",
    "110": "Supplemental Program Support - Day Program",
    "113": "DSS Licensed Specialized Residential Facility",
    "116": "Early Start Specialized Therapeutic Services",
    "117": "Specialized Therapeutic Services (age 3 and older)",
    "510": "Adult Development Center",
    "515": "Behavior Management Program",
    "520": "Independent Living Program",
    "531": "Day Services",
    "612": "Behavior Analyst",
    "613": "Associate Behavior Analyst",
    "615": "Behavior Management Assistant",
    "616": "Behavior Technician - Paraprofessional",
    "805": "Infant Development Program",
    "862": "In-Home Respite Services",
    "880": "Transportation - Additional Component",
    "896": "Supported Living Services",
    "915": "Residential Facility Serving Adults - Staff Operated",
}

# Services the state funds specifically for developmental disability and autism.
# A vendor billing any of these is doing autism-directed work by definition.
AUTISM_DIRECT = {"116", "117", "515", "612", "613", "615", "616", "805"}
# Services that support the family rather than treat the child. Respite is the
# single most-requested and least-supplied thing parents ask for, so it earns
# its own label rather than being lumped in with the rest.
AUTISM_SUPPORT = {"862"}

# ---------------------------------------------------------------- sources
# url=None means we have not found that centre's published list yet. Left
# visible on purpose: a missing centre is a hole in California coverage, and a
# quietly absent dict key is how a hole becomes invisible.
RC_SOURCES = {
    "rceb":     dict(name="Regional Center of the East Bay", fmt="pdf",
                     url="https://rceb.org/wp-content/uploads/2026/08/SB74ListofVendors-08052026-Qport.pdf"),
    "inland":   dict(name="Inland Regional Center", fmt="xlsx",
                     url="https://www.inlandrc.org/wp-content/uploads/2026/07/IRC-Vendor-Master-Listing-7-22-26.xlsx"),
    "rcoc":     dict(name="Regional Center of Orange County", fmt="pdf",
                     url="https://www.rcocdd.com/wp-content/uploads/pdf/vendorsearch/Vendor_List.pdf"),
    "sgprc":    dict(name="San Gabriel/Pomona Regional Center", fmt="pdf",
                     url="https://sgprc.org/wp-content/uploads/2026/06/Provider-Search-050526.pdf"),
    "westside": dict(name="Westside Regional Center", fmt="pdf",
                     url="https://westsiderc.org/wp-content/uploads/2026/03/WRC-SERVICE-PROVIDER-DIRECTORY-Updated-3.26.2026.pdf"),
    "sdrc":     dict(name="San Diego Regional Center", fmt="pdf",
                     url="https://www.sdrc.org/_files/ugd/8a8ffe_72b7309de1bb4318bc5d5b6bc28b6400.pdf",
                     note="word-layout PDF, service categories in words rather than codes"),
    "sarc":     dict(name="San Andreas Regional Center", fmt="csv",
                     url="https://sanandreasregional.org/wp-content/uploads/provider-directory/sarc-provider-directory-2026-07-13.csv"),
    "harbor":   dict(name="Harbor Regional Center", fmt="pdf",
                     url="https://www.harborrc.org/wp-content/uploads/2025/09/service_provider_resource_list_9.10.25.pdf"),
    "ggrc":     dict(name="Golden Gate Regional Center", fmt="pdf",
                     url="https://www.ggrc.org/wp-content/uploads/2026/03/Service_Provider_Directory_3-26.pdf",
                     note="category words rather than service codes"),

    "acrc":     dict(name="Alta California Regional Center", fmt=None, url=None),
    "cvrc":     dict(name="Central Valley Regional Center", fmt="pdf",
                     url="https://www.cvrc.org/wp-content/uploads/2020/04/VendServ.pdf",
                     note="category words; file is dated 2020 and is the current published link"),
    "elarc":    dict(name="Eastern Los Angeles Regional Center", fmt="pdf",
                     url="https://www.elarc.org/files/assets/mainsite/v/1/transparency/documents/vendor-list-no-parent-vendor.pdf",
                     referer="https://www.elarc.org/Transparency/Transparency-Contracts/Vendor-List"),
    "farnorthern": dict(name="Far Northern Regional Center", fmt=None, url=None,
                     note="bot-detection challenge; must be downloaded by hand"),
    "kern":     dict(name="Kern Regional Center", fmt="pdf",
                     url="https://kernrc.org/wp-content/uploads/2024/03/Vendor-List-07292024-v3.pdf",
                     note="category words rather than service codes"),
    "lanterman": dict(name="Frank D. Lanterman Regional Center", fmt=None, url=None,
                     note="bot-detection challenge; must be downloaded by hand"),
    "nbrc":     dict(name="North Bay Regional Center", fmt="xlsx",
                     url="https://www.nbrc.net/wp-content/uploads/2025/10/Copy-of-NBRC-Vendors-2023-24-1-1.xlsx"),
    # One of the densest catchments in the state, and no file. Six routes tried,
    # recorded so nobody spends another afternoon on it: 1,771 service_provider
    # records sit at /wp-json/wp/v2/service_provider and every one has an empty
    # title, empty content and empty ACF; the taxonomy archives render nothing;
    # the search form's GET parameters are not server-rendered; the theme ships
    # no AJAX endpoint. What IS public is the service_code taxonomy with counts,
    # so the shape of what North LA funds is knowable even though who it funds
    # is not: 805 Infant Development 112, 612 Behavior Analyst 51, 862 In-Home
    # Respite 48, 615 Behavior Management Assistant 42, 116 Early Start
    # therapeutic 21, 616 Behavior Technician 11, 117 the same therapeutic
    # service at three and over 5. Twenty-one against five is the age-three drop
    # again, on a sixteenth centre, from a REST count rather than a parsed PDF.
    "nlacrc":   dict(name="North Los Angeles County Regional Center", fmt=None, url=None,
                     note="no file published; identifying fields absent from every public interface"),
    "redwood":  dict(name="Redwood Coast Regional Center", fmt="pdf",
                     url="https://redwoodcoastrc.org/wp-content/uploads/2026/03/2026-March-Vendor-List-updated.pdf",
                     note="category words rather than service codes"),
    "sclarc":   dict(name="South Central Los Angeles Regional Center", fmt="pdf",
                     url="https://sclarc.org/wp-content/uploads/2025/03/CO22021000313329830_zOsR8KHyRDyjCAxhEajL_VendorListforPublishingFeb24FINAL.pdf"),
    "tcrc":     dict(name="Tri-Counties Regional Center", fmt=None, url=None),
    "vmrc":     dict(name="Valley Mountain Regional Center", fmt=None, url=None),
}

def need(mod):
    try:
        return __import__(mod)
    except ImportError:
        sys.exit(f"Missing {mod}. Install it: pip3 install {mod}")

# ---------------------------------------------------------------- fetch
def fetch(only=None):
    requests = need("requests")
    for key, src in RC_SOURCES.items():
        if only and key != only:
            continue
        if not src["url"]:
            print(f"  {key:11s} no published list located yet"
                  + (f" — {src['note']}" if src.get("note") else ""))
            continue
        out = WORK / f"{key}.{src['fmt']}"
        try:
            # Some centres refuse a request that arrives without the page it
            # was linked from. Eastern LA returns 403 to a bare fetch of its own
            # published vendor list and 200 with the referring page named — so
            # a source can carry the page a browser would have come from.
            h = {"User-Agent": UA, "Accept": "application/pdf,*/*"}
            if src.get("referer"):
                h["Referer"] = src["referer"]
            r = requests.get(src["url"], headers=h, timeout=180, allow_redirects=True)
            r.raise_for_status()
            out.write_bytes(r.content)
            print(f"  {key:11s} {len(r.content)/1e6:6.2f} MB -> {out.name}")
        except Exception as e:
            print(f"  {key:11s} FAILED: {type(e).__name__}: {e}")

# ---------------------------------------------------------------- parse
HDR_KEYS = {
    "vendor_no": ("VENDOR#", "VENDOR NO", "VENDOR NUMBER", "VENDOR ID",
                  "VENDOR #", "RESOURCE #", "RESOURCE NUMBER"),
    "category":  ("SVC CATEGORY", "SERVICE CATEGORY", "SRV CATEGORY",
                  "SERVICE TYPE(S)", "DESCRIPTION"),
    "name":      ("VENDOR NAME", "PROVIDER NAME", "SERVICE PROVIDER", "COMPANY NAME",
                  "RESOURCE NAME", "SERVICE PROVIDER NAME"),
    # "SEVICE CODE" is not a typo here: it is Harbor RC's own column heading,
    # and matching what a file actually says beats matching what it should say.
    "code":      ("SVC CODE", "SERVICE CODE", "SERV CODE", "SEVICE CODE",
                  "SERVICE CODE(S)", "SRV CODE"),
    "sub":       ("SUB CODE", "SUB-CODE", "SUBCODE"),
    "address":   ("ADDRESS", "STREET", "MAILING ADDRESS", "PHYSICAL ADDRESS"),
    "city":      ("CITY",),
    "zip":       ("ZIP CODE", "ZIPCODE", "ZIP"),
    "phone":     ("PHONE NUMBER", "PHONE", "TELEPHONE"),
    "county":    ("COUNTY",),
}

def _norm(h):
    return re.sub(r"\s+", " ", str(h or "").replace("\n", " ")).strip().upper()

def _map_header(hdr):
    """Return {field: column index} for whichever columns this file happens to have."""
    idx = {}
    cells = [_norm(h) for h in hdr]
    for field, names in HDR_KEYS.items():
        for i, cell in enumerate(cells):
            if not cell:
                continue
            if any(cell == n or cell.startswith(n) for n in names):
                idx.setdefault(field, i)
                break
    return idx

def _pad(code):
    """Normalise a service code to three digits.

    Two shapes arrive here. Excel silently drops leading zeros, so 055 comes
    through as 55. And some centres print the code together with its name in
    one cell — "090 - Crisis Inter" — so take the leading run of digits rather
    than stripping all non-digits, which would turn that cell into 090.
    """
    raw = str(code or "").strip()
    m = re.match(r"\s*(\d{1,3})\b", raw)
    if m:
        return m.group(1).zfill(3)
    c = re.sub(r"\D", "", raw)
    return c.zfill(3) if 0 < len(c) <= 3 else ""

def parse_xlsx(path):
    openpyxl = need("openpyxl")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    idx = _map_header(next(rows))
    out = []
    for r in rows:
        out.append({f: (str(r[i]).strip() if i < len(r) and r[i] is not None else "")
                    for f, i in idx.items()})
    return out

def parse_csv(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        rdr = csv.reader(fh)
        idx = _map_header(next(rdr))
        return [{f: (r[i].strip() if i < len(r) else "") for f, i in idx.items()}
                for r in rdr]

def parse_pdf(path):
    pdfplumber = need("pdfplumber")
    out, idx = [], None
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            tbl = pg.extract_table()
            if not tbl:
                continue
            # Only the first page carries a header. Latch the column map there
            # and reuse it — re-deriving per page silently drops every page
            # after the first, which is exactly the bug this comment exists to
            # stop someone reintroducing.
            head = _map_header(tbl[0])
            if head.get("name") is not None and head.get("code") is not None:
                idx = head
                body = tbl[1:]
            else:
                body = tbl
            if not idx:
                continue
            for r in body:
                row = {f: (str(r[i]).strip() if i < len(r) and r[i] is not None else "")
                       for f, i in idx.items()}
                if row.get("name"):
                    out.append(row)
    return out

def parse(only=None):
    all_rows, per_rc = [], {}
    for key, src in RC_SOURCES.items():
        if only and key != only:
            continue
        if not src["url"]:
            continue
        path = WORK / f"{key}.{src['fmt']}"
        if not path.exists():
            print(f"  {key:11s} not downloaded — run --fetch")
            continue
        try:
            rows = {"xlsx": parse_xlsx, "csv": parse_csv,
                    "pdf": parse_pdf}[src["fmt"]](path)
        except Exception as e:
            print(f"  {key:11s} PARSE FAILED: {type(e).__name__}: {e}")
            continue

        kept, codes = [], Counter()
        for r in rows:
            code = _pad(r.get("code"))
            if not code:
                continue
            name = re.sub(r"\s+", " ", r.get("name", "")).strip()
            if not name:
                continue
            codes[code] += 1
            kept.append({
                "rc": key, "rc_name": src["name"],
                "vendor_no": r.get("vendor_no", "").strip(),
                "name": name,
                "service_code": code,
                "service_name": SERVICE_CODES.get(code),
                "sub_code": r.get("sub", "").strip(),
                "rc_category": re.sub(r"\s+", " ", r.get("category", "")).strip(),
                "address": re.sub(r"\s+", " ", r.get("address", "")).strip(),
                "city": re.sub(r"\s+", " ", r.get("city", "")).strip().title(),
                "zip": re.sub(r"\D", "", r.get("zip", ""))[:5],
                "phone": r.get("phone", "").strip(),
                "county": r.get("county", "").strip(),
                "autism_direct": code in AUTISM_DIRECT,
                "autism_support": code in AUTISM_SUPPORT,
            })
        direct = sum(1 for k in kept if k["autism_direct"])
        support = sum(1 for k in kept if k["autism_support"])
        vendors = len({k["vendor_no"] or k["name"] for k in kept})
        per_rc[key] = dict(rows=len(kept), vendors=vendors,
                           autism_direct=direct, autism_support=support)
        all_rows += kept
        print(f"  {key:11s} {len(kept):6,} rows  {vendors:5,} vendors  "
              f"{direct:5,} autism-directed  {support:4,} respite")

    if not all_rows:
        return
    # One file per centre. A 100-page PDF takes minutes, so these are parsed a
    # few at a time; writing a single combined file from a partial run would
    # quietly replace fifteen centres' work with one centre's.
    for key in {r["rc"] for r in all_rows}:
        (WORK / f"parsed_{key}.json").write_text(
            json.dumps([r for r in all_rows if r["rc"] == key], indent=1), encoding="utf-8")
    merged = []
    for f in sorted(WORK.glob("parsed_*.json")):
        merged += json.loads(f.read_text())
    all_rows = merged
    out = WORK.parent / "rc_vendors.json"
    out.write_text(json.dumps(all_rows, indent=1), encoding="utf-8")

    direct_vendors = {r["vendor_no"] or r["name"] for r in all_rows if r["autism_direct"]}
    print(f"\n  {len(all_rows):,} vendor-service rows -> {out}")
    print(f"  {len(direct_vendors):,} distinct vendors billing an autism-directed service code")
    unknown = Counter(r["service_code"] for r in all_rows if not r["service_name"])
    if unknown:
        print(f"  {len(unknown)} service codes not in our verified table "
              f"(most common: {', '.join(c for c, _ in unknown.most_common(8))})")
        print("  Look them up in the DDS crosswalk before treating them as irrelevant.")

def status():
    have = [k for k, v in RC_SOURCES.items() if v["url"]]
    miss = [k for k, v in RC_SOURCES.items() if not v["url"]]
    print(f"  {len(have)}/{len(RC_SOURCES)} regional centres have a located vendor list")
    print(f"  located: {', '.join(sorted(have))}")
    print(f"  missing: {', '.join(sorted(miss))}")
    for k in miss:
        if RC_SOURCES[k].get("note"):
            print(f"    {k}: {RC_SOURCES[k]['note']}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--parse", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--only", metavar="RC")
    a = ap.parse_args()
    if a.fetch:  fetch(a.only)
    elif a.parse: parse(a.only)
    elif a.status: status()
    else: ap.print_help()
