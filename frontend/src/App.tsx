// Blank shell only: layout + nav for the 8 screens on the design Page. Stream 1 owns everything here.
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { USE_MOCKS } from "./api/config";
import Placeholder from "./pages/Placeholder";

const SCREENS = [
  { path: "library", label: "Library", note: "Upload with source label and owner, status per file, original vs derived size" },
  { path: "recording", label: "Recording view", note: "Video player (original kept), frame strip, transcript; click to jump" },
  { path: "document", label: "Document view", note: "Slide grid with hashes; badges for 'also in X' and 'similar to X'" },
  { path: "search", label: "Search", note: "One box; each hit shows text, frame or slide image, file, timestamp" },
  { path: "duplicates", label: "Duplicates", note: "Exact / shared slide / similar groups with evidence and source systems" },
  { path: "storage", label: "Storage report", note: "Original vs derived bars, the four scenarios, formula and exclusions" },
  { path: "offboarding", label: "Offboarding review", note: "Pick an owner; each file: 'eligible for deletion after approval' or 'keep'" },
  { path: "export", label: "Export", note: "Pretty-printed JSON preview and download" },
];

export default function App() {
  return (
    <div className="shell">
      <aside className="nav">
        <h1>Data Storage Optimization</h1>
        <p className="badge">{USE_MOCKS ? "MOCK DATA" : "LIVE API"} · sources simulated</p>
        <nav>
          {SCREENS.map((s) => (
            <NavLink key={s.path} to={`/${s.path}`}>{s.label}</NavLink>
          ))}
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/library" replace />} />
          {SCREENS.map((s) => (
            <Route key={s.path} path={`/${s.path}/*`} element={<Placeholder title={s.label} note={s.note} />} />
          ))}
        </Routes>
      </main>
    </div>
  );
}
