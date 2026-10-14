/**
 * Vine extension for the Pi coding agent.
 *
 * One file, used in two places:
 *  - shipped in the npm package and loaded from `package.json` -> `pi.extensions`
 *  - copied verbatim to `<project>/.pi/extensions/vine.js` by `vine init --pi`
 *
 * Provides:
 *  - systemPrompt context injection (active task + living specs + conventions + recent
 *    session digests)
 *  - session_start: refresh the memory cache, then notify
 *  - slash commands: /vine, /grill, /vine-review
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const EXTENSION_DIR = path.dirname(fileURLToPath(import.meta.url));

function findVineRoot(startDir = process.cwd()) {
  let curr = path.resolve(startDir);
  while (true) {
    if (fs.existsSync(path.join(curr, '.vine'))) return curr;
    const parent = path.dirname(curr);
    if (parent === curr) return null;
    curr = parent;
  }
}

function readConfig(vineDir) {
  const configPath = path.join(vineDir, 'config.json');
  if (!fs.existsSync(configPath)) return {};
  try {
    return JSON.parse(fs.readFileSync(configPath, 'utf8')) || {};
  } catch {
    return {};
  }
}

function readActiveTaskId(vineDir) {
  const pointer = path.join(vineDir, '.current-task');
  if (fs.existsSync(pointer)) {
    const value = fs.readFileSync(pointer, 'utf8').trim();
    if (value) return value;
  }
  return readConfig(vineDir).active_task || null;
}

/**
 * Digests of this project's recent agent sessions, newest first.
 *
 * Mirrors the wording of `session_start.py` so a session reads the same in every host.
 * Only reads the cache `vine mem` maintains; `mem_inject: false` in .vine/config.json
 * opts out of memory entirely.
 */
function getSessionMemory(vineDir) {
  const config = readConfig(vineDir);
  if (config.mem_inject === false) return null;

  const cachePath = path.join(vineDir, '.mem', 'sessions.json');
  if (!fs.existsSync(cachePath)) return null;
  let cache;
  try {
    cache = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
  } catch {
    return null;
  }

  const sessions = Object.values(cache?.sessions || {}).filter((s) => s && typeof s === 'object');
  if (!sessions.length) return null;

  const stamp = (s) => String(s.ended || s.started || '');
  const count = Number.isInteger(config.mem_recent) && config.mem_recent > 0 ? config.mem_recent : 3;
  const lines = ['### Previous Sessions In This Project'];
  for (const s of sessions.sort((a, b) => stamp(b).localeCompare(stamp(a))).slice(0, count)) {
    const when = stamp(s).slice(0, 16).replace('T', ' ');
    lines.push(`- \`${when}\` [${s.source || '?'}] ${s.name || s.id || 'session'}`);
    if (s.last_user) lines.push(`  last request: ${s.last_user}`);
    if (s.summary) lines.push(`  summary: ${s.summary}`);
  }
  lines.push('Recall more with `vine mem search <query>`; transcripts stay on this machine.');
  return lines.join('\n');
}

/**
 * The active Ponytail level, when it is not the default.
 *
 * `full` is the behaviour AGENTS.md already describes, so injecting it would be noise;
 * `lite` and `ultra` change what the agent should do and must be stated. Mirrors
 * `ponytail_level` in session_start.py so Pi reads the same context as Claude and Codex.
 */
function ponytailLevel(config) {
  const levels = {
    lite: 'build what was asked, and name the smaller option in one line instead of taking it',
    ultra: 'also question the request itself: push back on any part the need does not justify',
  };
  const level = config.ponytail_mode || 'full';
  return levels[level] ? `Ponytail level: \`${level}\` — ${levels[level]}.` : null;
}

function getVineContext(root) {
  if (!root) return null;
  const vineDir = path.join(root, '.vine');
  const parts = [];

  const activeTaskId = readActiveTaskId(vineDir);
  if (activeTaskId) {
    const taskDir = path.join(vineDir, 'tasks', activeTaskId);
    const taskJsonPath = path.join(taskDir, 'task.json');
    const taskSpecPath = path.join(taskDir, 'spec.md');

    if (fs.existsSync(taskJsonPath)) {
      try {
        const t = JSON.parse(fs.readFileSync(taskJsonPath, 'utf8'));
        parts.push(`## Active Task: ${t.title} (${t.status}) [ID: ${t.id}]`);
      } catch {}
    }
    if (fs.existsSync(taskSpecPath)) {
      try {
        const specLines = fs.readFileSync(taskSpecPath, 'utf8').split('\n').slice(0, 40);
        parts.push('### Task Specification\n' + specLines.join('\n'));
      } catch {}
    }
  } else {
    parts.push('## Vine Status: Free Session (No active task)');
  }

  const level = ponytailLevel(readConfig(vineDir));
  if (level) parts.push(level);

  const convPath = path.join(vineDir, 'spec', 'conventions.md');
  if (fs.existsSync(convPath)) {
    try {
      const convLines = fs.readFileSync(convPath, 'utf8').split('\n').slice(0, 150);
      parts.push('### Engineering Conventions\n' + convLines.join('\n'));
    } catch {}
  }

  const memory = getSessionMemory(vineDir);
  if (memory) parts.push(memory);

  return parts.join('\n\n');
}

/**
 * Locate the Vine package root so `python -m vine` can be spawned.
 *
 * The shipped extension sits inside the package and walks up to it. The copy `vine init --pi`
 * drops into a project cannot, and that is what `.vine/.package-path` (written by
 * `vine init`/`update`) is for. Returns null when neither works, in which case the
 * CLI-backed features degrade to a hint.
 */
function resolvePackageRoot(root) {
  let dir = EXTENSION_DIR;
  for (let i = 0; i < 6; i++) {
    if (fs.existsSync(path.join(dir, 'vine', '__main__.py'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  const pointer = root && path.join(root, '.vine', '.package-path');
  if (pointer && fs.existsSync(pointer)) {
    const recorded = fs.readFileSync(pointer, 'utf8').trim();
    if (recorded && fs.existsSync(path.join(recorded, 'vine', '__main__.py'))) return recorded;
  }
  return null;
}

function runVineCLI(args, packageRoot) {
  if (!packageRoot) return null;
  const py = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const env = {
    ...process.env,
    PYTHONPATH: [packageRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
  };
  const res = spawnSync(py, ['-m', 'vine', ...args], { cwd: process.cwd(), encoding: 'utf8', env });
  if (res.error) return `[!] ${res.error.message}`;
  return (res.stdout || '') + (res.stderr || '');
}

export default function vineExtension(pi) {
  const show = (ctx, text) => {
    if (ctx?.ui?.notify) ctx.ui.notify(text, 'info');
    else console.log(text);
  };

  // 1. Session start: index what just ended, then say hello
  pi.on('session_start', async (_event, ctx) => {
    const root = findVineRoot();
    if (!root) return;
    // The cache only moves when a `vine` command runs, so a session that just ended is
    // otherwise missing from the context injected below. Silent, and scoped to this project.
    if (readConfig(path.join(root, '.vine')).mem_inject !== false) {
      runVineCLI(['mem', 'refresh'], resolvePackageRoot(root));
    }
    show(ctx, 'Vine Harness active (Ponytail + Socratic Frontier + Specs)');
  });

  // 2. Context injection before each run
  pi.on('before_agent_start', async (event) => {
    const root = findVineRoot();
    if (!root) return;
    const vineCtx = getVineContext(root);
    if (!vineCtx) return;
    return {
      systemPrompt:
        (event.systemPrompt || '') +
        `\n\n<!-- VINE_HARNESS_CONTEXT -->\n# Vine Project Guidelines & Active Task\n${vineCtx}\n<!-- END_VINE_HARNESS_CONTEXT -->\n`,
    };
  });

  /**
   * Hand a skill to the agent as a user turn. Notifying the protocol text was a dead end:
   * a notification never reaches the model, so `/vine-review` looked like it did nothing.
   * Expansion turns `/skill:name` into that skill's own instructions.
   */
  const dispatchSkill = (skill, ctx, fallback) => {
    if (typeof pi.sendUserMessage === 'function') {
      pi.sendUserMessage(`/skill:${skill}`, { expandPromptTemplates: true });
      return;
    }
    show(ctx, fallback);
  };

  // 3. Slash commands
  pi.registerCommand('vine', {
    description: 'Vine lifecycle: /vine [status | list | new <title> | done | review]',
    handler: async (args, ctx) => {
      const tokens = (args || '').trim() ? args.trim().split(/\s+/) : [];
      const sub = tokens[0] || 'status';
      if (sub === 'review') {
        dispatchSkill('review', ctx, 'Run in your terminal: vine review');
        return;
      }
      const cliArgs = ['task', sub, ...tokens.slice(1)];
      const out = runVineCLI(cliArgs, resolvePackageRoot(findVineRoot()));
      show(ctx, out ?? `Run in your terminal: vine ${cliArgs.join(' ')}`);
    },
  });

  pi.registerCommand('grill', {
    description: 'Socratic Frontier brainstorming round for the current requirements',
    handler: async (_args, ctx) => {
      dispatchSkill(
        'grill',
        ctx,
        'Entering Socratic Frontier Brainstorming (/grill). Inspect codebase facts first, then present unresolved decisions in rounds with recommended choices.',
      );
    },
  });

  pi.registerCommand('vine-review', {
    description: 'Review the current change with the senior developer protocol',
    handler: async (_args, ctx) => {
      dispatchSkill('review', ctx, 'Run in your terminal: vine review');
    },
  });
}
