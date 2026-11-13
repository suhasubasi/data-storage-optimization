import type { Asset, AssetKind } from "@contracts/ts/dso-contracts";
import { SOURCE_LABEL } from "../lib/format";

export function AssetPicker({
  assets, kind, value, onChange, label,
}: { assets: Asset[]; kind: AssetKind | "any"; value: string | undefined; onChange: (id: string) => void; label: string }) {
  const list = assets.filter((a) => kind === "any" || a.kind === kind);
  return (
    <label className="field inline">
      <span>{label}</span>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {!value && <option value="">Choose…</option>}
        {list.map((a) => (
          <option key={a.id} value={a.id}>
            {a.filename} · {SOURCE_LABEL[a.source_system]} · {a.owner}
            {a.status !== "ready" ? ` (${a.status})` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
