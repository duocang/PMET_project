// Unit tests for useAdminStore (apps/pmet_frontend/lib/adminStore.ts).
//
// Why: the store is the single source of truth for "am I logged in as
// admin" — NavBar conditional rendering, the /admin gate, and the
// /tasks page all read from it. A refactor that quietly changes the
// {isAdmin, checked} semantics (e.g. starting with checked=true) would
// flash the Admin nav tab to every visitor for a frame before the
// /admin/me fetch resolved. These cases pin the contract: initial
// state hides the tab, setStatus marks the check complete, reset
// goes back to the initial state.
//
// Run: cd apps/pmet_frontend && npm run test:unit

import assert from 'node:assert/strict';

import { useAdminStore } from '../lib/adminStore';

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

const initial = useAdminStore.getState();
const reset = () => useAdminStore.setState(initial, /*replace=*/ true);

test('initial state is unchecked and not admin', () => {
  reset();
  const s = useAdminStore.getState();
  assert.strictEqual(s.isAdmin, false);
  assert.strictEqual(s.checked, false,
    'checked starts false so consumers can skip rendering until /me resolves');
});

test('setStatus(true) marks checked and flips isAdmin', () => {
  reset();
  useAdminStore.getState().setStatus(true);
  const s = useAdminStore.getState();
  assert.strictEqual(s.isAdmin, true);
  assert.strictEqual(s.checked, true);
});

test('setStatus(false) marks checked but leaves isAdmin false', () => {
  reset();
  useAdminStore.getState().setStatus(false);
  const s = useAdminStore.getState();
  assert.strictEqual(s.isAdmin, false);
  assert.strictEqual(s.checked, true,
    'a confirmed "not admin" result must still set checked=true');
});

test('reset returns to initial state after a successful login', () => {
  reset();
  useAdminStore.getState().setStatus(true);
  useAdminStore.getState().reset();
  const s = useAdminStore.getState();
  assert.strictEqual(s.isAdmin, false);
  assert.strictEqual(s.checked, false,
    'reset is for logout — nav must hide the Admin tab until /me re-confirms');
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
console.log(`\n[admin_store] ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
