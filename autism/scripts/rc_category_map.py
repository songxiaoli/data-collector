#!/usr/bin/env python3
"""Map regional-centre category WORDS onto verified DDS service codes.

Five centres publish a numeric service code per vendor row. Four — San Diego,
San Gabriel/Pomona, Westside and Golden Gate — publish the service as a phrase
instead, in their own house abbreviations, so 8,841 rows cannot reach the
relevance logic until the phrases are mapped.

The mapping is only as trustworthy as the code table behind it, so it is split
three ways rather than forced into two:

  direct   the phrase names a service whose DDS code we verified against the
           Rate Reform Service Code Crosswalk of 5 February 2026. These carry a
           code and count exactly like a numeric row from another centre.
  support  the phrase names a service that supports the family rather than
           treating the child — respite, parent training, interpreting. Counted,
           labelled, and given a code only where one was verified.
  review   the phrase is plainly autism-relevant but its code is NOT in our
           verified table. These are kept and flagged, never given a guessed
           code. "Behavior Management Consultant" is real and relevant; writing
           616 next to it because 616 is nearby would put a wrong number into a
           database that nobody would ever re-check.

Everything not listed is unmapped and drops out — dentistry, pharmacy, durable
medical equipment, transport, nursing and geriatric facilities are things a
regional centre buys, not autism services.
"""
import json, re, collections
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── direct: phrase -> (code, canonical name) ──────────────────────────────────
# Codes verified against the DDS Rate Reform Service Code Crosswalk, 2026-02-05.
DIRECT = {
    "ES OT/PT/ST SPEC THERAPEUTIC SRVCS":           ("116", "Early Start Specialized Therapeutic Services"),
    "EARLY START SPEC THERAPEUTIC SRVCS":           ("116", "Early Start Specialized Therapeutic Services"),
    "EARLY START SPECIALIZED THERAPEUTIC SERVICES": ("116", "Early Start Specialized Therapeutic Services"),
    "SPECIAL THERAPEUTIC SRVCS":                    ("117", "Specialized Therapeutic Services (age 3 and older)"),
    "SPECIALIZED THERAPEUTIC SERVICES":             ("117", "Specialized Therapeutic Services (age 3 and older)"),
    "BEHAVIOR ANALYST":                             ("612", "Behavior Analyst"),
    "ASSOC BEHAVIOR ANALYST":                       ("613", "Associate Behavior Analyst"),
    "ASSOCIATE BEHAVIOR ANALYST":                   ("613", "Associate Behavior Analyst"),
    "BEHAVIOR MGMT ASSIST":                         ("615", "Behavior Management Assistant"),
    # The source's own spelling. Matching what a file says beats matching what
    # it ought to say — an unrecognised phrase is silently dropped, not flagged.
    "BEHAVIOR MANAGEMENT ASSISSTANT":               ("615", "Behavior Management Assistant"),
    "BEHAVIOR MANAGEMENT ASSISTANT":                ("615", "Behavior Management Assistant"),
    "BEHAVIOR MGMT TECH":                           ("616", "Behavior Technician - Paraprofessional"),
    "BEHAVIOR MANAGEMENT TECHNICIAN":               ("616", "Behavior Technician - Paraprofessional"),
    "BEHAVIOR MGMT PROGRM":                         ("515", "Behavior Management Program"),
    "BEHAVIOR MANAGEMENT PROGRAM":                  ("515", "Behavior Management Program"),
    "INFANT DEV PROGRAM":                           ("805", "Infant Development Program"),
    "INFANT DEVELOPMENT PROGRAM":                   ("805", "Infant Development Program"),
}

# ── support: family-facing rather than child-treating ─────────────────────────
SUPPORT = {
    "IN-HOME RESPITE SERV":            ("862", "In-Home Respite Services"),
    "IN-HOME RESPITE SERVICES":        ("862", "In-Home Respite Services"),
    # Out-of-home respite is a separate code we have not verified. It is still
    # respite, and respite is the thing parents ask for most, so it counts —
    # with the code left empty rather than borrowed from 862.
    "OUT-OF-HOME RESPITE SERVICES":    (None,  "Out-of-Home Respite Services"),
    "OUT OF HOME RESPITE SERVICES":    (None,  "Out-of-Home Respite Services"),
    "INDIVIDUAL OR FAMILY TRAINING":   (None,  "Individual or Family Training"),
    "COORDINATED FAMILY SUPPORT SERVICES": (None, "Coordinated Family Support Services"),
    "COORDINATED FAMILY SUPPORTS":     (None,  "Coordinated Family Support Services"),
    "TRANSLATOR":                      (None,  "Translator"),
    "INTERPRETER":                     (None,  "Interpreter"),
}

# ── review: autism-relevant, code not in our verified table ───────────────────
REVIEW = {
    "ADAPTIVE SKILL TRAIN":                     "Adaptive Skills Training",
    "ADAPTIVE SKILLS TRAINING":                 "Adaptive Skills Training",
    "BEHAVIOR MGMT CONSUL":                     "Behavior Management Consultant",
    "BEHAVIOR MANAGEMENT CONSULTANT":           "Behavior Management Consultant",
    "BEHAV. DAY PROGRAM":                       "Behavior Management Day Program",
    "BEHAVIOR MANAGEMENT DAY PROGRAM":          "Behavior Management Day Program",
    # An age split of the therapeutic-services family. 117 is documented as
    # "age 3 and older", so a 21-and-over listing is probably a different code;
    # probably is not good enough to write a number down.
    "SPECIALIZED THERAPEUTIC SERVICES (21 & OVER)": "Specialized Therapeutic Services (21 and over)",
    "INTERDISCIPLINARY ASSESSMT SERVICE":        "Interdisciplinary Assessment Services",
    "INTERDISCIPLINARY ASSESSMENT SERVICES":     "Interdisciplinary Assessment Services",
    "SOCIALIZATION TRAINING PROGRAM":            "Socialization Training Program",
    "SPEECH PATHOLOGY":                          "Speech Pathology",
    "OCCUPATIONAL THERAPY":                      "Occupational Therapy",
    "CLINICAL PSYCHOLOGIST":                     "Clinical Psychologist",
    "MUSIC THERAPIST":                           "Music Therapist",
    "SPECIALIZED RECREATIONAL THERAPY":          "Specialized Recreational Therapy",
    "COUNSELING SERVICES":                       "Counseling Services",
}

def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().upper())

def classify(category):
    """-> (bucket, code, canonical name). bucket is direct|support|review|None."""
    c = _norm(category)
    if c in DIRECT:
        code, name = DIRECT[c];  return "direct",  code, name
    if c in SUPPORT:
        code, name = SUPPORT[c]; return "support", code, name
    if c in REVIEW:
        return "review", None, REVIEW[c]
    return None, None, None

def main():
    RCNAME = {"sdrc": "San Diego Regional Center",
              "sgprc": "San Gabriel/Pomona Regional Center",
              "westside": "Westside Regional Center",
              "ggrc": "Golden Gate Regional Center"}
    out, per = [], collections.defaultdict(lambda: collections.Counter())
    unmapped = collections.Counter()

    for key, rcname in RCNAME.items():
        rows = json.loads((HERE / f"parsed_{key}.json").read_text())
        for r in rows:
            bucket, code, name = classify(r.get("category"))
            if bucket is None:
                if r.get("category"):
                    unmapped[_norm(r["category"])] += 1
                continue
            per[key][bucket] += 1
            out.append({
                "rc": key, "rc_name": rcname,
                "vendor_no": r.get("vendor_no", "") or "",
                "name": r.get("name", ""),
                "service_code": code or "",
                "service_name": name,
                "category_raw": r.get("category", ""),
                "address": r.get("address", "") or "",
                "city": (r.get("city") or "").title(),
                "zip": re.sub(r"\D", "", r.get("zip", "") or "")[:5],
                "phone": r.get("phone", "") or "",
                "email": r.get("email", "") or "",
                "autism_direct":  bucket == "direct",
                "autism_support": bucket == "support",
                "needs_code_review": bucket == "review",
            })

    (HERE / "rc_vendors_wordlayout.json").write_text(json.dumps(out, indent=1))

    print(f"{len(out):,} rows mapped from 8,841 parsed\n")
    print(f"{'centre':10s} {'direct':>8s} {'support':>8s} {'review':>8s}")
    for k in RCNAME:
        p = per[k]
        print(f"{k:10s} {p['direct']:8,} {p['support']:8,} {p['review']:8,}")
    tot = collections.Counter()
    for p in per.values(): tot.update(p)
    print(f"{'total':10s} {tot['direct']:8,} {tot['support']:8,} {tot['review']:8,}")

    vend = lambda pred: len({(r["rc"], r["vendor_no"] or r["name"]) for r in out if pred(r)})
    print(f"\ndistinct vendors: {vend(lambda r: True):,} total, "
          f"{vend(lambda r: r['autism_direct']):,} autism-directed, "
          f"{vend(lambda r: r['autism_support']):,} family support")
    print(f"with an email: {sum(1 for r in out if r['email']):,}")

    print(f"\nunmapped categories dropped: {sum(unmapped.values()):,} rows, "
          f"{len(unmapped)} distinct. Largest:")
    for c, n in unmapped.most_common(12):
        print(f"   {n:5,}  {c}")

if __name__ == "__main__":
    main()
