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
| S1 | **high** | WebProtégé round-trip corrupts any literal containing `@` (emails) into an invalid language-tagged literal; emails embedded in free text break the serialization structurally | **fixed** (sanitizer recovers bare + embedded) + architectural guidance |
| S7 | **high** | WebProtégé round-trip **silently drops RDF reification** (`rdf:subject/predicate/object`), orphaning provenance annotations — invisible to counts/parsing, found only by structural set-diff (issue #14) | **guard + guidance** (onto warns; canonical = truth) |
| S2 | med | `validate --reason` (HermiT) aborts on datatypes outside the OWL2 map (e.g. `xsd:gYear`) | **fixed** (auto-relax unsupported datatypes + retry) |
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
literal, since valid tags have no dot) is re-joined into the quoted string. The regex pulls any
trailing original text (up to the end-of-line statement terminator) back inside the quotes, so it
now recovers **both** the bare "value is an email" case and the embedded-mid-text case
(real `cli test` export: 40/40 repaired, value reconstructed verbatim — issue #8).

**Architectural guidance (the real fix):** treat the **canonical file (git) as the source of
truth**, not the WebProtégé export. Edit that file with `onto`, then `wp apply-edits` to *push*
to WebProtégé for visualization. Do **not** build the edit on a fresh `wp export` — pulling
re-imports WebProtégé's corruption. The canonical 2,064-triple file loads, validates, and edits
cleanly; only the WebProtégé export is lossy. (If you must start from an export, prefer Turtle +
the sanitizer, and spot-check email/free-text fields.)

### S7 — WebProtégé silently drops RDF reification (issue #14, the subtle one)
Found by running a **structural set-diff** of the real ontology against its own re-export (the
field test that motivated this round). Counts all looked healthy — the trap is that the loss is
invisible to them:
- **Named (bnode-free) triples: 0 lost.** Every class/property/individual assertion survived; the
  +247 added triples are all benign type materialization (242 `owl:NamedIndividual`, 3
  `rdfs:Datatype`, 1 `owl:AnnotationProperty`, 1 `owl:Class`).
- **But `rdf:subject`/`rdf:predicate`/`rdf:object` went 26 → 0.** The 26 reified provenance
  statements kept their annotations (`:asOf`/`:source`/`:verified`/`:note`) but lost the link to
  *which fact* they describe — 78 triples gone, annotations orphaned.

**Cause:** OWLAPI doesn't model RDF reification, so on import it keeps the `rdf:Statement` node's
annotations (as an anonymous individual) but discards the non-OWL s/p/o pointers. The OWL 2 way to
annotate an axiom is `owl:Axiom` + `owl:annotatedSource/Property/Target`, which *is* supported —
the source ontology just doesn't use it. A WebProtégé limitation, not a CLI bug.

**Why it's dangerous:** no parse error, healthy counts, clean-looking export — only a bnode-level
diff reveals it. More insidious than S1.

**Guard shipped:** `onto info`/`validate` detect `rdf:Statement` reification and warn (exit 0)
that it won't survive a round-trip. Same architectural rule as S1: **canonical file = truth,
WebProtégé = view-only.** The deeper fix is a built-in round-trip differential (`onto diff` /
`wp verify`) that automates this set-diff so *unknown* losses can't hide either — see Prioritized.

### S2 — reasoner datatype limits — FIXED (2026-06-26 session 3)
`onto validate --reason` shells HermiT (via owlready2). HermiT only supports the OWL2 datatype
map and aborts on others; the real ontology uses `xsd:gYear`, so reasoning previously failed
with `UnsupportedDatatypeException` and produced no result.

**Pellet fallback was investigated and rejected for this environment.** owlready2 0.51 bundles
Pellet, but its Jena dependency is compiled for a newer JRE (class file 69 = Java 25) than the
machine ships (Java 21) — `sync_reasoner_pellet` dies with `UnsupportedClassVersionError`
*regardless of datatype*. So Pellet can't be the fallback here without a heavier JDK upgrade.

**Shipped instead — datatype relaxation + retry.** HermiT's abort message quotes the offending
datatype IRI; `_reason` catches it, rewrites every literal/`rdfs:range` using that datatype to
an opaque string **in a temp copy used only for reasoning** (the user's file is never touched),
and retries. The loop adds one datatype per pass until HermiT runs (or an inconsistency / a
non-datatype error surfaces). Class-level consistency / unsatisfiability reasoning — the part
users actually care about — runs to completion; the relaxed datatypes are reported on a
`reasoner: relaxed N unsupported datatype(s)…` line so nothing is hidden. Verified on the real
~2000-triple ontology: now reports "consistent, no unsatisfiable classes" after relaxing
`xsd:gYear`. Regression test added (`test/onto_test.py`, java-guarded). `validate` (parse +
structural) was already unaffected.

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
0. **A round-trip differential is the fundamental guard** (S1, S7) — **SHIPPED: `onto diff <A> <B>`.**
   The boundary to WebProtégé is lossy *by design* (RDF↔OWL is not 1:1) and we can't change that. So
   the durable fix isn't patching each loss — it's making **no loss go unnoticed**. `onto diff`
   structurally compares two files (bnode-free triples exactly; bnode structures — reification,
   lists, restrictions — by per-predicate count; plus an explicit reification check) and **exits 1
   if any A assertion is missing from B**. Verified: a file vs itself → `IDENTICAL` (exit 0); source
   vs re-export → 78 reification link-triples flagged lost (exit 1). It also catches `@`-mangling the
   sanitizer might miss — so it guards the *unknown* losses, not just S1/S7. Next: a post-push
   `wp verify` that auto-runs it, and `validate --profile owlapi-safe` (flag constructs known not to
   survive: reification, datatypes outside the OWL2 map, `@`-literals).
1. **File-as-source-of-truth pattern** (S1, S7) — the architectural rule that makes any boundary
   loss *harmless*: edit the canonical git file, push to WebProtégé for **viewing only**, never
   pull an export back as an edit base. *(guidance written + README; onto warns on reification.)*
2. **Load sanitizer** (S1) — done for bare **and** embedded emails (issue #8); a safety net, not
   the sanctioned path.
3. **Reification guard** (S7/#14) — done (`info`/`validate` warn). Deeper: an `owl:Axiom`
   re-encoding of provenance that survives the round-trip (needs live verification).
4. **`apply-edits` 0-change warning** (S3, done; consider pre-flight IRI check) +
   **reasoner robustness** (S2, done).
5. **State-based Playwright waits** (S6), **`remove --prune-reification`** (S5), **`wp sync`**
   wrapper, and **`onto info` instance count** (S4, done).

## Bottom line
The CLI is solid for the **push** direction (file → WebProtégé) at real scale. The fragile part is
the **boundary itself**: WebProtégé's RDF↔OWL translation is lossy (emails → S1, reification →
S7), and the losses are *silent* — counts and parsing look fine. Two things contain this: (a) the
architectural rule **canonical file = truth, WebProtégé = view-only**, which makes the loss
irrelevant to your data; and (b) treating the boundary as **verify-by-diff**, so nothing crosses
it on trust. With both, the hybrid (`onto` edit → `wp apply-edits` → push) is robust on the real
ontology.
