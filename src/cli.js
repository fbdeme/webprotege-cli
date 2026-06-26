#!/usr/bin/env node
// webprotege-cli — drive a self-hosted WebProtégé instance from the command line.
//
// Auth/connection via flags or env:
//   WP_URL   (default http://localhost:5000)   --url
//   WP_USER                                     --user
//   WP_PASS                                     --pass
//   WP_EMAIL (only needed for `signup`)         --email
//   WP_STATE (storageState cache path)          --state
import { Command } from 'commander';
import { WebProtegeClient } from './wp.js';

const program = new Command();
program
  .name('wp')
  .description('Control a self-hosted WebProtégé (2019 image, no REST) via headless browser')
  .version('0.1.0')
  // Defaults intentionally come from env at run time (not declared here) so that
  // `--help` never prints a password pulled from WP_PASS.
  .option('--url <url>', 'WebProtégé base URL (env WP_URL)')
  .option('--user <name>', 'username (env WP_USER)')
  .option('--pass <password>', 'password (env WP_PASS)')
  .option('--state <path>', 'storageState cache file, skips re-login (env WP_STATE)')
  .option('--headed', 'show the browser (debug)', false)
  .option('--debug-dir <dir>', 'write screenshots here on key steps/failures');

function newClient() {
  const o = program.opts();
  return new WebProtegeClient({
    url: o.url || process.env.WP_URL || 'http://localhost:5000',
    headless: !o.headed,
    statePath: o.state || process.env.WP_STATE,
    debugDir: o.debugDir,
  });
}

function creds(extra = {}) {
  const o = program.opts();
  const c = { user: o.user || process.env.WP_USER, password: o.pass || process.env.WP_PASS, ...extra };
  if (!c.user || !c.password) {
    throw new Error('missing credentials: set --user/--pass or WP_USER/WP_PASS');
  }
  return c;
}

async function run(fn) {
  const wp = newClient();
  try {
    await wp.open();
    await fn(wp);
  } catch (e) {
    console.error('error:', e.message);
    process.exitCode = 1;
  } finally {
    await wp.close();
  }
}

program
  .command('signup')
  .description('create a local account (sign-up must be enabled on the instance)')
  .option('--email <email>', 'email address', process.env.WP_EMAIL)
  .action(async (opts) => {
    await run(async (wp) => {
      const c = creds({ email: opts.email });
      if (!c.email) throw new Error('signup needs --email or WP_EMAIL');
      await wp.signUp({ user: c.user, email: c.email, password: c.password });
      console.log(`signed up: ${c.user}`);
    });
  });

program
  .command('login')
  .description('sign in and cache the session to --state (if given)')
  .action(async () => {
    await run(async (wp) => {
      await wp.signIn(creds());
      console.log(`signed in: ${program.opts().user}`);
    });
  });

program
  .command('projects')
  .alias('ls')
  .description('list projects')
  .option('--json', 'output JSON', false)
  .action(async (opts) => {
    await run(async (wp) => {
      await wp.signIn(creds());
      const list = await wp.listProjects();
      if (opts.json) {
        console.log(JSON.stringify(list, null, 2));
      } else if (list.length === 0) {
        console.log('(no projects)');
      } else {
        for (const p of list) console.log('•', p.name);
      }
    });
  });

program
  .command('create <name>')
  .description('create a project from an OWL/RDF file')
  .requiredOption('-f, --file <path>', 'ontology file (.owl/.ttl/.rdf)')
  .option('-d, --desc <text>', 'description', '')
  .option('-l, --lang <tag>', 'default language tag', '')
  .action(async (name, opts) => {
    await run(async (wp) => {
      await wp.signIn(creds());
      await wp.createProject({ name, file: opts.file, description: opts.desc, language: opts.lang });
      console.log(`created project: ${name}  (from ${opts.file})`);
    });
  });

program
  .command('apply-edits <name>')
  .description('apply an externally-edited ontology to a project (server diffs add+remove, commits a new revision)')
  .requiredOption('-f, --file <path>', 'edited ontology file — MUST keep the same ontology IRI as the project')
  .option('-m, --message <text>', 'commit message for the revision')
  .action(async (name, opts) => {
    await run(async (wp) => {
      await wp.signIn(creds());
      const r = await wp.applyExternalEdits({ name, file: opts.file, message: opts.message });
      const n = r.changeCount != null ? ` (~${r.changeCount} change(s))` : '';
      console.log(`applied external edits to ${name}${n}`);
      if (r.changeCount === 0) {
        console.error('warning: 0 changes applied. The merge only diffs ontologies with the SAME '
          + 'ontology IRI — if the uploaded file\'s IRI differs from the project\'s, nothing is '
          + 'applied. Check `onto info <file>` vs the project, or the file may be identical.');
      }
    });
  });

program
  .command('export <name>')
  .description('download a project ontology (served as a ZIP)')
  .option('-F, --format <fmt>', 'RDF/XML | Turtle | OWL/XML | Manchester OWL Syntax | Functional OWL Syntax', 'RDF/XML')
  .option('-o, --out <path>', 'output file (default: server-suggested name)')
  .action(async (name, opts) => {
    await run(async (wp) => {
      await wp.signIn(creds());
      const r = await wp.exportProject({ name, format: opts.format, out: opts.out });
      console.log(`exported: ${r.file}`);
    });
  });

program.parseAsync();
