"""dataset(JSON) を index.html の <script id="dataset-json"> ブロックに埋め込む。

使い方:
    python scripts/embed_dataset.py --dataset data/dataset.json --html index.html
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
START_TAG = '<script type="application/json" id="dataset-json">'
END_TAG = "</script>"


def embed(dataset_path: Path, html_path: Path) -> None:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    compact = json.dumps(dataset, ensure_ascii=False, separators=(",", ":"))
    html = html_path.read_text(encoding="utf-8")
    start = html.index(START_TAG) + len(START_TAG)
    end = html.index(END_TAG, start)
    html_path.write_text(html[:start] + compact + html[end:], encoding="utf-8")
    print(f"[ok] {dataset_path.name} ({len(compact):,} 文字) を {html_path.name} に埋め込み")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(REPO_ROOT / "data" / "dataset.json"))
    ap.add_argument("--html", default=str(REPO_ROOT / "index.html"))
    args = ap.parse_args(argv)
    embed(Path(args.dataset), Path(args.html))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
