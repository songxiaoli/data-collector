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

# ------------------------------------------------------------------ relevance
# Autism relevance, in three tiers.
#
# The first cut of this file matched taxonomy *descriptions* with regexes. That
# was wrong in a way worth recording: r"neurolog" matched Neurological Surgery,
# r"clinic/center" matched dialysis and dental clinics, and the result was
# 396,156 California rows — essentially every licensed provider in the state.
# A directory of everyone is a directory of no one.
#
# So relevance is now an explicit code table, and every code below is checked
# against the NUCC file at load time. An unknown code is a hard error, never a
# silent omission — the failure mode of the old approach was that a whole
# profession could vanish and nothing would say so.
#
# Tier 1 — the taxonomy itself names developmental disability, autism, or early
#   intervention work. Relevance needs no further evidence.
# Tier 2 — a discipline families are routinely referred to for autism, but the
#   taxonomy says nothing about autism. Listable, labelled honestly.
# Tier 3 — general mental health and general clinics. Held from publication
#   until something else says they actually work with autistic clients.

TIER1 = {
    "2080P0006X": "dev-peds",      # Pediatrics / Developmental - Behavioral Pediatrics
    "2080P0008X": "dev-peds",      # Pediatrics / Neurodevelopmental Disabilities
    "2084P0005X": "dev-peds",      # Psychiatry & Neurology / Neurodevelopmental Disabilities
    "103TM1800X": "psych-idd",     # Psychologist / Intellectual & Developmental Disabilities
    "222Q00000X": "dev-therapy",   # Developmental Therapist
    "252Y00000X": "early-int",     # Early Intervention Provider Agency
    "251C00000X": "day-program",   # Day Training, Developmentally Disabled Services
    "261QD1600X": "clinic-dd",     # Clinic/Center / Developmental Disabilities
    "385HR2060X": "respite",       # Respite Care / IDD, Child
    "315P00000X": "residential",   # Intermediate Care Facility, Intellectual Disabilities
    "320600000X": "residential",   # Residential Treatment Facility, I/DD
    "320900000X": "residential",   # Community Based Residential Treatment, I/DD
    # Behaviour-analytic practice is community-contested, not excluded. It is
    # tier 1 because in California it is funded through the regional centres and
    # the insurance mandate specifically for autism — relevance is not in doubt.
    # The stance flag, not the tier, is what carries the criticism.
    "103K00000X": "bcba",          # Behavior Analyst (BCBA)
}

TIER2 = {
    "235Z00000X": "slp",           # Speech-Language Pathologist
    "2355S0801X": "slp",           # Specialist/Technologist / Speech-Language Assistant
    "261QH0700X": "clinic-speech", # Clinic/Center / Hearing and Speech
    "225X00000X": "ot",            # Occupational Therapist
    "225XP0200X": "ot",            # OT / Pediatrics
    "225XF0002X": "ot",            # OT / Feeding, Eating & Swallowing
    "225XM0800X": "ot",            # OT / Mental Health
    "224Z00000X": "ot",            # Occupational Therapy Assistant
    "224ZF0002X": "ot",            # OTA / Feeding, Eating & Swallowing
    "2251P0200X": "pt-peds",       # Physical Therapist / Pediatrics  (general PT excluded)
    "231H00000X": "audiology",     # Audiologist
    "231HA2400X": "audiology",     # Audiologist / Assistive Technology Practitioner
    "231HA2500X": "audiology",     # Audiologist / Assistive Technology Supplier
    "103TC2200X": "psych-child",   # Psychologist / Clinical Child & Adolescent
    "103TS0200X": "psych-school",  # Psychologist / School
    "103G00000X": "neuropsych",    # Clinical Neuropsychologist
    "103GC0700X": "neuropsych",    # Clinical Neuropsychologist / Clinical
    "2084P0804X": "child-psychiatry",   # Psychiatry & Neurology / Child & Adolescent Psychiatry
    "2084N0402X": "child-neurology",    # Neurology w/ Special Qualifications in Child Neurology
    "163WP0807X": "child-psych-np",     # RN / Psychiatric-Mental Health, Child & Adolescent
    "364SP0807X": "child-psych-cns",    # CNS / Psychiatric-Mental Health, Child & Adolescent
    "364SP0810X": "child-psych-cns",    # CNS / Psychiatric-Mental Health, Child & Family
    "261QM0855X": "clinic-child-mh",    # Clinic/Center / Adolescent and Children Mental Health
    "225CA2400X": "assistive-tech",     # Rehab Counselor / Assistive Technology Practitioner
    "225CA2500X": "assistive-tech",     # Rehab Counselor / Assistive Technology Supplier
    "385HR2055X": "respite",            # Respite Care / Mental Illness, Child
}

TIER3 = {
    "103T00000X": "psych",
    "103TC0700X": "psych",
    "103TB0200X": "psych",
    "103TF0000X": "psych",
    "103TP2700X": "psych",
    "103TH0100X": "psych",
    "106H00000X": "lmft",
    "1041C0700X": "lcsw",
    "104100000X": "lcsw",
    "101YM0800X": "counselor",
    "101Y00000X": "counselor",
    "101YP2500X": "counselor",
    "2084P0800X": "psychiatry",
    "251S00000X": "clinic-behavioral",
    "261QM0801X": "clinic-mh",
    "208000000X": "peds",
}

# Behaviour technicians and assistant behaviour analysts are deliberately absent,
# and this is the entry most likely to look like an oversight, so: California has
# 177,938 NPIs under Behavior Technician (106S00000X) and 3,412 under Assistant
# Behavior Analyst (106E00000X), against 23,806 BCBAs. Including them made tier 1
# 87% behaviour technicians. An RBT is an entry-level paraprofessional who works
# under a BCBA's supervision and is assigned by an agency — a family hires the
# agency, never the technician. Listing them would multiply the directory tenfold
# with people nobody can choose, and bury the 314 developmental-behavioural
# paediatricians in the state under them. They are real autism workers; they are
# not a thing a parent picks from a list.
#
# Deliberately NOT here, and why — so nobody re-adds them by pattern later:
# general Physical Therapist (225100000X), Addiction Counselor (101YA0400X),
# Hospice (251G00000X), Home Health (251E00000X), dental, dialysis, ambulatory
# surgical, Neurological Surgery (207T00000X), general Neurology (2084N0400X),
# Psychiatric Technician (167G00000X), substance-use facilities. Each of these
# was pulled in by the old regexes and none of them belongs in an autism
# directory.

TIERS = [("1", TIER1), ("2", TIER2), ("3", TIER3)]


def load_taxonomy():
    """Return {code: (tier, discipline)}, verifying every code against NUCC.

    Codes are declared explicitly above rather than matched by regex, so the
    one thing that can go wrong is a typo or a retired code. That is exactly
    what this checks, loudly, before anything downstream depends on it.
    """
    f = WORK / "nucc_taxonomy.csv"
    if not f.exists():
        sys.exit("Run --fetch-taxonomy first.")
    known = {}
    with open(f, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("Code") or "").strip()
            if code:
                known[code] = "{} / {}".format(
                    (row.get("Classification") or "").strip(),
                    (row.get("Specialization") or "").strip() or "-")

    keep, missing = {}, []
    for tier, table in TIERS:
        for code, disc in table.items():
            if code not in known:
                missing.append((tier, code, disc))
                continue
            keep[code] = (tier, disc)
    if missing:
        for tier, code, disc in missing:
            print(f"  !! tier {tier} code {code} ({disc}) is not in this NUCC release")
        sys.exit("  Refusing to run on a code table that no longer matches NUCC.\n"
                 "  Re-run --fetch-taxonomy, then look each missing code up before editing.")

    by_tier = Counter(t for t, _ in keep.values())
    print(f"  {len(keep)} taxonomy codes verified against NUCC "
          f"(tier 1: {by_tier['1']}, tier 2: {by_tier['2']}, tier 3: {by_tier['3']})")
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

    # Discovery is deliberately after this check: with the archive already on
    # disk there is nothing to look up, and reaching for the network anyway
    # means a re-filter fails on machines that cannot reach CMS.
    zpath = WORK / "nppes_monthly.zip"
    if zpath.exists():
        print(f"  reusing {zpath.name} ({zpath.stat().st_size/1e9:.2f} GB) — delete it to re-download")
    else:
        url = explicit_url or discover_monthly_url(requests)
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
    tier_counts = Counter()
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
                "tier", "license_no", "license_state"]
        with z.open(name) as raw, open(out, "w", newline="", encoding="utf-8") as fh:
            src = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            rdr = csv.reader(src)
            w   = csv.writer(fh)
            w.writerow(cols)

            # This used to be a csv.DictReader, and it could not finish. The file
            # is 330 columns wide and about ten million rows, so DictReader built
            # ten million 330-key dictionaries — minutes of allocation for the
            # dozen or so columns we actually read. csv.reader yields a plain
            # list and we index it by position instead.
            #
            # Position indexing is only safe because the positions come from this
            # file's own header, resolved below. NPPES has appended and reordered
            # columns between releases, so a hardcoded index would quietly read
            # the wrong field — the exact failure mode the taxonomy table above
            # was rewritten to avoid. col() therefore dies loudly on a name it
            # cannot find rather than defaulting to anything.
            head  = next(rdr)
            ncols = len(head)
            pos   = {h.strip(): i for i, h in enumerate(head)}

            def col(label):
                if label not in pos:
                    sys.exit(f"  {name} has no column {label!r}.\n"
                             f"  NPPES changed the layout — read the header and fix the\n"
                             f"  names below before trusting anything this writes.")
                return pos[label]

            i_npi   = col("NPI")
            i_ent   = col("Entity Type Code")
            i_org   = col("Provider Organization Name (Legal Business Name)")
            i_first = col("Provider First Name")
            i_last  = col("Provider Last Name (Legal Name)")
            i_cred  = col("Provider Credential Text")
            i_addr  = col("Provider First Line Business Practice Location Address")
            i_city  = col("Provider Business Practice Location Address City Name")
            i_state = col("Provider Business Practice Location Address State Name")
            i_zip   = col("Provider Business Practice Location Address Postal Code")
            i_phone = col("Provider Business Practice Location Address Telephone Number")
            # The taxonomy columns repeat fifteen times as a code / licence /
            # licence-state triple, so resolve them as triples: the licence we
            # keep has to be the one belonging to the code that matched, not
            # whichever licence happened to be first on the row.
            slots = [(col(f"Healthcare Provider Taxonomy Code_{i}"),
                      col(f"Provider License Number_{i}"),
                      col(f"Provider License Number State Code_{i}"))
                     for i in range(1, 16)]

            for r in rdr:
                seen += 1
                if seen % 500000 == 0:
                    print(f"    scanned {seen:,}, kept {kept:,}", flush=True)
                # A short row would raise on a positional read where DictReader
                # quietly handed back None. Pad it so malformed rows behave the
                # way they always did — empty fields, filtered out downstream.
                if len(r) < ncols:
                    r = r + [""] * (ncols - len(r))
                # State is checked before anything else touches the row: roughly
                # nine rows in ten are not California, and dropping them here is
                # most of what makes the scan fit in one pass.
                if r[i_state].strip().upper() != "CA":
                    continue

                taxes, discs, tiers, lic, licst = [], set(), set(), "", ""
                for i_code, i_lic, i_licst in slots:
                    code = r[i_code].strip()
                    if not code or code not in keep_codes:
                        continue
                    tier, disc = keep_codes[code]
                    if code not in taxes:      # NPPES repeats the same code across slots
                        taxes.append(code)
                    discs.add(disc)
                    tiers.add(tier)
                    if not lic:
                        lic   = r[i_lic].strip()
                        licst = r[i_licst].strip()
                if not discs:
                    continue
                # A provider is placed at their strongest claim to relevance: a
                # psychologist who also holds the I/DD specialisation is tier 1.
                best_tier = min(tiers)

                ent = r[i_ent].strip()
                org = r[i_org].strip()
                if ent == "2":
                    nm = org
                else:
                    nm = " ".join(filter(None, [r[i_first].strip().title(),
                                                r[i_last].strip().title()]))

                # Written positionally in the same order as `cols` above.
                w.writerow([
                    r[i_npi],
                    "organization" if ent == "2" else "individual",
                    nm,
                    r[i_cred].strip(),
                    org,
                    r[i_addr].strip(),
                    r[i_city].strip().title(),
                    "CA",
                    r[i_zip][:5],
                    r[i_phone].strip(),
                    ";".join(taxes),
                    ";".join(sorted(discs)),
                    best_tier,
                    lic,
                    licst,
                ])
                kept += 1
                tier_counts[best_tier] += 1
    print(f"  scanned {seen:,} NPI records, kept {kept:,} California rows -> {out}")
    for t in ("1", "2", "3"):
        print(f"    tier {t}: {tier_counts[t]:,}")
    print("  tier 3 is held from publication until an autism signal corroborates it.")


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
            tier = int(r.get("tier") or 3)
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
                "relevance_tier": tier,
                # Tier 3 is general mental health with no autism signal at all.
                # It is carried so a regional-centre match can promote it later,
                # but it does not go out: a parent searching an autism directory
                # and finding every therapist in the state has learned nothing.
                "publish_status": None if tier <= 2 else "hold-needs-autism-signal",
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
    tiers = Counter(p["relevance_tier"] for p in out)
    held = sum(1 for p in out if p["publish_status"])
    print(f"  tiers: 1={tiers[1]:,}  2={tiers[2]:,}  3={tiers[3]:,}")
    print(f"  {len(out)-held:,} publishable, {held:,} held pending an autism signal")

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
        c.table("autism_providers").upsert(rows[i:i+100], on_conflict="slug").execute()
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
