// REC v1.4: choose the Whisper model + device. Saved on the backend; used only by jobs started afterwards.
import { useEffect, useState } from "react";
import type { Settings, WhisperDevice, WhisperModelName } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { Badge, Callout, ErrorBox, Loading, PageHeader } from "../components/ui";

const MODEL_HELP: Record<WhisperModelName, string> = {
  small: "Fast. Good on any computer, also without a GPU. Some small word mistakes.",
  "large-v3-turbo": "Fast + accurate. Best choice with an NVIDIA GPU (used about 1.3 GB of GPU memory in our test). Slow on a CPU.",
  "large-v3": "Most accurate, but slower. Needs an NVIDIA GPU (used about 2.4 GB of GPU memory in our test). Very slow on a CPU.",
};

const DEVICES: { value: WhisperDevice; label: string; help: string }[] = [
  { value: "auto", label: "Auto", help: "Use the NVIDIA GPU if there is one, else the CPU." },
  { value: "cuda", label: "GPU", help: "NVIDIA GPU only. A job fails with a clear message if no GPU is usable." },
  { value: "cpu", label: "CPU", help: "Never use the GPU." },
];

export default function SettingsPage() {
  const s = useAsync(() => api.getSettings(), []);
  const [model, setModel] = useState<WhisperModelName>("small");
  const [device, setDevice] = useState<WhisperDevice>("cpu");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);
  const [saved, setSaved] = useState<Settings | null>(null);

  useEffect(() => {
    if (s.data) {
      setModel(s.data.whisper_model);
      setDevice(s.data.whisper_device);
    }
  }, [s.data]);

  const current = saved ?? s.data;

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      setSaved(await api.putSettings({ whisper_model: model, whisper_device: device }));
    } catch (e) {
      setSaveError(e as Error);
    } finally {
      setSaving(false);
    }
  }

  const changed = !!current && (current.whisper_model !== model || current.whisper_device !== device);

  return (
    <section>
      <PageHeader
        title="Settings"
        lead="Choose the speech-to-text model (Whisper) and where it runs. The choice is used for the next files you process. Files that are already processed are never re-processed automatically."
      />
      {s.loading && !s.data ? (
        <Loading />
      ) : s.error ? (
        <ErrorBox error={s.error} onRetry={s.reload} />
      ) : current ? (
        <>
          <div className="card">
            <div className="card-head">
              <h3>Speech-to-text model</h3>
              <span>
                GPU:{" "}
                {current.gpu_available === true ? (
                  <Badge tone="green">NVIDIA GPU found</Badge>
                ) : current.gpu_available === false ? (
                  <Badge tone="grey">no NVIDIA GPU</Badge>
                ) : (
                  <Badge tone="amber">could not check</Badge>
                )}
              </span>
            </div>
            <div className="choice-list" role="radiogroup" aria-label="Whisper model">
              {current.models.map((m) => (
                <label key={m.name} className={`choice ${model === m.name ? "on" : ""} ${m.installed ? "" : "off"}`}>
                  <input
                    type="radio"
                    name="model"
                    value={m.name}
                    checked={model === m.name}
                    disabled={!m.installed}
                    onChange={() => setModel(m.name)}
                  />
                  <span>
                    <b>{m.label}</b> <code>{m.name}</code>{" "}
                    {m.installed ? <Badge tone="green">installed</Badge> : <Badge tone="grey">not installed</Badge>}
                    <br />
                    <span className="muted small">
                      {MODEL_HELP[m.name]}
                      {!m.installed && <> To use it, download it first: see the README, section "Which Whisper model?".</>}
                    </span>
                  </span>
                </label>
              ))}
            </div>

            <h3>Device</h3>
            <div className="choice-list" role="radiogroup" aria-label="Device">
              {DEVICES.map((d) => {
                const blocked = d.value === "cuda" && current.gpu_available === false;
                return (
                  <label key={d.value} className={`choice ${device === d.value ? "on" : ""} ${blocked ? "off" : ""}`}>
                    <input
                      type="radio"
                      name="device"
                      value={d.value}
                      checked={device === d.value}
                      disabled={blocked}
                      onChange={() => setDevice(d.value)}
                    />
                    <span>
                      <b>{d.label}</b>
                      <br />
                      <span className="muted small">{d.help}</span>
                    </span>
                  </label>
                );
              })}
            </div>

            <div className="row-actions">
              <button className="btn primary" disabled={saving || !changed} onClick={save}>
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
            {saveError && <ErrorBox error={saveError} />}
            {saved && !changed && (
              <Callout tone="safe" title="Saved.">
                The next file you process (or re-process) uses <code>{saved.whisper_model}</code> on{" "}
                <code>{saved.whisper_device}</code>. Nothing was re-processed.
              </Callout>
            )}
          </div>

          <div className="card">
            <h3>What the next job will really use</h3>
            <p>
              Model <code>{current.effective_model}</code> · device <code>{current.effective_device}</code>
            </p>
            {current.env_overrides.length > 0 && (
              <Callout tone="warn" title="Set by the backend start command.">
                {current.env_overrides.map((v) => (
                  <code key={v}>{v} </code>
                ))}
                is set when the backend was started, and it wins over the choice above. Start the backend without it to use the
                choice saved here.
              </Callout>
            )}
            <p className="muted small">
              Each transcript records the model and device that made it (shown as "Model" on the recording page).
            </p>
          </div>
        </>
      ) : null}
    </section>
  );
}
