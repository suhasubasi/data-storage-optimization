import type { Asset, StorageScenario } from "@contracts/ts/dso-contracts";

/** Independently check the backend's conservative storage equation. Never clamp losses to savings. */
export function checkScenario(s: StorageScenario) {
  const after = s.kept_original_bytes + s.derived_bytes + s.index_bytes;
  const pct = s.before_bytes ? ((s.before_bytes - after) / s.before_bytes) * 100 : null;
  const valid = [s.before_bytes, s.kept_original_bytes, s.derived_bytes, s.index_bytes, s.after_bytes]
    .every((n) => Number.isFinite(n) && n >= 0)
    && after === s.after_bytes
    && s.before_bytes - after === s.saved_bytes
    && (pct === null ? s.savings_pct === null : s.savings_pct !== null && Math.abs(pct - s.savings_pct) < 0.01);
  return { after, pct, valid };
}

/** Choose useful existing evidence without hard-coded files or synthetic demo data. */
export function selectEvidence(assets: Asset[]) {
  const real = assets.filter((a) => !a.test_data);
  const ready = real.filter((a) => a.status === "ready").sort((a, b) => b.bytes - a.bytes);
  return {
    recording: ready.find((a) => a.kind === "video"),
    document: ready.find((a) => a.kind === "document"),
    readyCount: ready.length,
    realCount: real.length,
  };
}
