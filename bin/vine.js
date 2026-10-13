#!/usr/bin/env node

/**
 * Vine CLI - Node.js binary launcher.
 *
 * Forwards commands to the bundled Vine engine with zero npm dependencies.
 */

const { spawn } = require('child_process');
const path = require('path');

function getPythonExecutable() {
  if (process.env.PYTHON) {
    return process.env.PYTHON;
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

const pythonBin = getPythonExecutable();
const packageRoot = path.resolve(__dirname, '..');
const args = process.argv.slice(2);

// Forward to python -m vine with packageRoot added to PYTHONPATH
const env = { ...process.env };
const existingPythonPath = env.PYTHONPATH || '';
env.PYTHONPATH = existingPythonPath
  ? `${packageRoot}${path.delimiter}${existingPythonPath}`
  : packageRoot;

const child = spawn(pythonBin, ['-m', 'vine', ...args], {
  cwd: process.cwd(),
  stdio: 'inherit',
  env,
});

child.on('error', (err) => {
  if (err.code === 'ENOENT') {
    console.error(`\x1b[31m[!] Error: Python runtime not found ('${pythonBin}').\x1b[0m`);
    console.error('    Vine requires Python 3.9+ installed and available on your PATH.');
    console.error('    You can also set the PYTHON environment variable, e.g.:');
    console.error('      export PYTHON=/path/to/python3');
  } else {
    console.error(err);
  }
  process.exit(1);
});

child.on('close', (code) => {
  process.exit(code ?? 0);
});
