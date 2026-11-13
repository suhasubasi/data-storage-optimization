"""CLI entry the backend job runner calls (interface frozen in contracts/CONTRACTS.md §4):

    python -m dso_pipeline process --asset-id a_01 --kind video \
        --input data/originals/a_01/event.mp4 --out data/derived/a_01

Exit 0 = data/derived/<id>/manifest.json written (atomically, last). Non-zero = failure; message on
stderr and in data/derived/<id>/error.json. Optional progress in data/derived/<id>/progress.json.
SKELETON: argument parsing only. TODO Stream 3: video.py (ffmpeg + faster-whisper + key frames),
document.py (PyMuPDF + three hashes), manifest.py (validate with dso_contracts.models.Manifest).
"""
import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dso_pipeline")
    sub = p.add_subparsers(dest="command", required=True)
    proc = sub.add_parser("process", help="Process one original into derived files + manifest.json")
    proc.add_argument("--asset-id", required=True)
    proc.add_argument("--kind", required=True, choices=["video", "document"])
    proc.add_argument("--input", required=True, help="Path to the original (read-only)")
    proc.add_argument("--out", required=True, help="data/derived/<asset_id>/")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"dso_pipeline: '{args.command}' not implemented yet (Stream 3)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
