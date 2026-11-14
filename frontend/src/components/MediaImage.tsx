import { useEffect, useState } from "react";
import { absUrl } from "../api/config";
import { unavailableImage } from "../lib/placeholder";

interface Props {
  url: string | null | undefined;
  kind: "frame" | "slide";
  title: string;
  sub?: string;
  alt: string;
  className?: string;
}

export function MediaImage({ url, kind, title, sub, alt, className }: Props) {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [url]);

  const missing = !url || failed;
  const src = missing ? unavailableImage(kind, sub ?? "") : absUrl(url!);
  return (
    <img
      className={`media-img media-${kind} ${className ?? ""}`}
      src={src}
      alt={alt}
      title={title}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
