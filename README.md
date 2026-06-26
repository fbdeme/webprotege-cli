# webprotege-cli

Drive a **self-hosted [WebProtégé](https://github.com/protegeproject/webprotege)** instance
from the command line (and from agents) — create projects from an OWL/RDF file, list them, and
export them — without clicking through the web UI.

> Companion to the [`webprotege-selfhost`](https://github.com/fbdeme/webprotege-selfhost)
> runbook, which stands up the instance this CLI talks to.

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
npm install            # installs playwright
npx playwright install chromium
npm link               # optional: puts `wp` on your PATH
```

Requires Node ≥ 18 and a reachable WebProtégé instance with sign-up enabled (see the
`webprotege-selfhost` runbook for the MongoDB seeds that enable it).

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
```

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

Working: `signup`, `login`, `projects`, `create` (from file), `export`. Selectors are pinned to
WebProtégé `4.0.0-beta-3` — pin the image to keep them valid. Roadmap and known limits live in
[`docs/`](docs/) (`current_status.md`, `todo.md`, `issues.md`). Notably **not** yet covered:
fine-grained in-app entity edits (create class/property/individual, add axioms) and a raw-HTTP
fast-path for read-only exports.

## License

MIT — see [LICENSE](LICENSE).
