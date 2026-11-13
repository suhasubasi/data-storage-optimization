from dso_pipeline.cli import build_parser


def test_parser_accepts_contract_args():
    a = build_parser().parse_args(["process", "--asset-id", "a_01", "--kind", "video", "--input", "x.mp4", "--out", "d"])
    assert a.asset_id == "a_01" and a.kind == "video"
