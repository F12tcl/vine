/**
 * Vine extension for the Pi coding agent.
 *
 * One file, used in two places:
 *  - shipped in the npm package and loaded from `package.json` -> `pi.extensions`
 *  - copied verbatim to `<project>/.pi/extensions/vine.js` by `vine init --pi`
 *
 * Provides:
 *  - shared project context via the installed standalone Python reader
 *  - session_start: bind host identity and notify
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

function bindSession(ctx) {
  const id = ctx?.sessionManager?.getSessionId?.();
  if (id) process.env.VINE_SESSION_ID = id;
}

function getVineContext(root) {
  const reader = path.join(root, '.vine', 'hooks', 'context.py');
  const py = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const res = spawnSync(py, [reader], { cwd: root, encoding: 'utf8', timeout: 10000, env: process.env });
  if (res.error || res.status !== 0) {
    return `[Vine context unavailable] ${res.error?.message || res.stderr || 'Run vine update to install the shared reader.'}`;
  }
  return res.stdout;
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

  // Session start only binds host identity; context reading never indexes chat logs.
  pi.on('session_start', async (_event, ctx) => {
    bindSession(ctx);
    const root = findVineRoot();
    if (!root) return;
    show(ctx, 'Vine Harness active (Ponytail + Socratic Frontier + Specs)');
  });

  // 2. Context injection before each run
  pi.on('before_agent_start', async (event, ctx) => {
    bindSession(ctx);
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

  // Shell tools and user-entered shell commands inherit this process's session identity.
  pi.on('tool_call', async (_event, ctx) => { bindSession(ctx); });
  pi.on('user_bash', async (_event, ctx) => { bindSession(ctx); });

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
      bindSession(ctx);
      const tokens = (args || '').trim() ? args.trim().split(/\s+/) : [];
      const sub = tokens[0] || 'status';
      if (sub === 'review') {
        dispatchSkill('review', ctx, 'Run in your terminal: vine review');
        return;
      }
      if (sub === 'done' || sub === 'new') {
        dispatchSkill(`vine ${args.trim()}`, ctx, 'Read the vine skill to plan or finish this task, then run the lifecycle command.');
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
