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


def test_load_submitted_skips_type_malformed(tmp_path):
    good = load_fixture("game_normal.json")
    (tmp_path / "good.json").write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")

    bad_atbats = copy.deepcopy(good)
    bad_atbats["atBats"] = None
    (tmp_path / "bad_atbats.json").write_text(
        json.dumps(bad_atbats, ensure_ascii=False), encoding="utf-8")

    bad_linescore = copy.deepcopy(good)
    bad_linescore["linescore"] = None
    (tmp_path / "bad_linescore.json").write_text(
        json.dumps(bad_linescore, ensure_ascii=False), encoding="utf-8")

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


def test_batting_logs_counts():
    sub = load_fixture("game_normal.json")
    roster = {"谷本大知": "1", "福田龍之介": "7", "中村駿": "19", "藤堂真雄": "2",
              "半井大稀": "3", "遠部巧大": "4", "榊原健斗": "5", "Yuito": "6", "薮中竜也": "9"}
    logs = ms.batting_logs_from_submission(sub, roster)
    by_name = {r["name"]: r for r in logs}

    tan = by_name["谷本大知"]
    assert (tan["pa"], tan["ab"], tan["h"], tan["double"], tan["hr"]) == (2, 2, 2, 1, 0)
    assert (tan["rbi"], tan["r"]) == (1, 1)
    assert tan["number"] == "1"
    assert tan["is_roster_member"] is True
    assert tan["started"] == "先発"
    assert tan["position"] == "三"

    fuk = by_name["福田龍之介"]
    assert (fuk["pa"], fuk["ab"], fuk["h"], fuk["bb"], fuk["so"]) == (2, 1, 0, 1, 0)

    nak = by_name["中村駿"]
    assert (nak["pa"], nak["ab"], nak["h"], nak["so"]) == (1, 1, 0, 1)

    tod = by_name["藤堂真雄"]
    assert (tod["pa"], tod["ab"], tod["h"], tod["hr"], tod["rbi"], tod["r"]) == (1, 1, 1, 1, 1, 1)

    han = by_name["半井大稀"]
    assert (han["pa"], han["ab"], han["sac"], han["h"]) == (1, 0, 1, 0)

    ono = by_name["遠部巧大"]
    assert (ono["pa"], ono["ab"], ono["h"], ono["error_reach"]) == (1, 1, 0, 1)

    # 打席が無かった先発(榊原/Yuito/薮中)も pa=0 の行が出る
    assert by_name["榊原健斗"]["pa"] == 0


def test_batting_logs_guest_player():
    sub = load_fixture("game_normal.json")
    sub["lineup"].append({"order": 10, "name": "助っ人太郎", "position": "控え"})
    sub["atBats"].append({"order": 10, "batter": "助っ人太郎", "inning": 2, "pa": 1,
                          "result": "単打", "position": 9, "ballType": "ゴロ", "notation": "9安ゴ"})
    roster = {"谷本大知": "1"}
    logs = ms.batting_logs_from_submission(sub, roster)
    guest = next(r for r in logs if r["name"] == "助っ人太郎")
    assert guest["is_roster_member"] is False
    assert guest["number"] == ""


def test_pitcher_by_inning_no_change():
    sub = load_fixture("game_normal.json")
    assert ms.pitcher_by_inning(sub) == {1: "中村駿", 2: "中村駿", 3: "中村駿"}


def test_pitching_logs_single_pitcher():
    sub = load_fixture("game_normal.json")
    roster = {"中村駿": "19"}
    logs = ms.pitching_logs_from_submission(sub, roster)
    assert len(logs) == 1
    p = logs[0]
    assert p["name"] == "中村駿"
    assert p["number"] == "19"
    # defense: 1回=アウト,三振,安打(1) 2回=アウト,四球,アウト  → アウト4つ
    assert p["innings"] == round(4 / 3, 4)
    assert p["h"] == 1
    assert p["so"] == 1
    assert p["bb"] == 1
    assert p["r"] == 1 and p["er"] == 1
    assert p["decision"] == "-"


def test_pitching_logs_with_change():
    sub = load_fixture("game_pitcher_change.json")
    roster = {"中村駿": "19", "半井大稀": "3"}
    logs = ms.pitching_logs_from_submission(sub, roster)
    by_name = {p["name"]: p for p in logs}
    assert set(by_name) == {"中村駿", "半井大稀"}
    # 中村: 1-2回 アウト4つ, 半井: 3回 三振1+安打(2失点) アウト1つ
    assert by_name["中村駿"]["innings"] == round(4 / 3, 4)
    assert by_name["半井大稀"]["innings"] == round(1 / 3, 4)
    assert by_name["半井大稀"]["r"] == 2
    assert by_name["半井大稀"]["h"] == 1


def test_pitching_logs_no_pitcher(capsys):
    sub = load_fixture("game_normal.json")
    sub["lineup"] = [r for r in sub["lineup"] if r["position"] != "投手"]
    sub["substitutions"] = []
    logs = ms.pitching_logs_from_submission(sub, {})
    assert logs == []
    assert "投手" in capsys.readouterr().err


def test_merge_adds_one_game():
    base = load_fixture("dataset_base_min.json")
    sub = load_fixture("game_normal.json")
    merged = ms.merge(base, [sub])
    assert len(merged["games"]) == 2
    ids = {g["game_id"] for g in merged["games"]}
    assert "sub_2026-08-30_神戸グフ" in ids
    assert "900001" in ids
    # batting_logs は 既存1 + 手入力9人 = 10
    assert len(merged["batting_logs"]) == 1 + 9
    assert any(b["game_id"] == "sub_2026-08-30_神戸グフ" for b in merged["batting_logs"])
    assert any(p["game_id"] == "sub_2026-08-30_神戸グフ" for p in merged["pitching_logs"])


def test_merge_is_idempotent():
    base = load_fixture("dataset_base_min.json")
    sub = load_fixture("game_normal.json")
    once = ms.merge(base, [sub])
    twice = ms.merge(once, [sub])
    assert once == twice


def test_merge_replaces_same_id():
    base = load_fixture("dataset_base_min.json")
    sub = load_fixture("game_normal.json")
    merged1 = ms.merge(base, [sub])
    sub2 = load_fixture("game_normal.json")
    sub2["linescore"]["self"] = [9, 0, 0, None, None, None, None]  # スコア修正
    merged2 = ms.merge(merged1, [sub2])
    g = next(x for x in merged2["games"] if x["game_id"] == "sub_2026-08-30_神戸グフ")
    assert g["score_for"] == 9
    assert len([x for x in merged2["games"] if x["game_id"] == "sub_2026-08-30_神戸グフ"]) == 1


def test_main_writes_valid_output(tmp_path):
    base_path = FIXTURES / "dataset_base_min.json"
    sub_dir = tmp_path / "submitted"
    sub_dir.mkdir()
    (sub_dir / "g.json").write_text(
        json.dumps(load_fixture("game_normal.json"), ensure_ascii=False), encoding="utf-8")
    (sub_dir / "broken.json").write_text("{oops", encoding="utf-8")
    out_path = tmp_path / "merged.json"

    rc = ms.main(["--base", str(base_path), "--submitted", str(sub_dir), "--out", str(out_path)])
    assert rc == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data["games"]) == 2                      # 壊れたファイルは無視
    assert out_path.read_text(encoding="utf-8").count("\n") == 0  # コンパクト1行


def test_main_never_shrinks_games(tmp_path):
    """不正データだらけでも既存 games を減らさない"""
    base_path = FIXTURES / "dataset_base_min.json"
    sub_dir = tmp_path / "submitted"
    sub_dir.mkdir()
    (sub_dir / "a.json").write_text("not json", encoding="utf-8")
    out_path = tmp_path / "merged.json"
    rc = ms.main(["--base", str(base_path), "--submitted", str(sub_dir), "--out", str(out_path)])
    assert rc == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data["games"]) == 1
