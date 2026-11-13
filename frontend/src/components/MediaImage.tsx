import { useState } from "react";
import { absUrl } from "../api/config";
import { unavailableImage } from "../lib/placeholder";

interface Props {
  url: string | null | undefined;
  kind: "frame" | "slide";
  /** Tooltip text (slide text or the transcript said on this frame). */
  title: string;
  sub?: string;
  alt: string;
  className?: string;
}

/** Real image from /files/... (neutral "not available" card if it is missing or cannot load). */
export function MediaImage({ url, kind, title, sub, alt, className }: Props) {
  const [failed, setFailed] = useState(false);
  const missing = !url || failed;
  const src = missing ? unavailableImage(kind, sub ?? "") : absUrl(url!);
  return (
    <img
      className={`media ${kind} ${className ?? ""}`}
      src={src}
      alt={alt}
      title={title}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
