// End-to-end smoke test against a live WebProtégé instance.
//
//   WP_URL=http://localhost:5000 WP_USER=alice WP_PASS=… [WP_EMAIL=…] node test/e2e.js
//
// If WP_EMAIL is set and the account doesn't exist, it is created first.
// Creates a uniquely-named project from test/fixtures/tiny.owl, verifies it lists,
// exports it as Turtle, and checks a non-empty ZIP came back.
import { WebProtegeClient } from '../src/wp.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixture = path.join(__dirname, 'fixtures', 'tiny.owl');
const user = process.env.WP_USER;
const password = process.env.WP_PASS;
const email = process.env.WP_EMAIL;

if (!user || !password) {
  console.error('set WP_USER and WP_PASS (and WP_EMAIL to auto-create the account)');
  process.exit(2);
}

const name = `wpcli-e2e-${process.pid}-${Number(process.hrtime.bigint() % 100000n)}`;
const outDir = process.env.WP_TEST_OUT || path.join(__dirname, '..', 'downloads');
const out = path.join(outDir, `${name}.ttl.zip`);

let failed = false;
const wp = new WebProtegeClient({ debugDir: process.env.WP_DEBUG_DIR });
try {
  await wp.open();
  await wp.ensureSignedIn({ user, password, email });
  console.log('✓ signed in as', user);

  await wp.createProject({ name, file: fixture, description: 'e2e smoke' });
  console.log('✓ created', name);

  const list = await wp.listProjects();
  if (!list.some((p) => p.name === name)) throw new Error('created project not in list');
  console.log(`✓ listed (${list.length} project(s))`);

  const r = await wp.exportProject({ name, format: 'Turtle', out });
  const size = fs.statSync(r.file).size;
  if (size <= 0) throw new Error('exported file is empty');
  if (!r.suggested.endsWith('.zip')) throw new Error('expected a .zip download, got ' + r.suggested);
  console.log(`✓ exported ${r.file} (${size} bytes, suggested ${r.suggested})`);

  console.log('\nPASS');
} catch (e) {
  failed = true;
  console.error('\nFAIL:', e.message);
} finally {
  await wp.close();
}
process.exit(failed ? 1 : 0);
