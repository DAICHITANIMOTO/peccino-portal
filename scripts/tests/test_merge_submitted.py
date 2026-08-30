from __future__ import annotations

import json
import copy
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import merge_submitted as ms

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_validate_accepts_normal_game():
    ms.validate_submission(load_fixture("game_normal.json"))  # raise しなければ OK


def test_validate_rejects_missing_game_key():
    bad = load_fixture("game_normal.json")
    del bad["game"]
    with pytest.raises(ms.SubmittedGameError):
        ms.validate_submission(bad)


def test_validate_rejects_bad_balltype():
    bad = load_fixture("game_normal.json")
    bad["atBats"][0]["ballType"] = "スライダー"
    with pytest.raises(ms.SubmittedGameError):
        ms.validate_submission(bad)


def test_validate_rejects_bad_position():
    bad = load_fixture("game_normal.json")
    bad["atBats"][0]["position"] = 12
    with pytest.raises(ms.SubmittedGameError):
        ms.validate_submission(bad)


def test_validate_rejects_bad_result():
    bad = load_fixture("game_normal.json")
    bad["atBats"][0]["result"] = "ホームスチール"
    with pytest.raises(ms.SubmittedGameError):
        ms.validate_submission(bad)


def test_load_submitted_skips_invalid(tmp_path):
    good = load_fixture("game_normal.json")
    (tmp_path / "good.json").write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")
    bad = copy.deepcopy(good)
    del bad["lineup"]
    (tmp_path / "invalid.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")

    result = ms.load_submitted(str(tmp_path))
    assert len(result) == 1
    assert result[0]["game"]["opponent"] == "神戸グフ"


def test_game_id_for():
    assert ms.game_id_for(load_fixture("game_normal.json")) == "sub_2026-08-30_神戸グフ"


def test_game_entry_basic():
    entry = ms.game_entry_from_submission(load_fixture("game_normal.json"))
    assert entry["game_id"] == "sub_2026-08-30_神戸グフ"
    assert entry["date"] == "2026/8/30 (日)"       # 2026-08-30 は日曜
    assert entry["date_sort"] == "2026-08-30"
    assert entry["opponent"] == "神戸グフ"
    assert entry["place"] == "名谷公園野球場"
    assert entry["category"] == "練習試合"
    assert entry["score_for"] == 3      # linescore.self 2+0+1
    assert entry["score_against"] == 1  # linescore.opp 1
    assert entry["result"] == "勝ち"
