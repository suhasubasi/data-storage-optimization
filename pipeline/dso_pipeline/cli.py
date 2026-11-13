"""CLI entry the backend job runner calls (interface frozen in contracts/CONTRACTS.md §4):

    python -m dso_pipeline process --asset-id a_01 --kind video \
        --input data/originals/a_01/event.mp4 --out data/derived/a_01

Exit 0 = data/derived/<id>/manifest.json written (atomically, last). Non-zero = failure; message on
stderr and in data/derived/<id>/error.json. Progress in data/derived/<id>/progress.json.
"""
import argparse
import re
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dso_pipeline",
        description="Local processing of one original (MP4 or PDF) into derived files + manifest.json. "
        "Never deletes or modifies the original. Processing alone saves no storage.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    proc = sub.add_parser("process", help="Process one original into derived files + manifest.json")
    proc.add_argument("--asset-id", required=True)
    proc.add_argument("--kind", required=True, choices=["video", "document"])
    proc.add_argument("--input", required=True, help="Path to the original (read-only)")
    proc.add_argument("--out", required=True, help="data/derived/<asset_id>/")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "process":
        return 2
    if not re.fullmatch(r"a_[A-Za-z0-9]+", args.asset_id):
        print(f"dso_pipeline: invalid asset id {args.asset_id!r} (expected a_<alnum>)", file=sys.stderr)
        return 2
    from .process import run  # deferred: keeps --help fast

    try:
        m = run(args.asset_id, args.kind, Path(args.input), Path(args.out))
    except Exception as e:  # noqa: BLE001
        print(f"dso_pipeline: failed: {e}", file=sys.stderr)
        return 1
    print(
        f"dso_pipeline: ok {m['asset_id']} kind={m['kind']} segments={len(m['segments'])} "
        f"frames={len(m['frames'])} slides={len(m['slides'])} derived_files={len(m['derived_files'])} "
        f"seconds={m['pipeline']['seconds']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
