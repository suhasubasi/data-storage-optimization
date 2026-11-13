import subprocess
import sys

from dso_pipeline.cli import build_parser


def test_parser_accepts_contract_args():
    a = build_parser().parse_args(["process", "--asset-id", "a_01", "--kind", "video", "--input", "x.mp4", "--out", "d"])
    assert a.asset_id == "a_01" and a.kind == "video"


def test_help_works():
    for args in (["--help"], ["process", "--help"]):
        p = subprocess.run([sys.executable, "-m", "dso_pipeline", *args], capture_output=True, text=True)
        assert p.returncode == 0 and "usage" in p.stdout


def test_bad_asset_id_rejected():
    p = subprocess.run([sys.executable, "-m", "dso_pipeline", "process", "--asset-id", "../x", "--kind", "document",
                        "--input", "x.pdf", "--out", "d"], capture_output=True, text=True)
    assert p.returncode == 2
