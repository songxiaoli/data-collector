"""
parse_wordlayout.py -- standalone parsers for four California regional-centre
vendor directories whose PDFs defeat pdfplumber's ``extract_table()``.

    parse(key, path) -> list[dict]      key in {"sdrc", "sgprc", "westside", "ggrc"}

Every returned row is a dict with the keys:

    rc, vendor_no, name, category, address, city, zip, phone, email

A key is OMITTED only when the source directory genuinely has no such column
(see PER-FILE NOTES below).  A key that exists in the source but is blank on a
particular row is present with value ``None`` -- nothing is ever guessed or
back-filled from another row, with the single documented exception of SGPRC's
category, which the source itself prints once per group (see below).


-----------------------------------------------------------------------------
WHY NOT extract_table()
-----------------------------------------------------------------------------
Three of the four PDFs have no ruling lines and no cell boxes; they are plain
text laid out in columns by absolute position.  ``extract_table()`` returns
nothing at all for them.  ``extract_text()`` is also unusable, because adjacent
columns touch: SDRC prints "7603527440EL CENTRO" (phone abutting city) and,
worse, its long category strings physically overlap the provider-name column,
so pdfplumber's word grouper interleaves characters from the two columns and
emits nonsense like "FAAC IPLLITAYCE" (which is "FACILITY" + "AC PLACE"
interleaved by x).

The fix used throughout is TEXT-RUN RECONSTRUCTION.  ``page.chars`` is in PDF
content-stream order, and every table cell is emitted as one contiguous drawing
run, so within a run each character's x0 equals the previous character's x1.
Walking the chars in document order and cutting wherever that abutment breaks
rebuilds the original cell strings exactly -- even when two cells overlap in x.
Only after the runs are rebuilt is x-position used, and then only to decide
which COLUMN a run belongs to (by the run's starting x, never by its extent).


-----------------------------------------------------------------------------
HOW THE COLUMN MAPS WERE DERIVED  (no hand-typed magic numbers)
-----------------------------------------------------------------------------
For each file the column boundaries below were derived by measurement, not
guessed, using the procedure in ``derive_column_map()`` at the bottom of this
module (run it to re-derive them against a new edition of any of these PDFs):

  1. Rebuild the text runs for every data line on a sample of pages.
  2. Histogram the runs' STARTING x co-ordinates.  Left-aligned columns show up
     as needle-sharp modes recurring once per row (e.g. SDRC: 52.07, 164.39,
     384.71, 513.83, 669.35, each occurring exactly once per data row).  A
     right-aligned column (SDRC's and SGPRC's phone) shows the same behaviour in
     the histogram of run END x instead.
  3. Place each boundary in the middle of the empty x-interval between one
     column's observed extent and the next column's observed start.

The boundaries are then LATCHED AS MODULE CONSTANTS and reused for every page of
the document.  This is deliberate and load-bearing: in these files only page 1
carries a header (SDRC) or the per-page geometry drifts (Westside), so a column
map re-derived per page silently mis-assigns or drops rows on pages that lack a
header or that happen to hold few rows.  An earlier version of this pipeline
dropped ~95% of SDRC's rows for exactly that reason.  The maps here are computed
once from the whole document and never re-derived mid-run.

Because starts are classified (not extents), a boundary only has to fall in the
gap between two columns' START positions.  Those gaps are wide -- e.g. SDRC's
name column starts at 164.39 and its vendor-number column at 384.71, so the
boundary at 370 is safe even though long provider names physically run to x=410
and overlap the vendor-number column.

Dependencies: pdfplumber only.
"""

from __future__ import annotations

import collections
import json
import re
import sys

import pdfplumber

# --------------------------------------------------------------------------
# Output schema
# --------------------------------------------------------------------------

FIELDS = ("rc", "vendor_no", "name", "category", "address", "city", "zip",
          "phone", "email")

# Which of the nine keys each source actually has a column for.  Keys not
# listed are omitted from that file's rows entirely.
PRESENT = {
    # SDRC: Description | Provider Name | Resource # | Phone | City,State | Zip
    "sdrc":     ("rc", "vendor_no", "name", "category", "city", "zip", "phone"),
    # SGPRC: Description | Resource Name | Phone Number | Email
    "sgprc":    ("rc", "name", "category", "phone", "email"),
    # Westside: <CATEGORY heading> then Name | Address | City | Email
    "westside": ("rc", "name", "category", "address", "city", "email"),
    # GGRC: Vendor # | Srv Category | Vendor Name | Address | City | Zip | Phone
    "ggrc":     ("rc", "vendor_no", "name", "category", "address", "city",
                 "zip", "phone"),
}


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------

def _norm(s):
    """Collapse runs of whitespace; return None for an empty result."""
    if s is None:
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s or None


_CITY_SMALL = {"of", "del", "de", "la", "las", "los", "el", "the", "and"}


def _title_city(s):
    """Title-case a city name, keeping short connectives lower except first."""
    s = _norm(s)
    if not s:
        return None
    parts = s.lower().split(" ")
    out = []
    for i, p in enumerate(parts):
        if i and p in _CITY_SMALL:
            out.append(p)
        elif "'" in p:                      # O'Neill, Coeur d'Alene
            a, b = p.split("'", 1)
            out.append(a.capitalize() + "'" + b.capitalize())
        else:
            out.append(p.capitalize())
    return " ".join(out)


def _phone(s):
    """Keep the phone exactly as printed.  '0' is this data's null placeholder
    (SDRC prints a literal 0 where it holds no number) -> None, not '0'."""
    s = _norm(s)
    if not s or s.strip("0 ()-") == "" and set(s) <= set("0 ()-"):
        return None
    return s


def _lines(page, ytop, ybot, tol=1.5):
    """Group a page's characters into visual lines.

    Characters are kept in PDF CONTENT-STREAM ORDER inside each line -- that
    ordering is what makes run reconstruction work.  Used by the SDRC and SGPRC
    parsers, whose rows sit on a single baseline; Westside needs the richer
    ``_logical_rows`` because its cells straddle baselines.
    """
    buckets = []                                    # [(top, [chars])]
    for c in page.chars:
        t = c["top"]
        if not (ytop <= t <= ybot):
            continue
        for b in buckets:
            if abs(b[0] - t) <= tol:
                b[1].append(c)
                break
        else:
            buckets.append((t, [c]))
    buckets.sort(key=lambda b: b[0])
    return buckets


def _runs(chars, gap=0.6):
    """Rebuild original text runs (= table cells) from characters.

    Walks ``chars`` in document order and starts a new run whenever the next
    character does not continue from the previous one's right edge.  ``abs()``
    is used so a backwards jump (the renderer moving to a cell further left)
    also cuts.  Returns [(x0, x1, text)] sorted left-to-right.
    """
    runs, cur = [], []
    for c in chars:
        if cur and abs(c["x0"] - cur[-1]["x1"]) > gap:
            runs.append(cur)
            cur = []
        cur.append(c)
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        txt = "".join(c["text"] for c in r)
        if txt.strip():
            out.append((r[0]["x0"], r[-1]["x1"], txt))
    out.sort(key=lambda t: t[0])
    return out


def _logical_rows(page, ytop, ybot, phys_tol, merge_tol, gap):
    """Group a page into logical table rows, run-by-run.

    Runs are rebuilt WITHIN each physical baseline first and only then are
    nearby baselines merged into one logical row.  Doing it in the other order
    is a trap: when a record's name sits on one baseline and its address 1pt
    below, pooling the characters first puts the name's last character and the
    address's first character 0.2pt apart, so run reconstruction fuses two
    different cells into one run and the address ends up inside the name.

    Returns [(top, chars, runs)] ordered top to bottom, runs sorted by x.
    """
    phys = []
    for c in page.chars:
        t = c["top"]
        if not (ytop <= t <= ybot):
            continue
        for b in phys:
            if abs(b[0] - t) <= phys_tol:
                b[1].append(c)
                break
        else:
            phys.append((t, [c]))
    phys.sort(key=lambda b: b[0])

    rows = []
    for top, chars in phys:
        runs = _runs(chars, gap)
        if rows and abs(rows[-1][0] - top) <= merge_tol:
            rows[-1][1].extend(chars)
            rows[-1][2].extend(runs)
        else:
            rows.append([top, list(chars), runs])
    for r in rows:
        r[2].sort(key=lambda t: t[0])
    return rows


def _pages(pdf, only, skip_first=False):
    """Iterate the pages to parse.

    ``only`` is an optional collection of 0-based page indices, used by the
    verification harness to re-parse a single page in isolation; passing None
    (the normal case) parses the whole document.
    """
    for i, page in enumerate(pdf.pages):
        if skip_first and i == 0:
            continue
        if only is not None and i not in only:
            continue
        yield i, page


def _bucket(x, bounds):
    """Index of the column whose range contains x.  ``bounds`` is the list of
    upper boundaries; the last column is everything above the last boundary."""
    for i, b in enumerate(bounds):
        if x < b:
            return i
    return len(bounds)


def _row(key, **kw):
    """Build an output row restricted to the columns this source really has."""
    r = {"rc": key.upper()}
    for f in FIELDS:
        if f == "rc" or f not in PRESENT[key]:
            continue
        r[f] = kw.get(f)
    return {f: r[f] for f in FIELDS if f in r}


# ==========================================================================
# 1. SDRC -- San Diego Regional Center (93 pages)
# ==========================================================================
#
# Layout: Description | Provider Name | Resource # | Phone | City,State | Zip
# Header appears on page 1 ONLY; pages 2-93 are bare data.  Every data line is
# exactly six runs.  There are no wrapped/continuation rows anywhere.
#
# Measured column geometry (see derive_column_map): run starts occur at exactly
#   52.07 (category)  164.39 (name)  384.71 (resource #)  513.83 (city,state)
#   669.35 (zip)
# once per data row, and the phone is RIGHT-aligned with a constant right edge
# at x=510.97 (its start floats between 467.76 and 506.64 with the digit count).
# The boundaries below sit in the empty intervals between those starts.  The
# tightest real gap in the whole page is phone-end 510.97 -> city-start 513.83,
# which is why extract_text() glues "7603527440EL CENTRO" together and why the
# run reconstruction (a 2.86pt non-abutment) is what separates them.
SDRC_BOUNDS = [370.0, 440.0, 512.0, 660.0]          # after cat|name merge, see below
SDRC_CAT_NAME_BOUND = 150.0

# NOTE on the provider-name cell.  It holds a name left-justified in a field of
# minimum width 25, optionally followed by a second unlabelled segment (a
# staffing ratio like "1:6 AC", or a legal entity, e.g.
# "ALVARADO PARKWAY INSTITUT" + "BH SD OPCO, LLC").  The two are drawn as ONE
# continuous string -- measured character by character, the deltas across the
# junction are sub-0.1pt kerning noise, identical to those inside a word -- so
# there is NO geometric way to find the boundary.  Splitting at index 25 was
# tried and rejected: it cuts genuine long names mid-word
# ("TERI CRIMSON PROJECT IMPACT" -> "IMPA"/"CT").  The whole cell is therefore
# emitted verbatim (whitespace-normalised).  About 15% of cells exceed the
# 25-char pad width; in an unknown subset of those the source has concatenated
# two fields with no delimiter.  That defect is in the PDF, and it is left
# visible rather than papered over with a guess.
#
# y-band: the "Service Provider List" title sits at top=25.4 on every page.
# Page 1 additionally carries the column header at top=57.6 with data from 71.6;
# pages 2-93 have NO header and their first data row starts at top=56.8.  YTOP
# must therefore be below 56.8, not below 65 -- an earlier cut at 65 silently
# dropped the first row of all 92 header-less pages.  The page-1 header is
# removed by content instead.
SDRC_YTOP = 45.0
SDRC_YBOT = 620.0


def parse_sdrc(path, pages=None):
    rows = []
    with pdfplumber.open(path) as pdf:
        for _i, page in _pages(pdf, pages):
            for _top, chars in _lines(page, SDRC_YTOP, SDRC_YBOT, tol=1.5):
                runs = _runs(chars, gap=0.6)
                if not runs:
                    continue

                cells = {}
                for x0, _x1, txt in runs:
                    if x0 < SDRC_CAT_NAME_BOUND:
                        cells.setdefault("cat", "")
                        cells["cat"] += txt
                    else:
                        i = _bucket(x0, SDRC_BOUNDS)
                        k = ("name", "vno", "phone", "city", "zip")[i]
                        cells[k] = cells.get(k, "") + txt

                # A real data row always carries a resource number and a name.
                if "vno" not in cells or "name" not in cells:
                    continue
                # Skip the page-1 header line.
                if cells.get("cat", "").strip().startswith("Description"):
                    continue

                # City cell is "SAN DIEGO              CA": fixed-width city
                # then the 2-letter state.  Split the trailing state token off.
                # A few source rows have the state typed into the city field too
                # ("MURRIETA CA            CA"), so a trailing " CA" is stripped
                # repeatedly.
                city = _norm(cells.get("city")) or ""
                m = re.match(r"^(.*?)\s+([A-Z]{2})$", city)
                if m:
                    city = m.group(1)
                while city.upper().endswith(" CA"):
                    city = city[:-3].strip()

                rows.append(_row(
                    "sdrc",
                    vendor_no=_norm(cells.get("vno")),
                    name=_norm(cells["name"]),
                    category=_norm(cells.get("cat")),
                    city=_title_city(city),
                    zip=_norm(cells.get("zip")),
                    phone=_phone(cells.get("phone")),
                ))
    return rows


# ==========================================================================
# 2. SGPRC -- San Gabriel/Pomona Regional Center (47 pages)
# ==========================================================================
#
# Layout: Description | Resource Name | Phone Number | Email
# This is a fixed-pitch mainframe-style report: the WHOLE line is emitted as a
# single text run padded with spaces, so run reconstruction gives one run per
# line and the split has to be done on x per character instead.
#
# Measured geometry: word starts pile up at exactly 215.5 (name, 1086 hits),
# 359.8 (phone, 1071) and 434.7 (e-mail, 944) over a 24-page sample; the
# description starts at 23.0 in a fixed 36-character field that therefore always
# ends before 215.5.  The ink-density profile over data lines is exactly zero
# across 350-358 (name|phone) and effectively zero at 424-434 (phone|email),
# so the boundaries sit at 215.0 / 354.0 / 430.0.
SGPRC_BOUNDS = [215.0, 354.0, 430.0]                # cat | name | phone | email
SGPRC_YTOP = 90.0                                   # below the repeated header
SGPRC_YBOT = 535.0                                  # above the footer line


def parse_sgprc(path, pages=None):
    rows = []
    # The source prints the Description ONCE at the top of each group of
    # providers and leaves it blank on the following rows -- that blank means
    # "same as above" in the document itself, so carrying it forward is
    # reading the layout, not inventing data.  It carries across page breaks.
    current_cat = None
    with pdfplumber.open(path) as pdf:
        for _i, page in _pages(pdf, pages):
            for _top, chars in _lines(page, SGPRC_YTOP, SGPRC_YBOT, tol=1.5):
                cells = ["", "", "", ""]
                for c in chars:
                    cells[_bucket(c["x0"], SGPRC_BOUNDS)] += c["text"]
                cat, name, phone, email = (_norm(x) for x in cells)

                # Repeated per-page header ("Description Resource Phone Email"
                # / "Name Number") and the page footer.
                if cat and cat.startswith("Description"):
                    continue
                if name in ("Name", "Resource Name") or (
                        name and name.startswith("Name") and phone == "Number"):
                    continue
                if cat and "Regional Center" in cat:
                    continue

                if cat:
                    current_cat = cat
                if not name:
                    continue

                rows.append(_row(
                    "sgprc",
                    name=name,
                    category=current_cat,
                    phone=_phone(phone),
                    email=email,
                ))
    return rows


# ==========================================================================
# 3. Westside -- Westside Regional Center (85 pages)
# ==========================================================================
#
# Layout: a CATEGORY heading on its own line, then rows of
#         Name | Address | City | Email beneath it.
#
# Headings are NOT distinguishable by position -- a wrapped provider name sits
# at the same x as a heading (page 1's "DANCE STUDIO" is the tail of
# "ATTENDANCE INC. DBA: DANCER4LIFE", not a category).  They ARE distinguishable
# by font: headings are Calibri-Bold at 12pt, every data cell is Calibri at
# 11pt.  77 heading lines in the document, some of which wrap over two lines
# and are joined here.
#
# The per-page column geometry DRIFTS in this file (the address column starts
# anywhere from x=236 to x=290 depending on the section's table), so the
# boundaries are placed in the wide gaps BETWEEN the columns' start positions
# rather than near any one column:
#     name starts   50.8-81      (a few indented sub-entries reach 195)
#     address       236-290
#     city          409-420
#     email         493-510
# Boundaries 232 / 350 / 492 sit inside those gaps for every page, so one
# latched map covers all 85 pages despite the drift.
WRC_BOUNDS = [232.0, 350.0, 492.0]                  # name | address | city | email
# y-band.  Only page 1 carries the long preamble (banner, WIC disclaimer,
# revision date) that pushes its first row down to top=114.8; on pages 2-85 the
# banner ends at 41.3 and the first data row starts at top=58.3.  A cut at 100
# would silently drop the first three or four rows of all 84 following pages, so
# the band starts at 50 and the preamble is removed by font/content instead.
WRC_YTOP = 50.0
WRC_YBOT = 578.0
WRC_HEAD_SIZE = 12                                  # Calibri-Bold 12 = category
WRC_BODY_SIZE = 11                                  # Calibri 11 = data cells

# Vertical assembly.  The four cells of one record are NOT always drawn on the
# same baseline: depending on the section the source uses, a record's e-mail can
# sit 0.4pt above its name, its address 1pt below, and in one variant the city
# and e-mail are drawn ~7pt ABOVE the name they belong to.  Measured over all
# 85 pages the gaps between consecutive line tops are sharply bimodal: 0-2pt
# (585 cases, same record) and >=11pt (1500+ cases, next line of the table).
# WRC_LINE_TOL groups the first kind together; anything further apart is a
# separate line and is resolved by nearest-anchor attachment below.
WRC_LINE_TOL = 3.0
# Baselines closer together than this are the same physical line of text.
WRC_PHYS_TOL = 0.5

# Run-splitting gap.  Westside cells frequently END exactly where the next cell
# BEGINS, so the junction is not a clear space.  Signed character-to-character
# deltas over the whole document are a dense kerning band from -0.5 to +0.5
# (~50k samples) and then nothing until |delta| >= 0.7 -- and a cell junction
# often shows as a small NEGATIVE delta (the next cell starts slightly left of
# where the previous ended, e.g. -0.77 between "…ISRAEL CENTER FOR THE" and
# "1400 GLENVILLE DR").  0.65 sits in that empty valley: it separates glued
# cells without cutting words apart.
WRC_RUN_GAP = 0.65

# A wrapped continuation line can carry a name fragment together with an
# address fragment ("TO INDEPENDENCE" + "#306"), which would otherwise look
# like a new record.  A genuine new record carries a city, an e-mail, or an
# address that starts with a street number.
_WRC_STREET = re.compile(r"^\d+\s+\S")


def _wrc_font(chars):
    """Dominant (fontname, rounded size) of a line, or None if blank."""
    ink = [c for c in chars if c["text"].strip()]
    if not ink:
        return None
    f = collections.Counter((c["fontname"], round(c["size"])) for c in ink)
    return f.most_common(1)[0][0]


def _wrc_is_heading(chars):
    f = _wrc_font(chars)
    return bool(f) and "Bold" in f[0] and f[1] == WRC_HEAD_SIZE


# Non-data furniture that shares the data band on some pages.
_WRC_SKIP = re.compile(
    r"WESTSIDE REGIONAL CENTER|SERVICE PROVIDERS|WRC List of Service"
    r"|Welfare & Institutions|WIC 4629|^REVISED |^\*\*|^#")


def _wrc_add(rec, key, value):
    """Merge a cell fragment into a record.

    E-mails wrap mid-token ("...@GMAIL." + "COM"), so a fragment is appended
    with no separator; names and addresses wrap on word boundaries and take a
    space.  An empty field is simply filled.
    """
    old = rec.get(key)
    if not old:
        rec[key] = value
    elif key == "email":
        rec[key] = old + value
    else:
        rec[key] = old + " " + value


def parse_westside(path, pages=None):
    rows = []
    category = None
    pending_head = []           # consecutive bold lines form one category
    cur = None                  # record open for name-wrap continuation
    stats = {"name_wraps": 0, "orphans_back": 0, "orphans_fwd": 0}

    def flush_head():
        nonlocal category, pending_head
        if pending_head:
            category = _norm(" ".join(pending_head))
            pending_head = []

    with pdfplumber.open(path) as pdf:
        for _i, page in _pages(pdf, pages):
            anchored = []        # [(top, record)] records anchored on this page
            orphans = []         # [(top, cells)] lines with no name column

            for top, chars, runs in _logical_rows(
                    page, WRC_YTOP, WRC_YBOT, WRC_PHYS_TOL, WRC_LINE_TOL,
                    WRC_RUN_GAP):
                text_all = "".join(c["text"] for c in chars).strip()
                if not text_all or _WRC_SKIP.search(text_all):
                    continue
                # The page banner and the revision date are set at 14pt; every
                # data cell is 11pt and every category heading 12pt.
                font = _wrc_font(chars)
                if font and font[1] > WRC_HEAD_SIZE:
                    continue

                if _wrc_is_heading(chars):
                    pending_head.append(text_all)
                    cur = None
                    continue
                flush_head()

                cells = {}
                for x0, _x1, txt in runs:
                    k = ("name", "address", "city", "email")[_bucket(x0, WRC_BOUNDS)]
                    cells[k] = (cells[k] + " " + txt) if k in cells else txt
                cells = {k: v for k, v in ((k, _norm(v)) for k, v in cells.items())
                         if v}
                if not cells:
                    continue

                if "name" not in cells:
                    # Cannot be placed yet: it may continue the record above OR
                    # belong to the record below (some sections draw a record's
                    # city/e-mail ~7pt ABOVE its name).  Resolved after the page.
                    orphans.append((top, cells))
                    continue

                # Is this a new record, or the wrapped tail of the one above?
                # A new record carries a city, an e-mail, or a street-numbered
                # address.  A continuation carries only name/address fragments
                # ("SPECTRUM CONNECTION LLC DBA WE ROCK THE" / "SPECTRUM-R";
                # "…POSITIVE STEPS" / "TO INDEPENDENCE" with "#306").
                # An e-mail counts as evidence of a new record only if it is a
                # whole address ("H.COM" is the tail of a wrapped one) and the
                # open record does not already have one (some vendors list two,
                # continued on the next line).
                email = cells.get("email") or ""
                starts_record = bool(
                    cells.get("city")
                    or _WRC_STREET.match(cells.get("address") or "")
                    or ("@" in email and not (cur or {}).get("email")))
                if cur is not None and not starts_record:
                    for k, v in cells.items():
                        _wrc_add(cur, k, v)
                    stats["name_wraps"] += 1
                    continue

                cur = _row("westside", category=category, **cells)
                rows.append(cur)
                anchored.append((top, cur))

            # Attach each orphan line to the vertically NEAREST anchored record.
            # Checked against every ambiguous case in the document: a wrapped
            # e-mail sits ~13pt below its own record and further from the next,
            # while a vertically-offset city/e-mail sits ~7pt above the record
            # it belongs to and ~22pt below the previous one.
            for top, cells in orphans:
                if anchored:
                    anchor_top, rec = min(anchored, key=lambda p: abs(top - p[0]))
                    stats["orphans_fwd" if anchor_top > top
                          else "orphans_back"] += 1
                elif cur is not None:
                    rec = cur           # first line of a page, record above
                    stats["orphans_back"] += 1
                else:
                    continue
                for k, v in cells.items():
                    _wrc_add(rec, k, v)

    for r in rows:
        r["city"] = _title_city(r.get("city"))
        for k in ("name", "address", "email"):
            r[k] = _norm(r.get(k))
    parse_westside.stats = stats
    return rows


# ==========================================================================
# 4. GGRC -- Golden Gate Regional Center (28 pages)
# ==========================================================================
#
# Page 1 is a cover page.  From page 2 onwards extract_table() works; the only
# adjustments needed are (a) skip the cover, (b) drop the header row that
# repeats on every page, and (c) the City column carries the state glued on
# ("SAN FRANCISCO CA") which is split off here.
GGRC_HEADER = "Vendor #"
GGRC_COLS = ("vendor_no", "category", "name", "address", "city", "zip", "phone")


def parse_ggrc(path, pages=None):
    rows = []
    with pdfplumber.open(path) as pdf:
        for _i, page in _pages(pdf, pages, skip_first=True):   # p1 is the cover
            table = page.extract_table()
            if not table:
                continue
            for raw in table:
                if not raw or (raw[0] or "").strip() == GGRC_HEADER:
                    continue
                if len(raw) < len(GGRC_COLS):
                    continue
                d = dict(zip(GGRC_COLS, (_norm(v) for v in raw)))
                city = d.get("city") or ""
                m = re.match(r"^(.*?)\s+([A-Z]{2})$", city)
                if m:
                    city = m.group(1)
                rows.append(_row(
                    "ggrc",
                    vendor_no=d.get("vendor_no"),
                    name=d.get("name"),
                    category=d.get("category"),
                    address=d.get("address"),
                    city=_title_city(city),
                    zip=d.get("zip"),
                    phone=_phone(d.get("phone")),
                ))
    return rows


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

PARSERS = {
    "sdrc": parse_sdrc,
    "sgprc": parse_sgprc,
    "westside": parse_westside,
    "ggrc": parse_ggrc,
}


def parse(key, path, pages=None):
    """Parse one directory.  ``key`` in {'sdrc','sgprc','westside','ggrc'}.

    ``pages`` optionally restricts parsing to a set of 0-based page indices;
    it exists for verification and is None in normal use.
    """
    key = key.lower()
    if key not in PARSERS:
        raise ValueError("unknown key %r; expected one of %s"
                         % (key, sorted(PARSERS)))
    return PARSERS[key](path, pages)


# --------------------------------------------------------------------------
# Column-map derivation (documentation of provenance / re-derivation tool)
# --------------------------------------------------------------------------

def derive_column_map(path, ytop, ybot, every=4, gap=0.6, top_n=12):
    """Re-derive a file's column anchors from the PDF itself.

    Prints the modes of the run START x co-ordinates (left-aligned columns) and
    of the run END x co-ordinates (right-aligned columns, e.g. phone numbers),
    plus the zero-ink intervals between them.  The latched *_BOUNDS constants
    above were read off this output; run it again if a new edition of one of
    these directories is published, and put each boundary in the middle of an
    empty interval between two adjacent column START modes.
    """
    starts, ends = collections.Counter(), collections.Counter()
    hist = collections.Counter()
    with pdfplumber.open(path) as pdf:
        for i in range(0, len(pdf.pages), every):
            page = pdf.pages[i]
            for _t, chars in _lines(page, ytop, ybot, tol=1.5):
                for x0, x1, _txt in _runs(chars, gap=gap):
                    starts[round(x0, 2)] += 1
                    ends[round(x1, 2)] += 1
                for c in chars:
                    if c["text"].strip():
                        for x in range(int(c["x0"]), int(c["x1"]) + 1):
                            hist[x] += 1
    print("run START modes:", starts.most_common(top_n))
    print("run END   modes:", ends.most_common(top_n))
    lo, hi = min(hist), max(hist)
    empty, run_start = [], None
    for x in range(lo, hi + 1):
        if hist[x] == 0:
            run_start = x if run_start is None else run_start
        elif run_start is not None:
            empty.append((run_start, x - 1))
            run_start = None
    print("zero-ink intervals:", [e for e in empty if e[1] - e[0] >= 1])


if __name__ == "__main__":
    key, path = sys.argv[1], sys.argv[2]
    out = parse(key, path)
    print(json.dumps(out[:5], indent=2))
    print("rows:", len(out), file=sys.stderr)
