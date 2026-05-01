// Unit tests for the form-state actions on useSettingsStore
// (apps/pmet_frontend/lib/store.ts).
//
// Why: the bug we just fixed in commit 40e023b was that page-level
// useState in /submit was lost on SPA nav, taking species / motif-DB /
// file picks with it. We hoisted those into Zustand. params (IC
// threshold etc.) followed in the next commit. Without tests, a future
// refactor that subtly breaks the per-mode keying would re-regress
// silently. These cases pin the action contract: each updater touches
// only the targeted mode's slot, leaves the other two alone, and merges
// patches rather than overwriting.
//
// Run: cd apps/pmet_frontend && npm run test:unit

import assert from 'node:assert/strict';

// Zustand's persist middleware reaches for localStorage at module load
// time. Node has no localStorage, so the import below fails without a
// shim. Map-backed in-memory implementation is enough — the tests
// don't care about persistence semantics, only the in-memory state.
const _store = new Map<string, string>();
(globalThis as any).localStorage = {
  getItem: (k: string) => (_store.has(k) ? _store.get(k)! : null),
  setItem: (k: string, v: string) => { _store.set(k, v); },
  removeItem: (k: string) => { _store.delete(k); },
  clear: () => { _store.clear(); },
  key: (i: number) => Array.from(_store.keys())[i] ?? null,
  get length() { return _store.size; },
};

// Sync require so the module loads AFTER the localStorage shim above.
// (A top-level static `import` would hoist above the shim and
// blow up persist middleware at evaluation time.)
const { useSettingsStore } = require('../lib/store') as typeof import('../lib/store');

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

// Snapshot a fresh slate so each case starts deterministic.
const initial = useSettingsStore.getState();
const reset = () => useSettingsStore.setState(initial, /*replace=*/ true);

test('updateFilesForMode patches only the target mode', () => {
  reset();
  const fakeFile = new File(['x'], 'a.fasta', { type: 'text/plain' });
  useSettingsStore.getState().updateFilesForMode('promoters_pre', { genes: fakeFile });
  const s = useSettingsStore.getState();
  assert.strictEqual(s.filesByMode.promoters_pre.genes, fakeFile);
  assert.strictEqual(s.filesByMode.promoters.genes, null,
    'promoters mode untouched');
  assert.strictEqual(s.filesByMode.intervals.genes, null,
    'intervals mode untouched');
});

test('updateFilesForMode merges patch (does not overwrite siblings)', () => {
  reset();
  const f1 = new File(['x'], 'a.fasta');
  const f2 = new File(['y'], 'b.gff3');
  useSettingsStore.getState().updateFilesForMode('promoters', { fasta: f1 });
  useSettingsStore.getState().updateFilesForMode('promoters', { gff3: f2 });
  const m = useSettingsStore.getState().filesByMode.promoters;
  assert.strictEqual(m.fasta, f1, 'fasta still set after second patch');
  assert.strictEqual(m.gff3, f2, 'gff3 set by second patch');
});

test('updatePathsForMode mirrors the file-update contract', () => {
  reset();
  useSettingsStore.getState().updatePathsForMode('intervals', { fasta: '/tmp/a.fa' });
  const s = useSettingsStore.getState();
  assert.strictEqual(s.pathsByMode.intervals.fasta, '/tmp/a.fa');
  assert.strictEqual(s.pathsByMode.promoters.fasta, '');
  assert.strictEqual(s.pathsByMode.promoters_pre.fasta, '');
});

test('setSpeciesForMode is per-mode (no cross-bleed)', () => {
  reset();
  const { setSpeciesForMode } = useSettingsStore.getState();
  setSpeciesForMode('promoters_pre', 'Arabidopsis_thaliana');
  setSpeciesForMode('promoters', 'Solanum_lycopersicum');
  const s = useSettingsStore.getState();
  assert.strictEqual(s.speciesByMode.promoters_pre, 'Arabidopsis_thaliana');
  assert.strictEqual(s.speciesByMode.promoters, 'Solanum_lycopersicum');
  assert.strictEqual(s.speciesByMode.intervals, '',
    'intervals mode preserved at empty default');
});

test('updateParamsForMode patches without dropping defaults', () => {
  reset();
  // ic_threshold default is 24; change it on `promoters` only.
  useSettingsStore.getState().updateParamsForMode('promoters', { ic_threshold: 32 });
  const s = useSettingsStore.getState();
  assert.strictEqual(s.paramsByMode.promoters.ic_threshold, 32);
  // Other params on the same mode keep their defaults — the patch
  // is shallow-merged.
  assert.strictEqual(s.paramsByMode.promoters.max_match, 5);
  assert.strictEqual(s.paramsByMode.promoters.promoter_length, 1000);
  // Other modes are untouched.
  assert.strictEqual(s.paramsByMode.promoters_pre.ic_threshold, 24);
  assert.strictEqual(s.paramsByMode.intervals.ic_threshold, 24);
});

test('updateParamsForMode applies multi-key patches in one call', () => {
  reset();
  useSettingsStore.getState().updateParamsForMode('intervals', {
    promoter_length: 2000,
    fimo_threshold: 0.0001,
  });
  const m = useSettingsStore.getState().paramsByMode.intervals;
  assert.strictEqual(m.promoter_length, 2000);
  assert.strictEqual(m.fimo_threshold, 0.0001);
  // Untouched key keeps its default.
  assert.strictEqual(m.ic_threshold, 24);
});

test('resetSubmitForm wipes files / paths / species / params back to defaults', () => {
  reset();
  const { updateFilesForMode, updatePathsForMode, setSpeciesForMode,
          updateParamsForMode, resetSubmitForm } = useSettingsStore.getState();
  // Dirty all three modes.
  updateFilesForMode('promoters', { fasta: new File(['x'], 'a.fa') });
  updatePathsForMode('intervals', { meme: '/tmp/m.meme' });
  setSpeciesForMode('promoters_pre', 'Zea_mays');
  updateParamsForMode('promoters', { ic_threshold: 32 });

  resetSubmitForm();

  const s = useSettingsStore.getState();
  assert.strictEqual(s.filesByMode.promoters.fasta, null);
  assert.strictEqual(s.pathsByMode.intervals.meme, '');
  assert.strictEqual(s.speciesByMode.promoters_pre, '');
  assert.strictEqual(s.paramsByMode.promoters.ic_threshold, 24);
});

test('mode + email use plain setters (sanity)', () => {
  reset();
  const { setMode, setEmail } = useSettingsStore.getState();
  setMode('intervals');
  setEmail('user@example.com');
  const s = useSettingsStore.getState();
  assert.strictEqual(s.mode, 'intervals');
  assert.strictEqual(s.email, 'user@example.com');
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
console.log(`\n[settings_store] ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
