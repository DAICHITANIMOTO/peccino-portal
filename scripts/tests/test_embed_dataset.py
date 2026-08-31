from __future__ import annotations
import json, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import embed_dataset as ed

START = '<script type="application/json" id="dataset-json">'
END = "</script>"


def test_embed_replaces_block(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(f"<html><body>{START}OLDDATA{END}</body></html>", encoding="utf-8")
    ds = tmp_path / "dataset.json"
    ds.write_text(json.dumps({"players": [], "games": [{"game_id": "x"}]}, ensure_ascii=False),
                  encoding="utf-8")

    rc = ed.main(["--dataset", str(ds), "--html", str(html)])
    assert rc == 0
    out = html.read_text(encoding="utf-8")
    assert "OLDDATA" not in out
    assert '"game_id":"x"' in out
    assert out.count(START) == 1 and out.count(END) == 1


def test_embed_output_is_compact(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(f"{START}x{END}", encoding="utf-8")
    ds = tmp_path / "dataset.json"
    ds.write_text('{"a": 1, "b": [1, 2]}', encoding="utf-8")
    ed.main(["--dataset", str(ds), "--html", str(html)])
    body = html.read_text(encoding="utf-8")
    assert '{"a":1,"b":[1,2]}' in body   # スペース無し


def test_embed_raises_if_start_tag_missing(tmp_path):
    html = tmp_path / "index.html"
    html.write_text("<html><body>no dataset block here</body></html>", encoding="utf-8")
    ds = tmp_path / "dataset.json"
    ds.write_text('{"a":1}', encoding="utf-8")
    with pytest.raises(ValueError):
        ed.main(["--dataset", str(ds), "--html", str(html)])
