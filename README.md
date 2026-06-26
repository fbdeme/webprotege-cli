# webprotege-cli

Drive a **self-hosted [WebProtégé](https://github.com/protegeproject/webprotege)** instance
from the command line (and from agents) — create projects from an OWL/RDF file, list them, and
export them — without clicking through the web UI.

> Companion to the [`webprotege-selfhost`](https://github.com/fbdeme/webprotege-selfhost)
> runbook, which stands up the instance this CLI talks to.
>
> Packaged as a Claude Code skill at
> [`webprotege-cli-skill`](https://github.com/fbdeme/webprotege-cli-skill) so agents can drive
> this tool directly.

## Why a browser, not HTTP?

The 2019 monolithic image (`protegeproject/webprotege:latest`, `4.0.0-beta-3` — the only
published tag) has **no REST API**. Everything goes through a single GWT-RPC servlet
(`/webprotege/dispatchservice`), authentication is a **CHAP handshake**, and the payloads lean
on dozens of custom GWT serializers. Hand-rolling that wire protocol is a large, brittle
surface. Since you pin the image anyway, the robust path is to let the app's own JavaScript do
the protocol work and drive it with a headless browser (Playwright). Full reverse-engineering
notes: [`references/control-surface.md`](references/control-surface.md).

## Install

```bash
# Node side — the `wp` browser-control CLI
npm install            # installs playwright
npx playwright install chromium
npm link               # optional: puts `wp` on your PATH

# Python side — the `onto` structured edit engine (optional, for hybrid editing)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # rdflib + owlready2
```

Requires Node ≥ 18 and a reachable WebProtégé instance with sign-up enabled (see the
`webprotege-selfhost` runbook for the MongoDB seeds that enable it). The `onto` reasoner
(`validate --reason`) additionally needs Java on PATH (owlready2 bundles HermiT).

## Configure

Flags or environment variables:

| env | flag | default |
|---|---|---|
| `WP_URL` | `--url` | `http://localhost:5000` |
| `WP_USER` | `--user` | — |
| `WP_PASS` | `--pass` | — |
| `WP_EMAIL` | `--email` (signup only) | — |
| `WP_STATE` | `--state` | — (a file to cache the logged-in session) |

```bash
export WP_URL=http://localhost:5000
export WP_USER=alice WP_PASS='…'
```

## Usage

```bash
wp signup --email alice@example.org      # create an account (one-time)
wp login                                  # sign in (caches session if --state given)

wp create my-ontology -f ontology.owl -d "my KB" -l en
wp projects                               # list (•-prefixed)
wp projects --json                        # machine-readable

wp export my-ontology -F Turtle -o my-ontology.ttl.zip
#   formats: RDF/XML | Turtle | OWL/XML | Manchester OWL Syntax | Functional OWL Syntax
#   WebProtégé serves the ontology as a ZIP containing the serialized file.

# push an externally-edited ontology back into a project:
# WebProtégé diffs it (add + remove) and commits the delta as a new revision.
wp apply-edits my-ontology -f edited.owl -m "add Foo, drop Bar"
#   the edited file MUST keep the SAME ontology IRI as the project, or nothing is applied.
```

## Editing ontologies safely (hybrid flow)

Letting an LLM rewrite raw Turtle is hallucination-prone (invented IRIs, dropped triples,
malformed syntax). Instead, `onto` exposes *structured, validated delta operations* — the
agent chooses a command + arguments; the engine (rdflib) generates the triples, **refuses to
reference entities that don't exist**, preserves the ontology IRI, and re-parses after every
change. Then `wp apply-edits` pushes the result back into the live project as a new revision.

```bash
# 1) pull the current ontology out of the project (IRI preserved)
wp export my-ontology -F Turtle -o exp.zip && unzip -o exp.zip -d work
F=$(find work -name '*.ttl')

# 2) edit it with typed, checked operations (run with the venv python)
.venv/bin/python onto.py add-class      "$F" --iri :Pump --label "Pump" --parent :Device
.venv/bin/python onto.py add-objprop    "$F" --iri :drives --domain :Pump --range :Device
.venv/bin/python onto.py add-annotation "$F" --entity :Pump --prop rdfs:comment --text "..."
.venv/bin/python onto.py validate       "$F" --reason     # parse + structural + HermiT
#   add-subclass --child :X --parent :NotThere  -> refused (exit 1), nothing written

# 3) sync the validated edits back into WebProtégé
wp apply-edits my-ontology -f "$F" -m "add Pump + drives"
```

> **Keep a canonical file as the source of truth.** Prefer editing the ontology file you
> already control (e.g. in git) and using `apply-edits` to *push* to WebProtégé for viewing.
> Round-tripping *through* WebProtégé is lossy: its export mangles any literal containing `@`
> (emails become invalid language-tagged literals), so building edits on a fresh `wp export` can
> corrupt those values. `onto`'s load sanitizer repairs these on the way in (both bare emails and
> emails embedded mid-text), but the canonical-file route avoids the problem entirely. See
> [`docs/strengthening.md`](docs/strengthening.md).

`onto` commands: `info`, `add-class`, `add-subclass`, `add-objprop`, `add-dataprop`,
`add-individual`, `add-annotation`, `add-disjoint`, `add-characteristic`, `add-inverse`,
`remove`, `remove-subclass`, `validate [--reason]`, `query "<SPARQL>"`, `diff <other>`. IRIs accept
full `http(s)://…`, prefixed names bound in the file (`rdfs:comment`, `ex:Foo`), or `:Name`/`Name`
against the default namespace.

### Verifying a round-trip (`onto diff`)

The WebProtégé boundary is **lossy by design** (RDF↔OWL isn't 1:1) and the losses are *silent* —
the export still parses and the counts look healthy. `onto diff` makes them impossible to miss: it
structurally compares two ontology files and **exits non-zero if any assertion in the first is
missing from the second**.

```bash
# round-trip a project and verify nothing was dropped
wp export my-kb -F Turtle -o rt.zip && unzip -o rt.zip -d rt
onto diff canonical.ttl "$(find rt -name '*.ttl')"   # exit 1 + report if WebProtégé lost anything
```

It diffs bnode-free triples exactly, compares blank-node structures (reification, lists,
restrictions) by per-predicate count, and explicitly flags dropped RDF reification. Two known-lossy
cases it catches automatically: `@`-literal mangling (if the sanitizer ever misses one) and
**RDF reification** — WebProtégé/OWLAPI silently drops `rdf:subject/predicate/object`, orphaning
provenance (`docs/issues.md` #14). `onto info`/`validate` also warn when a file contains reification.

Axiom hardening (disjointness, property characteristics) goes through the same checked path:

```bash
# 2 classes -> owl:disjointWith ; 3+ -> a single owl:AllDisjointClasses axiom
.venv/bin/python onto.py add-disjoint "$F" --classes :Cat :Dog :Fish
# functional | inverse-functional | transitive | symmetric | asymmetric | reflexive | irreflexive
.venv/bin/python onto.py add-characteristic "$F" --prop :age      --type functional
.venv/bin/python onto.py add-characteristic "$F" --prop :sibling  --type symmetric
.venv/bin/python onto.py add-inverse        "$F" --prop :parentOf --inverse :childOf
#   each refuses to characterize/relate a property or class that isn't declared first.
```

These survive the `apply-edits` round-trip intact: WebProtégé diffs by OWL *axiom* (not triple),
so adding the three axioms above shows up as exactly 3 changes, and a re-`export` returns the
`AllDisjointClasses` / `FunctionalProperty` / `SymmetricProperty` assertions unchanged.

Debug a flow visually:

```bash
wp --headed --debug-dir ./debug create demo -f ontology.owl
```

## As a library

```js
import { WebProtegeClient } from 'webprotege-cli/src/wp.js';

const wp = new WebProtegeClient({ url: 'http://localhost:5000' });
await wp.open();
await wp.signIn({ user: 'alice', password: '…' });
await wp.createProject({ name: 'kb', file: 'kb.owl' });
console.log(await wp.listProjects());
await wp.exportProject({ name: 'kb', format: 'Turtle', out: 'kb.ttl.zip' });
await wp.close();
```

## Status / scope

Working: `signup`, `login`, `projects`, `create` (from file), `export`, `apply-edits`
(push an edited ontology back as a diff/revision via *Apply External Edits*). Selectors are
pinned to WebProtégé `4.0.0-beta-3` — pin the image to keep them valid.

**Editing approach (hybrid):** rather than have an LLM rewrite raw Turtle (hallucination-prone),
edits go through `onto` — structured, validated delta operations with existence checks + an
optional HermiT consistency pass — and `apply-edits` syncs the result back into the live
project. Both halves work today (see "Editing ontologies safely" above). Offline engine test:
`.venv/bin/python test/onto_test.py`.

Roadmap and known limits: [`docs/`](docs/) (`current_status.md`, `todo.md`, `issues.md`).

## License

MIT — see [LICENSE](LICENSE).
