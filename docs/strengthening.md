# Strengthening investigation — findings & plan

> 2026-06-26. Drove the CLI against a **real ~2,000-triple ontology** (14 classes, ~240
> class instances, 16 object / 14 data properties, reified provenance statements,
> mixed-language labels, email contact literals) instead of the toy fixtures, to find where
> it actually breaks. Evidence-based; each finding was reproduced.

## What was exercised
- `wp create` / `wp export` round-trip of a 199 KB / 2,064-triple ontology.
- `onto info` / `query` / `validate --reason` / `add-*` / `remove` on both the WebProtégé
  export and the canonical source file.
- `wp apply-edits` happy path at scale + the ontology-IRI-mismatch edge case.

## Findings

| # | sev | finding | status |
|---|---|---|---|
| S1 | **high** | WebProtégé round-trip corrupts any literal containing `@` (emails) into an invalid language-tagged literal; emails embedded in free text break the serialization structurally | **partly fixed** (sanitizer) + architectural guidance |
| S2 | med | `validate --reason` (HermiT) aborts on datatypes outside the OWL2 map (e.g. `xsd:gYear`) | documented; fallback planned |
| S3 | med | `apply-edits` with a mismatched ontology IRI silently applies 0 changes and exits 0 | **fixed** (warns on 0 changes) |
| S4 | low | `onto info` counted only `owl:NamedIndividual`, missing individuals declared as `a :Class` | **fixed** (reports class instances too) |
| S5 | low | `onto remove` of an entity used as a reified statement's `rdf:subject/object` leaves an orphaned `rdf:Statement` blank node | documented |
| S6 | low | each browser op is ~9–15 s; fixed `waitForTimeout`s held at 2 k triples but have no safety margin for much larger / slower instances | planned (state-based waits) |

## Detail

### S1 — WebProtégé mangles `@` literals (the big one)
A plain literal `"user@dept.edu"` comes back out of WebProtégé as `"user"@dept.edu` — i.e. the
domain is treated as an RDF **language tag**. But BCP47 language tags can't contain `.`, so the
export is invalid Turtle/RDF and a spec-compliant parser (rdflib) refuses it. Confirmed:
- The source file and the uploaded `.owl` have the email as a normal string (rdflib loads them
  fine). After one WebProtégé round-trip, **~40 email literals** became language-tagged.
- It is **not** a Turtle-writer-only bug: the **RDF/XML** export also carries
  `xml:lang="dept.edu"`, so the corruption is in WebProtégé's stored data, not just one
  serializer.
- **Worse case:** when an email sits *inside* a longer free-text value
  (`"… contact foo@dept.edu, …"`), the split truncates the string at `@` and the text after the
  domain dangles as stray tokens → structurally broken Turtle that no regex cleanly repairs.

**Mitigation shipped:** `onto` sanitizes on load — any `"…"@<tag-with-a-dot>` (always a mangled
literal, since valid tags have no dot) is re-joined into the quoted string. This recovers the
simple "value is an email" case (40/40). It does **not** fully recover emails embedded mid-text.

**Architectural guidance (the real fix):** treat the **canonical file (git) as the source of
truth**, not the WebProtégé export. Edit that file with `onto`, then `wp apply-edits` to *push*
to WebProtégé for visualization. Do **not** build the edit on a fresh `wp export` — pulling
re-imports WebProtégé's corruption. The canonical 2,064-triple file loads, validates, and edits
cleanly; only the WebProtégé export is lossy. (If you must start from an export, prefer Turtle +
the sanitizer, and spot-check email/free-text fields.)

### S2 — reasoner datatype limits
`onto validate --reason` shells HermiT (via owlready2). HermiT only supports the OWL2 datatype
map and aborts on others; the real ontology uses `xsd:gYear`, so reasoning fails with
`UnsupportedDatatypeException`. The CLI degrades gracefully (prints the reason) but gives no
result. Plan: try Pellet as a fallback (wider datatype support), and/or surface a one-line
"reasoner can't handle datatype X" message. `validate` (parse + structural) is unaffected and
still useful.

### S3 — silent no-op on IRI mismatch (fixed)
`apply-edits` of a file whose ontology IRI differs from the project's produced
`applied … (~0 change(s))` and exit 0 — easy to mistake for success. Now the CLI prints a
warning whenever 0 changes are applied, naming the likely cause (IRI mismatch). A stronger
future check: compare the file's ontology IRI to the project's before uploading.

### S4 — individual count (fixed)
`onto info` now reports both `owl:NamedIndividual` count and "class instances" (subjects typed
with a declared class), so ABox-heavy ontologies that don't use explicit `NamedIndividual`
typing aren't shown as having 0 individuals.

### S5 — remove + reification
`onto remove --iri X` deletes every triple with X as subject or object. If X is the
`rdf:subject`/`rdf:object` of a reified `rdf:Statement`, the statement's blank node is left
behind (orphaned provenance). Low impact, but a `--prune-reification` option (drop dangling
`rdf:Statement` bnodes) would be cleaner.

### S6 — Playwright timing
Browser ops take ~9–15 s on the real ontology and the fixed `waitForTimeout`s were sufficient,
but they're guesses. For larger/slower instances, replace fixed sleeps with state-based waits
(e.g. wait for the merge preview's change list or a known post-condition element) to remove
flakiness and dead time.

## Prioritized plan
1. **Adopt & document the file-as-source-of-truth pattern** (S1) — the single most important
   change; makes the @-corruption irrelevant for editing. *(guidance written; reflect in README)*
2. **Keep/extend the load sanitizer** (S1) — done for simple emails; consider a line-oriented
   recovery for embedded emails if export-based editing is ever needed.
3. **`apply-edits` 0-change warning** (S3) — done; consider a pre-flight IRI check.
4. **Reasoner robustness** (S2) — Pellet fallback + clearer datatype message.
5. **State-based Playwright waits** (S6) and **`onto info` instance count** (S4, done).
6. **`remove --prune-reification`** (S5) and a **`wp sync`** wrapper for the 3-step loop.

## Bottom line
The CLI is solid for the **push** direction (file → WebProtégé) at real scale. The fragile part
was treating the **WebProtégé export as the editing base** — that route hits S1. With the
canonical file as source of truth, the hybrid (`onto` edit → `wp apply-edits`) is robust on the
real ontology.
