import { useEffect, useState } from "react";
import type { Settings, WhisperDevice, WhisperModelName } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { Badge, Callout, ErrorBox, Loading, PageHeader } from "../components/ui";

const MODEL_HELP: Record<WhisperModelName, string> = {
  small: "Fast baseline suitable for CPU or GPU.",
  "large-v3-turbo": "Best speed/accuracy balance on NVIDIA CUDA (~1.3 GB VRAM).",
  "large-v3": "Maximum transcription fidelity on GPU (~2.4 GB VRAM). Slow on CPU.",
};

const DEVICES: { value: WhisperDevice; label: string; help: string }[] = [
  { value: "auto", label: "Auto", help: "Use NVIDIA CUDA when available, otherwise CPU." },
  { value: "cuda", label: "NVIDIA GPU", help: "Require CUDA GPU; fail fast if unavailable." },
  { value: "cpu", label: "CPU only", help: "Force CPU execution regardless of GPU presence." },
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
  const changed = !!current && (current.whisper_model !== model || current.whisper_device !== device);

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

  return (
    <section className="page-stack page-settings">
      <PageHeader
        title="Runtime & speech-to-text settings"
        lead="Choose how future recordings are transcribed. Existing processed files stay as they are."
      />

      {s.loading && !s.data ? (
        <Loading label="Inspecting hardware & installed weights…" />
      ) : s.error ? (
        <ErrorBox error={s.error} onRetry={s.reload} />
      ) : current ? (
        <div className="split-2">
          <div className="card">
            <div className="card-head">
              <h3>Speech-to-text model (faster-whisper)</h3>
              {current.gpu_available === true ? (
                <Badge tone="green">NVIDIA CUDA detected</Badge>
              ) : current.gpu_available === false ? (
                <Badge tone="grey">CPU only host</Badge>
              ) : (
                <Badge tone="amber">Hardware probe inconclusive</Badge>
              )}
            </div>

            <div className="choice-stack" role="radiogroup" aria-label="Whisper model">
              {current.models.map((m) => (
                <label key={m.name} className={`choice-card ${model === m.name ? "on" : ""} ${m.installed ? "" : "disabled"}`}>
                  <input
                    type="radio"
                    name="model"
                    value={m.name}
                    checked={model === m.name}
                    disabled={!m.installed}
                    onChange={() => setModel(m.name)}
                  />
                  <div>
                    <div className="row-actions">
                      <strong>{m.label}</strong>
                      <code>{m.name}</code>
                      {m.installed ? <Badge tone="green">Installed</Badge> : <Badge tone="grey">Not downloaded</Badge>}
                    </div>
                    <p className="muted small">{MODEL_HELP[m.name]}</p>
                  </div>
                </label>
              ))}
            </div>

            <h3 style={{ marginTop: 20 }}>Compute device</h3>
            <div className="choice-stack" role="radiogroup" aria-label="Device">
              {DEVICES.map((d) => {
                const blocked = d.value === "cuda" && current.gpu_available === false;
                return (
                  <label key={d.value} className={`choice-card ${device === d.value ? "on" : ""} ${blocked ? "disabled" : ""}`}>
                    <input
                      type="radio"
                      name="device"
                      value={d.value}
                      checked={device === d.value}
                      disabled={blocked}
                      onChange={() => setDevice(d.value)}
                    />
                    <div>
                      <strong>{d.label}</strong>
                      <p className="muted small">{d.help}</p>
                    </div>
                  </label>
                );
              })}
            </div>

            <div className="row-actions" style={{ marginTop: 16 }}>
              <button type="button" className="btn btn-primary" disabled={saving || !changed} onClick={save}>
                {saving ? "Saving…" : "Save runtime settings"}
              </button>
            </div>
            {saveError && <ErrorBox error={saveError} />}
            {saved && !changed && (
              <Callout tone="safe" title="Configuration saved.">
                Upcoming jobs will use <code>{saved.whisper_model}</code> on <code>{saved.whisper_device}</code>.
              </Callout>
            )}
          </div>

          <div className="card">
            <h3>Effective runtime configuration</h3>
            <p>
              Next queued job runs <code>{current.effective_model}</code> on <code>{current.effective_device}</code>.
            </p>
            {current.env_overrides.length > 0 && (
              <Callout tone="warn" title="Environment override active.">
                {current.env_overrides.map((v) => <code key={v}>{v} </code>)} is forcing runtime behavior at backend startup and overrides saved UI choices.
              </Callout>
            )}
            <p className="muted small">
              Notice also: the standalone speaker diarizer (Silero VAD + Pyannote ONNX + SpeechBrain ECAPA + 2 fps visual playback classifier) runs locally alongside Whisper with zero saved audio clips.
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
