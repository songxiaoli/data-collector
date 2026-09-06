#!/usr/bin/env python3
"""Build the California provider layer from public bulk records.

Run this on your Mac, not through Claude — the sandbox's egress policy blocks
CMS and DCA, and the NPPES file is over a gigabyte anyway.

    python3 autism/scripts/build_providers.py --fetch-taxonomy
    python3 autism/scripts/build_providers.py --fetch-npi
    python3 autism/scripts/build_providers.py --load-dca ~/Downloads/<dca file>.csv
    python3 autism/scripts/build_providers.py --join
    python3 autism/scripts/build_providers.py --crosscheck      # measure coverage against PT
    python3 autism/scripts/build_providers.py --import          # upsert to Supabase

Why these sources and not a directory scrape
--------------------------------------------
NPPES is federal, public domain, and published as bulk files. The California DCA
licensee lists are public records by statute (Information Practices Act 1798.61,
B&P 161) and refresh monthly. Between them you get identity, credential, practice
address and — the thing no commercial directory carries — whether the licence is
actually current. Nobody has to be scraped for any of it.

CMS states plainly that holding an NPI does not mean a provider is licensed or
credentialed, which is exactly why the DCA join matters rather than being optional.
"""
import argparse, csv, gzip, io, json, os, re, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path

def repo_root():
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / ".git").exists():
            return parent
    return p.parent

ROOT   = repo_root()
WORK   = ROOT / "autism" / "data" / "providers"
WORK.mkdir(parents=True, exist_ok=True)
SUPABASE_URL = "https://nhdswigpkiwbgtxugtmw.supabase.co"

NPI_INDEX = "https://download.cms.gov/nppes/NPI_Files.html"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

NUCC_PAGE = "https://www.nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40/csv-mainmenu-57"

# Matched against the NUCC taxonomy DESCRIPTION, not against codes typed from
# memory. Getting a code wrong silently filters out a whole profession.
DISCIPLINE_PATTERNS = {
    "slp":       r"speech.language pathologist",
    "audiology": r"\baudiologist\b",
    "ot":        r"occupational therapist",
    "pt":        r"\bphysical therapist\b",
    "psych":     r"\bpsychologist\b",
    "psychiatry":r"psychiatr",
    "dev-peds":  r"developmental.{0,3}behavioral pediatric|neurodevelopmental",
    "peds":      r"^pediatrics$|pediatrician",
    "neurology": r"neurolog",
    "lmft":      r"marriage.{0,3}(and|&).{0,3}family therapist",
    "lcsw":      r"social worker",
    "counselor": r"counselor|counsellor",
    "bcba":      r"behavior analyst",
    "clinic":    r"clinic/center|community.based|home health|developmental disabilit",
}

def need(mod):
    try:
        return __import__(mod)
    except ImportError:
        sys.exit(f"Missing {mod}. Install it: pip3 install {mod}")

# ------------------------------------------------------------------ taxonomy
def fetch_taxonomy():
    """Pull the NUCC code set so discipline matching is by description."""
    requests = need("requests")
    print("NUCC publishes the taxonomy CSV from a page whose filename carries the")
    print("release date, so this looks it up rather than guessing the URL.")
    html = requests.get(NUCC_PAGE, timeout=60,
                        headers={"User-Agent": UA}).text
    links = re.findall(r'href="([^"]+\.csv)"', html, re.I)
    if not links:
        sys.exit(f"No CSV link found on {NUCC_PAGE} — open it and download by hand,\n"
                 f"then save it as {WORK/'nucc_taxonomy.csv'}")
    url = links[0]
    if url.startswith("/"):
        url = "https://www.nucc.org" + url
    print(f"  downloading {url}")
    out = WORK / "nucc_taxonomy.csv"
    out.write_bytes(requests.get(url, timeout=120).content)
    print(f"  wrote {out}")

def load_taxonomy():
    f = WORK / "nucc_taxonomy.csv"
    if not f.exists():
        sys.exit("Run --fetch-taxonomy first.")
    keep = {}
    with open(f, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("Code") or "").strip()
            desc = " ".join(filter(None, [row.get("Classification"), row.get("Specialization"),
                                          row.get("Grouping")])).lower()
            for disc, pat in DISCIPLINE_PATTERNS.items():
                if re.search(pat, desc):
                    keep.setdefault(code, set()).add(disc)
    print(f"  {len(keep)} taxonomy codes matched our disciplines")
    return keep

# ------------------------------------------------------------------ NPPES
def fetch_npi(explicit_url=None):
    """Stream the monthly full file, keep only the California rows we care about.

    The archive is over a gigabyte zipped. This never holds it in memory: it
    streams the download, reads the CSV out of the zip row by row, and writes a
    slim file of only the columns and rows we use.
    """
    requests = need("requests")
    keep_codes = load_taxonomy()

    url = explicit_url or discover_monthly_url(requests)
    zpath = WORK / "nppes_monthly.zip"
    if zpath.exists():
        print(f"  reusing {zpath.name} ({zpath.stat().st_size/1e9:.2f} GB) — delete it to re-download")
    else:
        print(f"  downloading {url.rsplit('/', 1)[-1]}")
        print("  this is around a gigabyte and will take a while")
        with requests.get(url, stream=True, timeout=3600,
                          headers={"User-Agent": UA}) as r, open(zpath, "wb") as fh:
            r.raise_for_status()
            done = 0
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if done % (100 << 20) < (1 << 20):
                    print(f"    {done/1e9:.2f} GB")

    out = WORK / "npi_ca.csv"
    kept = seen = 0
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist()
                    if n.lower().endswith(".csv")
                    and "header" not in n.lower()
                    and "othername" not in n.lower()
                    and "pl_" not in n.lower()
                    and "endpoint" not in n.lower())
        print(f"  reading {name}")
        cols = ["npi", "npi_type", "name", "credentials", "organization", "address",
                "city", "state", "zip", "phone", "taxonomies", "disciplines",
                "license_no", "license_state"]
        with z.open(name) as raw, open(out, "w", newline="", encoding="utf-8") as fh:
            rdr = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for row in rdr:
                seen += 1
                if seen % 500000 == 0:
                    print(f"    scanned {seen:,}, kept {kept:,}")
                state = (row.get("Provider Business Practice Location Address State Name") or "").strip()
                if state.upper() != "CA":
                    continue

                taxes, discs, lic, licst = [], set(), "", ""
                for i in range(1, 16):
                    code = (row.get(f"Healthcare Provider Taxonomy Code_{i}") or "").strip()
                    if not code:
                        continue
                    if code in keep_codes:
                        taxes.append(code)
                        discs |= keep_codes[code]
                        if not lic:
                            lic   = (row.get(f"Provider License Number_{i}") or "").strip()
                            licst = (row.get(f"Provider License Number State Code_{i}") or "").strip()
                if not discs:
                    continue

                ent = (row.get("Entity Type Code") or "").strip()
                org = (row.get("Provider Organization Name (Legal Business Name)") or "").strip()
                if ent == "2":
                    nm = org
                else:
                    nm = " ".join(filter(None, [
                        (row.get("Provider First Name") or "").strip().title(),
                        (row.get("Provider Last Name (Legal Name)") or "").strip().title()]))

                w.writerow({
                    "npi":          row.get("NPI", ""),
                    "npi_type":     "organization" if ent == "2" else "individual",
                    "name":         nm,
                    "credentials":  (row.get("Provider Credential Text") or "").strip(),
                    "organization": org,
                    "address":      (row.get("Provider First Line Business Practice Location Address") or "").strip(),
                    "city":         (row.get("Provider Business Practice Location Address City Name") or "").strip().title(),
                    "state":        "CA",
                    "zip":          (row.get("Provider Business Practice Location Address Postal Code") or "")[:5],
                    "phone":        (row.get("Provider Business Practice Location Address Telephone Number") or "").strip(),
                    "taxonomies":   ";".join(taxes),
                    "disciplines":  ";".join(sorted(discs)),
                    "license_no":   lic,
                    "license_state": licst,
                })
                kept += 1
    print(f"  scanned {seen:,} NPI records, kept {kept:,} California rows -> {out}")


def discover_monthly_url(requests):
    """Find the current monthly file without guessing at the URL.

    CMS serves a different page to a bare python User-Agent, so present a real
    one. Do not depend on how the href is quoted either — just look for the
    filename pattern anywhere in the page. The monthly file is named for a month
    and a year; the weekly ones carry digit ranges and the word Weekly.
    """
    html = requests.get(NPI_INDEX, timeout=60, headers={"User-Agent": UA}).text
    names = re.findall(r"NPPES_Data_Dissemination_[A-Za-z]+_\d{4}(?:_V\d+)?\.zip", html)
    if not names:
        any_zip = sorted(set(re.findall(r"[A-Za-z0-9_\-]+\.zip", html)))
        print(f"  no monthly file matched on {NPI_INDEX}")
        print(f"  page was {len(html)} characters")
        print(f"  .zip names visible: {any_zip[:12] or 'none — the page may be JS-rendered'}")
        sys.exit("  Open that page in a browser, copy the monthly ZIP link, and pass it:\n"
                 "    python3 autism/scripts/build_providers.py --fetch-npi --npi-url <url>")
    MONTHS = ["january", "february", "march", "april", "may", "june",
              "july", "august", "september", "october", "november", "december"]
    def when(n):
        m = re.search(r"_([A-Za-z]+)_(\d{4})", n)
        month = m.group(1).lower()
        return (int(m.group(2)), MONTHS.index(month) if month in MONTHS else 0)
    newest = sorted(set(names), key=when)[-1]
    print(f"  monthly file: {newest}")
    return "https://download.cms.gov/nppes/" + newest


# ------------------------------------------------------------------ DCA
def load_dca(path):
    """Normalise a DCA licensee file.

    DCA publishes these through a Box folder that refreshes at the start of each
    month, so it cannot be fetched by URL — download it once and point here.
    """
    src = Path(path).expanduser()
    if not src.exists(): sys.exit(f"No such file: {src}")
    out = WORK / "dca_licenses.csv"
    n = 0
    with open(src, newline="", encoding="utf-8-sig", errors="replace") as fh, \
         open(out, "w", newline="", encoding="utf-8") as ofh:
        rdr = csv.DictReader(fh)
        want = {"license_no":  ["license number","license_number","licensenumber","lic_number"],
                "board":       ["board name","board","boardname"],
                "status":      ["license status","status","licensestatus"],
                "expires":     ["expiration date","expiration_date","expdate"],
                "last":        ["last name","lastname"],
                "first":       ["first name","firstname"],
                "business":    ["business name","businessname","dba"],
                "city":        ["city"], "zip": ["zip","zip code","zipcode"], "county": ["county"]}
        low = {c.lower().strip(): c for c in (rdr.fieldnames or [])}
        pick = {k: next((low[a] for a in alts if a in low), None) for k, alts in want.items()}
        missing = [k for k in ("license_no","status") if not pick[k]]
        if missing:
            sys.exit(f"Could not find columns {missing} in {src.name}.\n"
                     f"Columns present: {rdr.fieldnames}\n"
                     f"Edit the `want` map above to match this board's layout.")
        w = csv.DictWriter(ofh, fieldnames=list(want)); w.writeheader()
        for row in rdr:
            rec = {k: (row.get(c) or "").strip() if c else "" for k, c in pick.items()}
            if not rec["license_no"]: continue
            w.writerow(rec); n += 1
    print(f"  normalised {n:,} licence rows -> {out}")

# ------------------------------------------------------------------ join
def norm_lic(s): return re.sub(r"[^A-Z0-9]", "", (s or "").upper())
def norm_name(s): return re.sub(r"[^a-z ]", "", (s or "").lower()).strip()

def join():
    npi_f, dca_f = WORK/"npi_ca.csv", WORK/"dca_licenses.csv"
    if not npi_f.exists(): sys.exit("Run --fetch-npi first.")
    dca = {}
    if dca_f.exists():
        with open(dca_f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                dca[norm_lic(r["license_no"])] = r
        print(f"  {len(dca):,} licence records available for matching")
    else:
        print("  no DCA file — licence status will be blank. Run --load-dca to fix.")

    out, matched = [], 0
    with open(npi_f, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            lic = dca.get(norm_lic(r["license_no"])) if r["license_no"] else None
            if lic: matched += 1
            slug = "prov-" + (r["npi"] or norm_name(r["name"]).replace(" ", "-"))[:60]
            out.append({
                "slug": slug, "npi": r["npi"] or None,
                "npi_type": r["npi_type"], "name": r["name"],
                "credentials": r["credentials"] or None,
                "organization": r["organization"] or None,
                "address": r["address"] or None, "city": r["city"] or None,
                "county": (lic or {}).get("county") or None,
                "state": "CA", "zip": r["zip"] or None, "phone": r["phone"] or None,
                "taxonomies": [t for t in r["taxonomies"].split(";") if t],
                "disciplines": [d for d in r["disciplines"].split(";") if d],
                "license_no": r["license_no"] or None,
                "license_board": (lic or {}).get("board") or None,
                "license_status": (lic or {}).get("status") or None,
                # everything operational stays null until a human confirms it
                "listing_status": "listed",
                "confidence": "high" if lic else "medium",
                "sources": [{"field": "identity", "source": "CMS NPPES monthly file"}]
                           + ([{"field": "license_status", "source": "CA DCA licensee file"}] if lic else []),
            })
    (WORK/"providers.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"  {len(out):,} providers, {matched:,} with a matched licence "
          f"({matched/max(1,len(out))*100:.0f}%) -> {WORK/'providers.json'}")
    print("  disciplines:", dict(Counter(d for p in out for d in p["disciplines"]).most_common(10)))

# ------------------------------------------------------------------ crosscheck
def crosscheck():
    """Measure coverage against the therapists table already in Supabase.

    This does NOT publish anything from that source. It uses two independent
    samples of the same population — licence registration on one side, a paid
    commercial listing on the other — to estimate how much of the population we
    are actually holding, and to triage which rows a human should check.

    Lincoln-Petersen:  N ≈ (A × B) / overlap
    The estimate runs conservative, because a commercial directory only contains
    people who chose to list there.
    """
    key = load_key()
    if not key: sys.exit("No SUPABASE_SERVICE_KEY in the environment or .env")
    from supabase import create_client
    c = create_client(SUPABASE_URL, key)
    pf = WORK / "providers.json"
    if not pf.exists(): sys.exit("Run --join first.")
    A = json.loads(pf.read_text())

    rows, page = [], 0
    while True:
        r = c.table("therapists").select("name,city,zip,credentials").eq("state","CA")\
             .range(page*1000, page*1000+999).execute()
        rows += r.data
        if len(r.data) < 1000: break
        page += 1
    print(f"  A (NPI+DCA): {len(A):,}    B (existing directory rows): {len(rows):,}")

    keyA = {(norm_name(p["name"]), (p.get("zip") or "")[:5]) for p in A}
    keyB = {(norm_name(r.get("name")), (r.get("zip") or "")[:5]) for r in rows}
    overlap = keyA & keyB
    print(f"  overlap on (name, ZIP): {len(overlap):,}")
    if overlap:
        est = len(keyA) * len(keyB) / len(overlap)
        cov = len(keyA | keyB) / est * 100
        print(f"\n  estimated population ≈ {est:,.0f}")
        print(f"  we currently hold     ≈ {cov:.0f}%")
        print(f"  still missing         ≈ {est - len(keyA|keyB):,.0f}")
    else:
        print("\n  no overlap — the two sources are not sampling the same population,")
        print("  so no estimate is possible. Check the name normalisation first.")

    onlyB = [r for r in rows if (norm_name(r.get("name")), (r.get("zip") or "")[:5]) not in keyA]
    (WORK/"triage_only_in_directory.json").write_text(json.dumps(onlyB[:2000], indent=1), encoding="utf-8")
    print(f"\n  {len(onlyB):,} rows appear in the directory but not in NPI+DCA.")
    print("  Some are unlicensed or out-of-state; some are ours to find. First 2000")
    print(f"  written to {WORK/'triage_only_in_directory.json'} — that is the human-review queue,")
    print("  and it is a far better use of review time than sampling at random.")

# ------------------------------------------------------------------ import
def load_key():
    k = os.environ.get("SUPABASE_SERVICE_KEY")
    if k: return k.strip()
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("SUPABASE_SERVICE_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None

def do_import():
    key = load_key()
    if not key: sys.exit("No SUPABASE_SERVICE_KEY in the environment or .env")
    from supabase import create_client
    c = create_client(SUPABASE_URL, key)
    rows = json.loads((WORK/"providers.json").read_text())
    print(f"  {len(rows):,} rows to upsert")
    for i in range(0, len(rows), 100):
        c.table("providers").upsert(rows[i:i+100], on_conflict="slug").execute()
        if (i//100) % 10 == 0: print(f"    {min(i+100,len(rows)):,}/{len(rows):,}")
    print("  done")

# ------------------------------------------------------------------ main
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch-taxonomy", action="store_true")
    ap.add_argument("--fetch-npi", action="store_true")
    ap.add_argument("--npi-url", metavar="URL",
                    help="skip discovery and download this monthly ZIP directly")
    ap.add_argument("--load-dca", metavar="CSV")
    ap.add_argument("--join", action="store_true")
    ap.add_argument("--crosscheck", action="store_true")
    ap.add_argument("--import", dest="do_import", action="store_true")
    a = ap.parse_args()
    if a.fetch_taxonomy: fetch_taxonomy()
    if a.fetch_npi:      fetch_npi(a.npi_url)
    if a.load_dca:       load_dca(a.load_dca)
    if a.join:           join()
    if a.crosscheck:     crosscheck()
    if a.do_import:      do_import()
    if not any(vars(a).values()): ap.print_help()
