// WebProtegeClient — drives a self-hosted WebProtégé (2019 monolithic image) through a
// headless browser. The 2019 image has no REST API and gates everything behind a GWT-RPC
// servlet with CHAP auth + custom serializers (see references/control-surface.md), so we let
// the app's own JavaScript do the protocol work and only script the UI.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const GWT_SETTLE_MS = 1200; // GWT renders after DOMContentLoaded; give it a beat

export class WebProtegeClient {
  /** @param {{url?:string, headless?:boolean, statePath?:string, slowMo?:number, debugDir?:string}} opts */
  constructor(opts = {}) {
    this.url = (opts.url || process.env.WP_URL || 'http://localhost:5000').replace(/\/$/, '');
    this.headless = opts.headless !== false;
    this.statePath = opts.statePath || process.env.WP_STATE || null;
    this.slowMo = opts.slowMo || 0;
    this.debugDir = opts.debugDir || null;
    this.browser = null;
    this.ctx = null;
    this.page = null;
  }

  async open() {
    this.browser = await chromium.launch({ headless: this.headless, slowMo: this.slowMo });
    const ctxOpts = { acceptDownloads: true };
    if (this.statePath && fs.existsSync(this.statePath)) ctxOpts.storageState = this.statePath;
    this.ctx = await this.browser.newContext(ctxOpts);
    this.page = await this.ctx.newPage();
    await this.goHome();
    return this;
  }

  async close() {
    if (this.browser) await this.browser.close();
    this.browser = this.ctx = this.page = null;
  }

  async goHome() {
    await this.page.goto(this.url + '/', { waitUntil: 'networkidle', timeout: 30000 });
    await this.page.waitForTimeout(GWT_SETTLE_MS);
  }

  async saveState() {
    if (!this.statePath) return;
    fs.mkdirSync(path.dirname(this.statePath), { recursive: true });
    await this.ctx.storageState({ path: this.statePath });
  }

  async _shot(name) {
    if (!this.debugDir) return;
    fs.mkdirSync(this.debugDir, { recursive: true });
    try { await this.page.screenshot({ path: path.join(this.debugDir, name + '.png'), fullPage: true }); } catch {}
  }

  // ---- auth ---------------------------------------------------------------

  /** True if the projects view is showing (i.e. we're authenticated). */
  async isSignedIn() {
    // The sign-in form shows a password field + "Sign In" button. Absence => signed in.
    const signInBtn = this.page.getByRole('button', { name: 'Sign In', exact: true });
    await this.page.waitForTimeout(300);
    return (await signInBtn.count()) === 0;
  }

  async signIn({ user, password }) {
    if (!user || !password) throw new Error('signIn needs { user, password }');
    await this.goHome();
    if (await this.isSignedIn()) return true;
    await this.page.locator('input[type=text]').first().fill(user);
    await this.page.locator('input[type=password]').first().fill(password);
    await this.page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await this.page.waitForTimeout(GWT_SETTLE_MS);
    const ok = await this.isSignedIn();
    if (!ok) { await this._shot('signin-failed'); throw new Error('sign-in failed (bad credentials or UI changed)'); }
    await this.saveState();
    return true;
  }

  async signUp({ user, email, password }) {
    if (!user || !email || !password) throw new Error('signUp needs { user, email, password }');
    await this.goHome();
    await this.page.getByText('Sign up for account', { exact: false }).first().click();
    await this.page.waitForTimeout(600);
    // Dialog "Create Account": inputs in order = [user, email, password(text), password(text)]
    const texts = this.page.locator('input[type=text]');
    const pwds = this.page.locator('input[type=password]');
    await texts.nth(0).fill(user);
    await texts.nth(1).fill(email);
    await pwds.nth(0).fill(password);
    await pwds.nth(1).fill(password);
    await this.page.getByRole('button', { name: 'Create Account', exact: true }).click();
    await this.page.waitForTimeout(GWT_SETTLE_MS);
    await this._shot('after-signup');
    return true;
  }

  /** Sign in; if that fails and an email is given, create the account then sign in. */
  async ensureSignedIn({ user, password, email }) {
    try {
      return await this.signIn({ user, password });
    } catch (e) {
      if (!email) throw e;
      await this.signUp({ user, email, password });
      return await this.signIn({ user, password });
    }
  }

  // ---- projects -----------------------------------------------------------
  // Selectors below are grounded in the live 4.0.0-beta-3 DOM:
  //   row   = .wp-project-list__rows__row
  //   name  = .wp-project-list__name-col
  //   menu  = per-row [title=Menu] (revealed on row hover) -> Open / Download / ...

  /** @returns {Promise<Array<{name:string, cells:string[]}>>} */
  async listProjects() {
    await this.goHome();
    if (!(await this.isSignedIn())) throw new Error('not signed in');
    await this.page.waitForTimeout(GWT_SETTLE_MS);
    const rows = this.page.locator('.wp-project-list__rows__row');
    const n = await rows.count();
    const out = [];
    for (let i = 0; i < n; i++) {
      const row = rows.nth(i);
      const name = (await row.locator('.wp-project-list__name-col').first().innerText().catch(() => '')).trim();
      if (!name) continue;
      const cells = (await row.locator('.wp-project-list__cell').allInnerTexts()).map((s) => s.trim()).filter(Boolean);
      out.push({ name, cells });
    }
    return out;
  }

  /**
   * Create a project from an OWL/RDF file (the "Create from existing sources" path).
   * @param {{name:string, file:string, description?:string, language?:string}} o
   */
  async createProject({ name, file, description = '', language = '' }) {
    if (!name) throw new Error('createProject needs a name');
    if (!file) throw new Error('createProject needs a file (this CLI creates from sources)');
    const abs = path.resolve(file);
    if (!fs.existsSync(abs)) throw new Error('file not found: ' + abs);
    await this.goHome();
    if (!(await this.isSignedIn())) throw new Error('not signed in');
    await this.page.getByRole('button', { name: 'Create New Project', exact: true }).first().click();
    await this.page.waitForTimeout(700);
    const texts = this.page.locator('input[type=text]');
    await texts.nth(0).fill(name);                          // Project name
    if (language) await texts.nth(1).fill(language);        // Language tag
    if (description) await this.page.locator('textarea').first().fill(description);
    await this.page.locator('input[type=file]').first().setInputFiles(abs);
    await this.page.waitForTimeout(600);
    // The dialog's confirm button shares the label "Create New Project"; it's the in-popup one.
    await this.page.getByRole('button', { name: 'Create New Project', exact: true }).last().click();
    // Upload + parse + create; WebProtégé then returns to the project list.
    await this.page.waitForFunction(() => location.hash.includes('projects/list'), null, { timeout: 60000 })
      .catch(() => {});
    await this.page.waitForTimeout(1500);
    await this._shot('after-create');
    const ok = (await this.listProjects()).some((p) => p.name === name);
    if (!ok) { await this._shot('create-unconfirmed'); throw new Error('project not visible after create: ' + name); }
    return { name };
  }

  /**
   * Download a project's ontology. WebProtégé serves a ZIP containing the serialized
   * ontology in the chosen syntax.
   * @param {{name:string, format?:string, out?:string}} o  format: RDF/XML|Turtle|OWL/XML|Manchester OWL Syntax|Functional OWL Syntax
   * @returns {Promise<{file:string, suggested:string}>}
   */
  async exportProject({ name, format = 'RDF/XML', out }) {
    if (!name) throw new Error('exportProject needs a project name');
    await this.goHome();
    if (!(await this.isSignedIn())) throw new Error('not signed in');
    await this.page.waitForTimeout(GWT_SETTLE_MS);
    const row = this.page.locator('.wp-project-list__rows__row', { hasText: name }).first();
    if ((await row.count()) === 0) throw new Error('project not found: ' + name);
    await row.locator('.wp-project-list__name-col').first().hover();
    await this.page.waitForTimeout(300);
    await row.locator('[title=Menu]').first().click();
    await this.page.getByText('Download', { exact: true }).first().click();
    await this.page.waitForTimeout(500);
    const fmt = this.page.locator('select').filter({ has: this.page.locator('option', { hasText: format }) }).first();
    if ((await fmt.count()) === 0) throw new Error('unknown format: ' + format);
    await fmt.selectOption({ label: format });
    const [dl] = await Promise.all([
      this.page.waitForEvent('download', { timeout: 60000 }),
      this.page.getByRole('button', { name: 'OK', exact: true }).click(),
    ]);
    const target = out || dl.suggestedFilename();
    fs.mkdirSync(path.dirname(path.resolve(target)), { recursive: true });
    await dl.saveAs(target);
    return { file: target, suggested: dl.suggestedFilename() };
  }
}

