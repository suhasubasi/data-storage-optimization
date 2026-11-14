import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.85,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true as const,
});

export const IconLibrary = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><path d="M4 7h16M4 12h16M4 17h10" /><circle cx="18" cy="17" r="2.5" /></svg>
);
export const IconSearch = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
);
export const IconPlay = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><rect x="3" y="4" width="18" height="16" rx="2.5" /><path d="m10 9 5 3-5 3Z" fill="currentColor" stroke="none" /></svg>
);
export const IconDoc = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7Z" /><path d="M14 2v5h5M9 13h6M9 17h4" /></svg>
);
export const IconCopy = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>
);
export const IconChart = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><path d="M3 3v18h18" /><rect x="7" y="11" width="3.5" height="6" rx="0.8" /><rect x="13" y="6" width="3.5" height="11" rx="0.8" /></svg>
);
export const IconUsers = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 11a2.5 2.5 0 1 0 0-5M17.5 19a4.5 4.5 0 0 0-2.5-4" /></svg>
);
export const IconCode = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><path d="m8 8-4 4 4 4M16 8l4 4-4 4M13 5l-2 14" /></svg>
);
export const IconSettings = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" /></svg>
);
export const IconShield = ({ size = 16, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><path d="M12 3 4.5 6v5.5c0 4.9 3.2 8.7 7.5 9.8 4.3-1.1 7.5-4.9 7.5-9.8V6Z" /><path d="m9 12 2 2 4-4" /></svg>
);
export const IconUpload = ({ size = 18, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
);
export const IconDownload = ({ size = 15, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><path d="M12 3v12M7 10l5 5 5-5" /><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
);
export const IconMic = ({ size = 16, ...p }: IconProps) => (
  <svg {...base(size)} {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v3" /></svg>
);
