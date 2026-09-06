# Autism Resource Library

A sibling product to the SEL Resource Finder, served at `/autism` under the same
shell. The two share a design system, a header and an account; they do not share
a matching layer, a taxonomy or an editorial policy.

The SEL finder matches on one axis — what the child is going through. This one
matches on two: what you are dealing with **and** where you are in a process that
runs from first suspicion to adulthood. The stage strip is that second axis.

```
autism/
├── data/resources.json     the curated set (gitignored — Supabase is the store)
├── scripts/
│   ├── import_autism_resources.py     JSON -> Supabase, derives the stage axis
│   └── therapist_field_normalizer.py  repairs the enrichment pipeline's output
├── sql/
│   ├── 001_schema.sql                 table, RLS, GIN + full-text indexes
│   └── 002_region_vocabulary.sql      CHECK constraint on `region`
└── (the page itself lives at web/autism/index.html — under web/ because
    that directory is Vercel's output root, so its layout is the URL layout)
```

## Running things

```bash
# credentials come from the repo-root .env, never from a file in git
python3 autism/scripts/import_autism_resources.py --check     # is the table reachable
python3 autism/scripts/import_autism_resources.py --dry-run   # counts, writes nothing
python3 autism/scripts/import_autism_resources.py             # upsert on slug
```

SQL migrations run in the Supabase SQL editor, in numeric order. Both are
idempotent and safe to re-run.

## The editorial layer

Every entry carries a stance: `affirming`, `neutral`, `contested`,
`portrayal-debated` or `unreviewed`. The house rules:

1. **Include, label, never bury.** A resource families actually use stays in the
   library even when the autistic community criticizes it.
2. **State the criticism as a fact about the debate**, naming who makes it and
   when — never as the site's own opinion.
3. **Exclude health misinformation outright**: cure and recovery claims,
   chelation, MMS, anti-vaccine content. Behaviour-analytic practice is
   contested, not excluded.
4. **Flag autistic authorship only from the creator's own self-description** —
   never from a third-party list, never from inference.
5. **Record what could not be verified** rather than softening or guessing it.

`publish_status = 'hold-needs-human'` withholds a row from the site entirely: the
RLS policy only exposes rows where it is NULL, so nothing unverified can reach the
anon key even by mistake.

## Region

California uses the `US-<state>` convention already present in the table, because
`CA` for California collided with `ca` and `CANADA` for Canada and every prefix
test put a Vancouver charity into California results. Valid values are `US`,
`UK`, `AU`, `CANADA`, `EU`, `IE`, `NZ`, `IN`, `GLOBAL`, or `US-XX[-area]`.
`002_region_vocabulary.sql` enforces this.
