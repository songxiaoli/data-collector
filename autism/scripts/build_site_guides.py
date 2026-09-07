#!/usr/bin/env python3
"""Turn the guides as authored on claude.ai into standalone pages for
powerpluspartner.com/autism/guides.

Three things have to change for a page to live on the site rather than on
claude.ai:

  1. The artifact runtime wraps the file in a document skeleton. Served from
     Vercel nothing does, so each page needs its own <!doctype>, <head>,
     charset and viewport.
  2. One page persists a family's call notes by republishing themselves
     through window.claude's `artifact` capability. That capability only
     exists on claude.ai — and republishing is the wrong model here anyway,
     because a published page is one share away from public and these are a
     parent's private notes about their own child. On the site the notes go
     to localStorage: this browser, this device, nobody else.
  3. The hub links to claude.ai artifact URLs. On the site it links to
     sibling pages.

Nothing else about the pages is touched.
"""

import re
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "autism" / "guides-src"     # the pages as authored
OUT = ROOT / "web" / "autism" / "guides"  # what Vercel serves

# slug -> (source file, container width for the top bar, back-link)
PAGES = {
    "index":            ("start-here.html",     720, ("/autism", "Provider library")),
    "first-90-days":    ("first-steps.html",    750, ("/autism/guides", "All guides")),
    "four-questions":   ("four-questions.html", 720, ("/autism/guides", "All guides")),
    "who-does-what":    ("who-does-what.html",  860, ("/autism/guides", "All guides")),
    "age-three":        ("rc-brief.html",       820, ("/autism/guides", "All guides")),
    "system-gaps":      ("system-seams.html",  1000, ("/autism/guides", "All guides")),
    "zh":               ("primer-zh.html",      820, ("/autism/guides", "所有指南")),
    "three-pockets":    ("primer-en.html",      820, ("/autism/guides", "All guides")),
    # frc-call-sheet.html is deliberately not here. It is our own outreach list —
    # who to ring at six Family Resource Centers and what to open with — not
    # something a family is looking for. It stays a private artifact.
}

# the claude.ai artifact ids the hub currently points at
ARTIFACT_LINKS = {
    "fc235e8e-e647-4c18-8c98-3abc00869a02": "/autism/guides/first-90-days",
    "3ab89f0f-81c0-4030-b662-50fb33c14206": "/autism/guides/four-questions",
    "62cb6a84-44d4-4415-8cbe-9f3ec0be357d": "/autism/guides/who-does-what",
    "61df2ea5-2cb2-4fba-9be0-f39dea4af947": "/autism/guides/system-gaps",
    "4e4dee9c-422c-4468-af04-0c619d1be435": "/autism/guides/age-three",
}

SPLIT = re.compile(r'^<div class="(?:wrap|sheet)">', re.M)

# The two primers carry <!-- internal:start --> … <!-- internal:end --> markers
# around the sections that say what we would build at each trap and in what
# order. They were stripped for the site at first; the decision on 7 Sept 2026
# was to publish the roadmap too, so nothing is stripped now. The markers stay
# so that flipping back is a one-line change: put a slug in STRIP_INTERNAL.
INTERNAL = re.compile(r'\s*<!-- internal:start -->.*?<!-- internal:end -->', re.S)
STRIP_INTERNAL = set()
LANG = {"zh": "zh-CN"}

HEAD = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{desc}">
<link rel="canonical" href="https://powerpluspartner.com/autism/guides{canon}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Power Plus Partner">
<style>
:root{{color-scheme:light dark}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0}}
img{{max-width:100%}}
[hidden]{{display:none!important}}
.ppp-bar{{max-width:{w}px; margin:0 auto; padding:16px 22px 0;
  display:flex; justify-content:space-between; align-items:center; gap:16px;
  font:600 10.5px/1 Manrope, ui-sans-serif, system-ui, sans-serif;
  letter-spacing:.14em; text-transform:uppercase}}
.ppp-bar a{{color:inherit; opacity:.5; text-decoration:none}}
.ppp-bar a:hover{{opacity:1}}
</style>
"""

BAR = """
<nav class="ppp-bar" aria-label="Site">
  <a href="/autism">Power Plus Partner</a>
  <a href="{href}">{label}</a>
</nav>
"""

META = {
    "index": ("Autism in California: Start Here",
              "Four short guides for California families and two for people who work inside the "
              "system \u2014 what to do first, what to ask, who is responsible, and where it leaks."),
    "first-90-days": ("The First Ninety Days",
                      "What to do from the day you first wonder, in order, with the words to say "
                      "on each call and the legal deadline each one starts."),
    "four-questions": ("Four Questions First",
                       "The four questions to ask a California autism provider, in the order that "
                       "saves the most time, with a place to log what each one said."),
    "who-does-what": ("Who Does What",
                      "Every party in California's autism system, what each must do by law, what "
                      "it does not do, and where two systems hand your child to each other."),
    "age-three": ("The Age Three Handoff",
                  "What happens to therapy funding when a California child turns three, counted "
                  "from the vendor lists the regional centres publish."),
    "zh": ("谁管什么，谁付钱",
           "从零开始，跟着一个孩子走一遍加州的自闭症服务系统：每个机构在它出场时才介绍，"
           "每一步说清谁付钱、谁负责、坑在哪。中文。"),
    "three-pockets": ("Three Pockets",
                      "Who handles what and who pays, explained from zero by following one child "
                      "through California's autism system: each organisation introduced as it appears, "
                      "and at every step who pays, who is responsible, and where the trap is."),
    "system-gaps": ("The Handoffs Nobody Owns",
                    "Where California's autism system leaks: what the law assigns at each handoff, "
                    "what the state's own numbers show happens instead, and what would close it."),
    "family-resource-centers": ("Family Resource Centers: Who to Call",
                                "Six California Family Resource Centers, why each one is worth a "
                                "call, and a sheet to track what they said."),
}

# ---------------------------------------------------------------- notes ----
# Replaces the artifact-publish block. `state`, `render`, and the touch
# function are already defined by the page; this only changes where the
# notes go.
LOCALSTORE = """(function(){
  // On claude.ai this page saved notes by republishing itself. Here the notes
  // stay in this browser: a family's call log about their own child is not
  // something to put behind a shareable URL.
  const KEY = "%(key)s";
  const btn = document.getElementById("save"), msg = document.getElementById("savemsg");
  let usable = true;
  try {
    const raw = localStorage.getItem(KEY);
    if (raw){
      const saved = JSON.parse(raw);
      if (saved && saved.calls){ state = saved; %(fixup)s render(); }
    }
  } catch (err){ usable = false; }

  function persist(){
    try { localStorage.setItem(KEY, JSON.stringify(state)); return true; }
    catch (err){ return false; }
  }

  if (!usable){
    btn.style.display = "none";
    msg.textContent = "This browser is blocking storage, so notes will not survive a reload.";
    return;
  }

  const original = %(touch)s;
  %(touch)s = function(){
    original();
    if (persist()){
      dirty = false;
      btn.disabled = true;
      msg.textContent = "Saved in this browser.";
    }
  };

  btn.disabled = true;
  msg.textContent = "Notes save automatically, in this browser on this device only.";
  btn.addEventListener("click", () => {
    msg.textContent = persist() ? "Saved in this browser."
                                : "Could not save — this browser is blocking storage.";
  });
})();"""

NOTE_PAGES = {
    "four-questions": dict(
        key="ppp.autism.four-questions.v1",
        touch="touch",
        fixup='if (!Array.isArray(state.calls)) state.calls = []; if (!state.calls.length) state.calls.push({});',
    ),
    "family-resource-centers": dict(
        key="ppp.autism.frc-call-sheet.v1",
        touch="markDirty",
        fixup="",
    ),
}

ARTIFACT_BLOCK = re.compile(
    r"\(async \(\) => \{\n(?:(?!\}\)\(\);).)*?window\.claude(?:(?!\}\)\(\);).)*?\}\)\(\);",
    re.S)

PRISTINE_LINE = re.compile(r'<script>\nconst PRISTINE = document\.documentElement\.outerHTML;\n</script>\n')


def build(slug, src_name, width, back):
    raw = (SRC / src_name).read_text()
    title, desc = META[slug]

    # the hub's four doors
    for aid, path in ARTIFACT_LINKS.items():
        raw = raw.replace(f"https://claude.ai/code/artifact/{aid}", path)
    if "claude.ai/code/artifact" in raw:
        sys.exit(f"{slug}: an artifact link is still unrewritten")

    # notes: republish -> localStorage
    if slug in NOTE_PAGES:
        new, n = ARTIFACT_BLOCK.subn(LOCALSTORE % NOTE_PAGES[slug], raw)
        if n != 1:
            sys.exit(f"{slug}: expected exactly one artifact block, matched {n}")
        # PRISTINE only existed to build the republished copy
        new, _ = PRISTINE_LINE.subn("", new)
        raw = new
    if "window.claude" in raw:
        sys.exit(f"{slug}: window.claude survived the rewrite")

    if slug in STRIP_INTERNAL:
        raw, n = INTERNAL.subn("", raw)
        if n == 0:
            sys.exit(f"{slug}: expected internal blocks to strip, found none")
        if "internal:" in raw:
            sys.exit(f"{slug}: an internal marker survived")
    # the bare markers never belong in served HTML, stripped or not
    raw = raw.replace("<!-- internal:start -->", "").replace("<!-- internal:end -->", "")

    m = SPLIT.search(raw)
    if not m:
        sys.exit(f"{slug}: no top-level container found")
    head, body = raw[:m.start()], raw[m.start():]

    href, label = back
    doc = (HEAD.format(desc=desc, title=title, canon="" if slug == "index" else "/" + slug, w=width,
                       lang=LANG.get(slug, "en"))
           + head.rstrip() + "\n</head>\n<body>\n"
           + BAR.format(href=href, label=label)
           + body.rstrip() + "\n</body>\n</html>\n")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{slug}.html").write_text(doc)
    return slug, len(doc)


if __name__ == "__main__":
    for slug, (src, w, back) in PAGES.items():
        name, size = build(slug, src, w, back)
        print(f"{name:26} {size:>7,} bytes")
