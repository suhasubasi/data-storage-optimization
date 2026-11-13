import { useState } from "react";
import { USE_MOCKS, absUrl } from "../api/config";
import { placeholderImage } from "../lib/placeholder";

interface Props {
  url: string | null | undefined;
  kind: "frame" | "slide";
  /** Text drawn on the mock placeholder (slide text or the transcript said on this frame). */
  title: string;
  sub?: string;
  alt: string;
  className?: string;
}

/** Real image from /files/... in live mode; labelled SVG placeholder in mock mode or if loading fails. */
export function MediaImage({ url, kind, title, sub, alt, className }: Props) {
  const [failed, setFailed] = useState(false);
  const usePlaceholder = USE_MOCKS || !url || failed;
  const src = usePlaceholder ? placeholderImage(kind, title, sub) : absUrl(url!);
  return (
    <img
      className={`media ${kind} ${className ?? ""}`}
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
