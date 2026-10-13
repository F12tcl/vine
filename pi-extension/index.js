/**
 * Vine Extension for Pi Coding Agent (@mariozechner/pi-coding-agent / @earendil-works/pi-coding-agent)
 *
 * Provides:
 * - Dynamic systemPrompt injection (active task + Ponytail ladder + living specs) via before_agent_start
 * - Session notification via session_start
 * - Slash commands: /vine, /grill, /vine-review
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

function findVineRoot(startDir = process.cwd()) {
  let curr = path.resolve(startDir);
  while (true) {
    if (fs.existsSync(path.join(curr, '.vine'))) {
      return curr;
    }
    const parent = path.dirname(curr);
    if (parent === curr) break;
    curr = parent;
  }
  return null;
}

function getVineContext(root) {
  if (!root) return null;
  const vineDir = path.join(root, '.vine');
  const cfgPath = path.join(vineDir, 'config.json');

  let activeTaskId = null;
  if (fs.existsSync(cfgPath)) {
    try {
      const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
      activeTaskId = cfg.active_task;
    } catch (e) {}
  }

  const parts = [];

  if (activeTaskId) {
    const taskJsonPath = path.join(vineDir, 'tasks', activeTaskId, 'task.json');
    const taskSpecPath = path.join(vineDir, 'tasks', activeTaskId, 'spec.md');

    if (fs.existsSync(taskJsonPath)) {
      try {
        const t = JSON.parse(fs.readFileSync(taskJsonPath, 'utf8'));
        parts.push(`## Active Task: ${t.title} (${t.status}) [ID: ${t.id}]`);
      } catch (e) {}
    }

    if (fs.existsSync(taskSpecPath)) {
      try {
        const specLines = fs.readFileSync(taskSpecPath, 'utf8').split('\n').slice(0, 40);
        parts.push('### Task Specification\n' + specLines.join('\n'));
      } catch (e) {}
    }
  } else {
    parts.push('## Vine Status: Free Session (No active task)');
  }

  // Conventions / Ponytail Ladder
  const convPath = path.join(vineDir, 'spec', 'conventions.md');
  if (fs.existsSync(convPath)) {
    try {
      const convLines = fs.readFileSync(convPath, 'utf8').split('\n').slice(0, 150);
      parts.push('### Engineering Conventions\n' + convLines.join('\n'));
    } catch (e) {}
  }

  return parts.join('\n\n');
}

function runVineCLI(args = [], cwd = process.cwd()) {
  const isWin = process.platform === 'win32';
  const py = process.env.PYTHON || (isWin ? 'python' : 'python3');
  const pkgRoot = path.resolve(import.meta.dirname, '..');
  const env = {
    ...process.env,
    PYTHONPATH: [pkgRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
  };

  const res = spawnSync(py, ['-m', 'vine', ...args], {
    cwd,
    encoding: 'utf8',
    env,
  });

  return (res.stdout || '') + (res.stderr || '');
}

export default function vineExtension(pi) {
  // 1. Session start notification
  pi.on('session_start', async (_event, ctx) => {
    const root = findVineRoot();
    if (root) {
      if (ctx?.ui?.notify) {
        ctx.ui.notify('Vine Harness active (Ponytail + Socratic Frontier + Specs)', 'info');
      }
    }
  });

  // 2. Dynamic context injection before agent runs
  pi.on('before_agent_start', async (event, _ctx) => {
    const root = findVineRoot();
    if (!root) return;

    const vineCtx = getVineContext(root);
    if (!vineCtx) return;

    const basePrompt = event.systemPrompt || '';
    const injection = `\n\n<!-- VINE_HARNESS_CONTEXT -->\n# Vine Project Guidelines & Active Task\n${vineCtx}\n<!-- END_VINE_HARNESS_CONTEXT -->\n`;

    return {
      systemPrompt: basePrompt + injection,
    };
  });

  // 3. Register Slash Commands
  pi.registerCommand('vine', {
    description: 'Vine lifecycle management: /vine [status | new <title> | done | list | review]',
    handler: async (args, ctx) => {
      const trimmed = (args || '').trim();
      const tokens = trimmed ? trimmed.split(/\s+/) : [];
      const sub = tokens[0] || 'status';

      if (sub === 'status' || !trimmed) {
        const out = runVineCLI(['task', 'status']);
        if (ctx?.ui?.notify) ctx.ui.notify(out, 'info');
        else console.log(out);
      } else if (sub === 'list') {
        const out = runVineCLI(['task', 'list']);
        console.log(out);
      } else if (sub === 'new') {
        const title = tokens.slice(1).join(' ') || 'Untitled Task';
        const out = runVineCLI(['task', 'new', title]);
        if (ctx?.ui?.notify) ctx.ui.notify(out, 'info');
        console.log(out);
      } else if (sub === 'done') {
        const out = runVineCLI(['task', 'done']);
        if (ctx?.ui?.notify) ctx.ui.notify(out, 'info');
        console.log(out);
      } else if (sub === 'review') {
        const out = runVineCLI(['review']);
        console.log(out);
      } else {
        const out = runVineCLI(tokens);
        console.log(out);
      }
    },
  });

  pi.registerCommand('grill', {
    description: 'Trigger Socratic Frontier brainstorming round for current requirements',
    handler: async (_args, ctx) => {
      const msg =
        'Entering Socratic Frontier Brainstorming (/grill). Inspect codebase facts first, then present unresolved decisions in rounds with recommended choices.';
      if (ctx?.ui?.notify) ctx.ui.notify(msg, 'info');
      console.log(msg);
    },
  });

  pi.registerCommand('vine-review', {
    description: 'Show Ponytail senior developer review checklist',
    handler: async (_args, _ctx) => {
      const out = runVineCLI(['review']);
      console.log(out);
    },
  });
}
