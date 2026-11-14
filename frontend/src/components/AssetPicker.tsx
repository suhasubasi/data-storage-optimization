import type { Asset, AssetKind } from "@contracts/ts/dso-contracts";
import { KIND_LABEL, SOURCE_LABEL } from "../lib/format";

export function AssetPicker({
  assets,
  kind,
  value,
  onChange,
  label = "File",
}: {
  assets: Asset[];
  kind: AssetKind | "any";
  value: string | undefined;
  onChange: (id: string) => void;
  label?: string;
}) {
  const list = assets.filter((a) => kind === "any" || a.kind === kind);
  return (
    <label className="picker-field">
      <span className="picker-label">{label}</span>
      <select className="select" value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={!list.length}>
        {list.length === 0 ? (
          <option value="">No processed {kind === "any" ? "files" : `${KIND_LABEL[kind].toLowerCase()}s`} yet</option>
        ) : (
          list.map((a) => (
            <option key={a.id} value={a.id}>
              {a.filename} · {SOURCE_LABEL[a.source_system]} · {a.owner} ({a.status})
            </option>
          ))
        )}
      </select>
    </label>
  );
}
