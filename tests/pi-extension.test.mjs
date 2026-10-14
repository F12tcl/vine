/**
 * The shipped Pi extension is the one asset no Python test can exercise, and its commit/review
 * commands used to only *notify* text (a notification never reaches the model, so `/vine-review`
 * looked like it did nothing). This drives it against a stubbed `pi` object instead of a real
 * runtime: no model, no network, no credentials.
 *
 * Run with: npm run test:pi   (or: node --test tests/pi-extension.test.mjs)
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

import vineExtension from '../vine/assets/pi-extension.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Load an extension against a fake Pi and collect what it registered and sent. */
function loadExtension({ withSend = true, factory = vineExtension } = {}) {
  const commands = new Map();
  const handlers = new Map();
  const sent = [];
  const notices = [];
  const pi = {
    on: (name, handler) => {
      handlers.set(name, handler);
      return () => {};
    },
    registerCommand: (name, spec) => commands.set(name, spec),
  };
  if (withSend) {
    pi.sendUserMessage = (content, options) => sent.push({ content, options });
  }
  factory(pi);
  return {
    commands,
    handlers,
    sent,
    notices,
    ctx: { ui: { notify: (text) => notices.push(text) } },
  };
}

/** A throwaway project directory, removed when the test ends. */
function tempProject(t, { config = {}, memory = null } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vine-pi-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, '.vine'), { recursive: true });
  fs.writeFileSync(path.join(root, '.vine', 'config.json'), JSON.stringify(config));
  if (memory) {
    fs.mkdirSync(path.join(root, '.vine', '.mem'), { recursive: true });
    fs.writeFileSync(path.join(root, '.vine', '.mem', 'sessions.json'), JSON.stringify(memory));
  }
  return root;
}

/** The extension reads the project from the working directory, like the CLI does. */
async function inProject(root, fn) {
  const previous = process.cwd();
  process.chdir(root);
  try {
    return await fn();
  } finally {
    process.chdir(previous);
  }
}

const CACHED_SESSIONS = {
  '/fake/older.jsonl': {
    id: 'older',
    source: 'claude',
    name: 'Fix the parser',
    started: '2025-10-11T09:00:00Z',
    ended: '2025-10-11T10:00:00Z',
    last_user: 'why does it drop lines?',
    summary: 'root-caused a readline bug',
  },
  '/fake/newer.jsonl': {
    id: 'newer',
    source: 'pi',
    name: 'Ship memory',
    started: '2025-10-12T09:00:00Z',
    ended: '2025-10-12T10:00:00Z',
    last_user: 'add cross-session memory',
    summary: '',
  },
};

const memoryCache = (sessions) => ({
  __version: 1,
  refreshed_at: '2025-10-13T00:00:00Z',
  sessions,
});

test('the extension registers the three documented commands', () => {
  const { commands } = loadExtension();
  assert.deepEqual([...commands.keys()].sort(), ['grill', 'vine', 'vine-review']);
  for (const spec of commands.values()) {
    assert.equal(typeof spec.handler, 'function');
    assert.ok(spec.description, 'every command needs a description for discovery');
  }
});

test('/vine-review hands the review to the agent instead of printing it', async () => {
  const { commands, sent, notices, ctx } = loadExtension();
  await commands.get('vine-review').handler('', ctx);

  assert.equal(sent.length, 1, 'a turn must actually be started');
  assert.equal(sent[0].content, '/skill:review');
  assert.equal(sent[0].options.expandPromptTemplates, true, 'the skill must be expanded server-side');
  assert.deepEqual(notices, [], 'nothing should be merely notified');
});

test('/vine review is the same action as /vine-review', async () => {
  const { commands, sent, ctx } = loadExtension();
  await commands.get('vine').handler('review', ctx);

  assert.equal(sent.length, 1);
  assert.equal(sent[0].content, '/skill:review');
});

test('/grill hands the brainstorming round to the agent', async () => {
  const { commands, sent, ctx } = loadExtension();
  await commands.get('grill').handler('', ctx);

  assert.equal(sent.length, 1);
  assert.equal(sent[0].content, '/skill:grill');
  assert.equal(sent[0].options.expandPromptTemplates, true);
});

test('without sendUserMessage the commands degrade to a hint', async () => {
  for (const [command, args] of [
    ['vine-review', ''],
    ['grill', ''],
    ['vine', 'review'],
  ]) {
    const { commands, notices, ctx } = loadExtension({ withSend: false });
    await commands.get(command).handler(args, ctx);
    assert.equal(notices.length, 1, `${command} must still say something`);
    assert.ok(notices[0].length > 0);
  }
});

test('before_agent_start recalls this project’s previous sessions', async (t) => {
  const { handlers } = loadExtension();
  const root = tempProject(t, { memory: memoryCache(CACHED_SESSIONS) });

  const result = await inProject(root, () =>
    handlers.get('before_agent_start')({ systemPrompt: 'BASE' }),
  );

  assert.match(result.systemPrompt, /### Previous Sessions In This Project/);
  assert.ok(result.systemPrompt.includes('add cross-session memory'));
  assert.ok(result.systemPrompt.includes('root-caused a readline bug'));
  assert.ok(
    result.systemPrompt.indexOf('add cross-session memory') <
      result.systemPrompt.indexOf('why does it drop lines?'),
    'the newest session must come first',
  );
});

test('mem_recent bounds recall and mem_inject: false turns memory off', async (t) => {
  const { handlers } = loadExtension();
  const limited = tempProject(t, {
    config: { mem_recent: 1 },
    memory: memoryCache(CACHED_SESSIONS),
  });

  const result = await inProject(limited, () =>
    handlers.get('before_agent_start')({ systemPrompt: 'BASE' }),
  );

  assert.equal(result.systemPrompt.match(/^- `/gm).length, 1);
  assert.ok(result.systemPrompt.includes('add cross-session memory'));
  assert.ok(!result.systemPrompt.includes('why does it drop lines?'));

  const { handlers: offHandlers } = loadExtension();
  const off = tempProject(t, {
    config: { mem_inject: false },
    memory: memoryCache(CACHED_SESSIONS),
  });

  const offResult = await inProject(off, () =>
    offHandlers.get('before_agent_start')({ systemPrompt: 'BASE' }),
  );

  assert.ok(!offResult.systemPrompt.includes('Previous Sessions'));
});

test('a project without a memory cache is unaffected', async (t) => {
  const { handlers } = loadExtension();
  const root = tempProject(t);

  const result = await inProject(root, () =>
    handlers.get('before_agent_start')({ systemPrompt: 'BASE' }),
  );

  assert.ok(!result.systemPrompt.includes('Previous Sessions'));
  assert.ok(result.systemPrompt.includes('Vine Status: Free Session'));
});

test('ponytail_mode lite and ultra reach the model; full is not noise', async (t) => {
  const contextFor = async (config) => {
    const { handlers } = loadExtension();
    const root = tempProject(t, { config });
    const result = await inProject(root, () =>
      handlers.get('before_agent_start')({ systemPrompt: 'BASE' }),
    );
    return result.systemPrompt;
  };

  assert.match(await contextFor({ ponytail_mode: 'lite' }), /Ponytail level: `lite`/);
  assert.match(
    await contextFor({ ponytail_mode: 'ultra' }),
    /push back on any part the need does not justify/,
  );

  // `full` is the behaviour AGENTS.md already states, and an unknown level is not ours
  // to interpret, so neither may add a line the model has to read.
  assert.ok(!(await contextFor({ ponytail_mode: 'full' })).includes('Ponytail level'));
  assert.ok(!(await contextFor({ ponytail_mode: 'sideways' })).includes('Ponytail level'));
});

function pythonInterpreter() {
  const py = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  return spawnSync(py, ['-c', 'pass'], { encoding: 'utf8' }).status === 0 ? py : null;
}

const STALE = '1999-01-01T00:00:00+00:00';

/** A cache whose `refreshed_at` only moves if the CLI really ran in this project. */
function staleCachePath(root) {
  const cachePath = path.join(root, '.vine', '.mem', 'sessions.json');
  fs.mkdirSync(path.dirname(cachePath), { recursive: true });
  fs.writeFileSync(
    cachePath,
    JSON.stringify({ __version: 1, refreshed_at: STALE, sessions: {} }),
  );
  return cachePath;
}

const refreshedAt = (cachePath) => JSON.parse(fs.readFileSync(cachePath, 'utf8')).refreshed_at;

/** Point the CLI at an empty host directory: never read the developer's real history. */
function isolatedHostDir(t, source) {
  const key = `VINE_MEM_${source.toUpperCase()}_DIR`;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `vine-pi-${source}-`));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  process.env[key] = dir;
  t.after(() => delete process.env[key]);
  return dir;
}

/** What `vine init --pi` produces: the extension living inside the project, not the package. */
async function installCopiedExtension(root) {
  const copy = path.join(root, '.pi', 'extensions', 'vine.js');
  fs.mkdirSync(path.dirname(copy), { recursive: true });
  fs.copyFileSync(path.join(REPO_ROOT, 'vine', 'assets', 'pi-extension.js'), copy);
  const loaded = await import(pathToFileURL(copy).href);
  return loaded.default;
}

test('session_start indexes the session that just ended', async (t) => {
  if (!pythonInterpreter()) return t.skip('no python interpreter to run the CLI with');

  const root = tempProject(t, { config: { platforms: ['claude'] } });
  const cachePath = staleCachePath(root);
  isolatedHostDir(t, 'claude');

  const { handlers, notices, ctx } = loadExtension();
  await inProject(root, () => handlers.get('session_start')({}, ctx));

  assert.notEqual(refreshedAt(cachePath), STALE, 'session_start must run `vine mem refresh`');
  assert.equal(notices.length, 1, 'and still greet the session');
});

test('a copied extension reaches the CLI through .vine/.package-path', async (t) => {
  if (!pythonInterpreter()) return t.skip('no python interpreter to run the CLI with');

  const root = tempProject(t, { config: { platforms: ['claude'] } });
  fs.writeFileSync(path.join(root, '.vine', '.package-path'), REPO_ROOT);
  const cachePath = staleCachePath(root);
  isolatedHostDir(t, 'claude');

  const copied = await installCopiedExtension(root);
  const { handlers, ctx } = loadExtension({ factory: copied });
  await inProject(root, () => handlers.get('session_start')({}, ctx));

  assert.notEqual(
    refreshedAt(cachePath),
    STALE,
    'the copy cannot walk up to the package, so the pointer must be used instead',
  );
});

test('a pointer to something that is not vine is ignored', async (t) => {
  const root = tempProject(t, { config: { platforms: ['claude'] } });
  fs.writeFileSync(path.join(root, '.vine', '.package-path'), path.join(root, 'moved-away'));
  const cachePath = staleCachePath(root);

  const copied = await installCopiedExtension(root);
  const { handlers, notices, ctx } = loadExtension({ factory: copied });
  await inProject(root, () => handlers.get('session_start')({}, ctx));

  assert.equal(refreshedAt(cachePath), STALE, 'no CLI on this machine means no refresh');
  assert.equal(notices.length, 1, 'and the session still starts');
});
