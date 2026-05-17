// Unit tests for lib/runtime.ts — pure-formatting helpers shared by
// the submit page (runtime estimate), task list (partial-result size
// label), task detail (error summary line), and several headers
// (humanized cluster / mode names).
//
// These functions have no side effects and no React state, so
// node-only tests in the existing tsx pattern are enough — no DOM, no
// network. They DO depend on a Translate callable for the
// runtime-range helper; we pass a tiny stub.
//
// Run: cd apps/pmet_frontend && npm run test:unit

import assert from 'node:assert/strict';

import {
  formatRuntimeRange,
  humanizeIdentifier,
  summarizeError,
  formatBytes,
} from '../lib/runtime';

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

// Tiny stub that returns the literal key — lets us verify the helper
// asked for the right key without depending on real translations.
const t = ((key: string) => `<${key}>`) as any;

// ---------------------------------------------------------------------
// formatRuntimeRange
// ---------------------------------------------------------------------
// Three bands: < 90 s → seconds, < 90 min → minutes, else → hours.
// The 90-unit boundary mirrors how humans read durations (you'd say
// "80 seconds" but "2 minutes", not "120 seconds").

test('formatRuntimeRange: under 90 s renders as seconds with rounding', () => {
  assert.strictEqual(
    formatRuntimeRange(30, 60, t),
    '30 <submit.estimate.range_sep> 60 <submit.estimate.unit.seconds>',
  );
});

test('formatRuntimeRange: 90 s boundary flips to minutes', () => {
  // hiSec = 90 → falls into the minutes branch (< 90 * 60 = 5400)
  assert.match(formatRuntimeRange(60, 90, t), /minutes/);
});

test('formatRuntimeRange: minutes branch covers up to 90 min', () => {
  // 30 min → 60 min: still minutes.
  assert.match(formatRuntimeRange(30 * 60, 60 * 60, t), /minutes/);
});

test('formatRuntimeRange: hour branch kicks in past 90 min', () => {
  // hiSec = 7200 (2 h) → hours branch (>= 5400 = 90 min)
  assert.match(formatRuntimeRange(3600, 7200, t), /hours/);
});

test('formatRuntimeRange: hours drops trailing ".0" for whole values', () => {
  // 1 h to 2 h → "1 hours" not "1.0 hours". Plurality stays "hours"
  // (the helper is locale-blind for now).
  const s = formatRuntimeRange(3600, 7200, t);
  assert.ok(!s.includes('1.0'), `should drop .0 suffix, got: ${s}`);
});

test('formatRuntimeRange: never shows zero — clamps to 1 in the seconds branch', () => {
  // A 0–0.4 s estimate would round to 0 without the clamp.
  const s = formatRuntimeRange(0.1, 0.4, t);
  assert.match(s, /^1 .* 1 /);
});

// ---------------------------------------------------------------------
// humanizeIdentifier
// ---------------------------------------------------------------------

test('humanizeIdentifier: underscore → space', () => {
  assert.strictEqual(humanizeIdentifier('cluster_one_two'), 'cluster one two');
});

test('humanizeIdentifier: null / undefined / empty all become ""', () => {
  assert.strictEqual(humanizeIdentifier(null), '');
  assert.strictEqual(humanizeIdentifier(undefined), '');
  assert.strictEqual(humanizeIdentifier(''), '');
});

test('humanizeIdentifier: no underscore is a no-op', () => {
  assert.strictEqual(humanizeIdentifier('plain'), 'plain');
});

// ---------------------------------------------------------------------
// summarizeError
// ---------------------------------------------------------------------
// summarizeError walks the lines and surfaces the first informative
// one — preferring "ERROR ...", then "!...", then "Command failed: ..."

test('summarizeError: surfaces the first ERROR line', () => {
  const msg = `
some preamble text
ERROR: motif universe is empty
... lots of R noise here ...
`.trim();
  assert.strictEqual(summarizeError(msg), 'ERROR: motif universe is empty');
});

test('summarizeError: falls back to a "!" line when no ERROR is present', () => {
  const msg = `
random noise
! could not allocate memory
trailing line
`.trim();
  assert.strictEqual(summarizeError(msg), '! could not allocate memory');
});

test('summarizeError: falls back to "Command failed" when first two patterns miss', () => {
  const msg = 'Command failed: bedtools intersect returned non-zero';
  assert.strictEqual(summarizeError(msg), 'Command failed: bedtools intersect returned non-zero');
});

test('summarizeError: returns first non-empty line when no patterns match', () => {
  assert.strictEqual(summarizeError('  \nbenign output\nanother'), 'benign output');
});

test('summarizeError: truncates lines longer than 140 chars with an ellipsis', () => {
  const long = 'ERROR: ' + 'x'.repeat(300);
  const out = summarizeError(long);
  assert.strictEqual(out.length, 138, `expected 137 + ellipsis = 138 chars, got ${out.length}`);
  assert.ok(out.endsWith('…'), 'should end with single-char ellipsis');
});

test('summarizeError: empty input returns empty string (no crash)', () => {
  assert.strictEqual(summarizeError(''), '');
  assert.strictEqual(summarizeError('\n\n  \n'), '');
});

// ---------------------------------------------------------------------
// formatBytes — partial-result download size labels
// ---------------------------------------------------------------------
// Uses base-1024 division ("KB"/"MB"/"GB" labels with SI capitalization
// per the helper's stated trade-off). Tests are precise about
// significant figures since the UI hangs labels on these.

test('formatBytes: null / undefined / negative / NaN → empty string', () => {
  assert.strictEqual(formatBytes(null), '');
  assert.strictEqual(formatBytes(undefined), '');
  assert.strictEqual(formatBytes(-1), '');
  assert.strictEqual(formatBytes(NaN), '');
});

test('formatBytes: < 1 KB shows raw bytes', () => {
  assert.strictEqual(formatBytes(0), '0 B');
  assert.strictEqual(formatBytes(512), '512 B');
});

test('formatBytes: KB branch — 1 decimal under 10, integer above', () => {
  assert.strictEqual(formatBytes(1024), '1.0 KB');
  assert.strictEqual(formatBytes(9 * 1024 + 500), '9.5 KB');
  assert.strictEqual(formatBytes(50 * 1024), '50 KB');
});

test('formatBytes: MB branch — same decimal rule', () => {
  assert.strictEqual(formatBytes(1024 * 1024), '1.0 MB');
  assert.strictEqual(formatBytes(15 * 1024 * 1024), '15 MB');
});

test('formatBytes: GB branch — 2 decimals under 10, 1 decimal above', () => {
  assert.strictEqual(formatBytes(1024 ** 3), '1.00 GB');
  assert.strictEqual(formatBytes(25 * 1024 ** 3), '25.0 GB');
});

test('formatBytes: ~993 MB partial-result example matches the README expectation', () => {
  // The README quotes "993 MB" for random_genes_top_N CIS-BP2 output.
  // 993 * 1024 * 1024 bytes should render exactly "993 MB".
  assert.strictEqual(formatBytes(993 * 1024 * 1024), '993 MB');
});

// Run all and report.
let passed = 0, failed = 0;
for (const t of tests) {
  try {
    t.fn();
    console.log('  ok   ' + t.name);
    passed++;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error('  FAIL ' + t.name + ': ' + msg);
    failed++;
  }
}
console.log(`\n[runtime] ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
