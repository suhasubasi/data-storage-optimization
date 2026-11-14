import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

// Compile the actual pure TypeScript module without a new test dependency or Node version requirement.
const source = readFileSync(new URL('../src/lib/impact.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { checkScenario, selectEvidence } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`);

const scenario = { before_bytes: 1000, kept_original_bytes: 200, derived_bytes: 90, index_bytes: 10, after_bytes: 300, saved_bytes: 700, savings_pct: 70 };

test('savings include all derived and index bytes', () => {
  assert.deepEqual(checkScenario(scenario), { after: 300, pct: 70, valid: true });
  assert.equal(checkScenario({ ...scenario, after_bytes: 290, saved_bytes: 710, savings_pct: 71 }).valid, false);
});

test('no originals means no percentage, even when the index occupies disk', () => {
  assert.deepEqual(checkScenario({ ...scenario, before_bytes: 0, kept_original_bytes: 0, derived_bytes: 0, after_bytes: 10, saved_bytes: -10, savings_pct: null }), { after: 10, pct: null, valid: true });
});

test('current storage overhead stays negative and is not a saving', () => {
  assert.deepEqual(checkScenario({ ...scenario, kept_original_bytes: 1000, after_bytes: 1100, saved_bytes: -100, savings_pct: -10 }), { after: 1100, pct: -10, valid: true });
});

test('reject inconsistent percentages and invalid byte counts', () => {
  assert.equal(checkScenario({ ...scenario, savings_pct: 99 }).valid, false);
  assert.equal(checkScenario({ ...scenario, index_bytes: -10 }).valid, false);
  assert.equal(checkScenario({ ...scenario, before_bytes: NaN }).valid, false);
});

test('evidence uses ready real assets and never synthetic or failed examples', () => {
  const assets = [
    { id: 'test', kind: 'video', bytes: 9000, status: 'ready', test_data: true },
    { id: 'failed', kind: 'video', bytes: 8000, status: 'failed' },
    { id: 'small', kind: 'video', bytes: 200, status: 'ready' },
    { id: 'large', kind: 'video', bytes: 500, status: 'ready' },
    { id: 'doc', kind: 'document', bytes: 50, status: 'ready' },
  ];
  const originalOrder = assets.map(a => a.id);
  const result = selectEvidence(assets);
  assert.equal(result.recording.id, 'large');
  assert.equal(result.document.id, 'doc');
  assert.equal(result.readyCount, 3);
  assert.equal(result.realCount, 4);
  assert.deepEqual(assets.map(a => a.id), originalOrder);
});

test('empty and unprocessed libraries have no invented evidence', () => {
  assert.deepEqual(selectEvidence([]), { recording: undefined, document: undefined, readyCount: 0, realCount: 0 });
  assert.equal(selectEvidence([{ id: 'pending', kind: 'video', status: 'uploaded' }]).recording, undefined);
});
