"""submitted-games/*.json を data/dataset.json にマージするスクリプト。

使い方:
    python scripts/merge_submitted.py --base data/dataset.json \
        --submitted submitted-games --out /tmp/merged.json

ローカルでも GitHub Actions でも同じものを使う。冪等(何度実行しても同じ結果)。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from pos_maps import (
    POS_FULL_TO_SHORT, NUM_TO_SHORT, BATTED_BALL_TYPES, OFF_RESULTS, DEF_RESULTS,
    HIT_RESULTS, OFF_OUT_RESULTS, QUICK_RESULTS,
)


class SubmittedGameError(Exception):
    """submitted-game JSON が期待する形をしていない。"""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SubmittedGameError(msg)


def validate_submission(obj: dict) -> None:
    _require(isinstance(obj, dict), "トップレベルが object でない")
    for key in ("game", "lineup", "atBats", "defense", "playerTally", "linescore"):
        _require(key in obj, f"必須キー '{key}' が無い")
    g = obj["game"]
    for key in ("date", "opponent", "firstAttack"):
        _require(key in g, f"game.{key} が無い")
    _require(isinstance(obj["lineup"], list) and obj["lineup"], "lineup が空")
    for row in obj["lineup"]:
        _require({"order", "name"} <= set(row), "lineup 行に order/name が無い")
    for ab in obj["atBats"]:
        _require(ab.get("result") in OFF_RESULTS, f"atBats.result が不正: {ab.get('result')}")
        pos = ab.get("position")
        _require(pos is None or pos in NUM_TO_SHORT, f"atBats.position が不正: {pos}")
        bt = ab.get("ballType")
        _require(bt is None or bt in BATTED_BALL_TYPES, f"atBats.ballType が不正: {bt}")
    for dp in obj["defense"]:
        _require(dp.get("result") in DEF_RESULTS, f"defense.result が不正: {dp.get('result')}")
        f = dp.get("fielder")
        _require(f is None or f in NUM_TO_SHORT, f"defense.fielder が不正: {f}")
    ls = obj["linescore"]
    _require("self" in ls and "opp" in ls, "linescore.self/opp が無い")


def load_submitted(dirpath: str) -> list[dict]:
    out: list[dict] = []
    for path in sorted(Path(dirpath).glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            validate_submission(obj)
        except (json.JSONDecodeError, SubmittedGameError) as e:
            print(f"[skip] {path.name}: {e}", file=sys.stderr)
            continue
        out.append(obj)
    return out


_WD = ["月", "火", "水", "木", "金", "土", "日"]


def _jp_date(iso: str) -> tuple[str, str]:
    y, m, d = (int(x) for x in iso.split("-"))
    wd = _WD[date(y, m, d).weekday()]
    return f"{y}/{m}/{d} ({wd})", f"{y:04d}-{m:02d}-{d:02d}"


def _safe_slug(opponent: str) -> str:
    # ファイル名/ID に使えない文字だけ除去。日本語はそのまま(GitHub は UTF-8 ファイル名可)
    bad = set('/\\:*?"<>|')
    s = "".join(c for c in opponent if c not in bad).strip().replace(" ", "-")
    return s or "unknown"


def game_id_for(sub: dict) -> str:
    g = sub["game"]
    return f"sub_{g['date']}_{_safe_slug(g['opponent'])}"


def _linescore_total(arr: list) -> int:
    return sum(int(x) for x in arr if x is not None)


def game_entry_from_submission(sub: dict) -> dict:
    g = sub["game"]
    disp, sort = _jp_date(g["date"])
    sf = _linescore_total(sub["linescore"]["self"])
    sa = _linescore_total(sub["linescore"]["opp"])
    result = "勝ち" if sf > sa else ("負け" if sf < sa else "引分け")
    return {
        "game_id": game_id_for(sub),
        "date": disp,
        "date_sort": sort,
        "category": "練習試合",
        "opponent": g["opponent"],
        "place": g.get("place", ""),
        "result": result,
        "score_for": sf,
        "score_against": sa,
    }


BATTING_ZERO_FIELDS = (
    "pa", "ab", "h", "hr", "rbi", "r", "sb", "double", "triple",
    "risp_ab", "risp_h", "so", "bb", "hbp", "sac", "sf", "gdp",
    "error_reach", "e", "cs", "cs_catcher",
)


def roster_index(base_dataset: dict) -> dict:
    return {p["name"]: str(p.get("number", "")) for p in base_dataset.get("players", [])}


def _blank_batting(game_id: str, name: str, roster: dict) -> dict:
    row = {
        "game_id": game_id,
        "number": roster.get(name, ""),
        "name": name,
        "is_roster_member": name in roster,
        "started": "先発",
        "order": 0,
        "position": "",
    }
    for f in BATTING_ZERO_FIELDS:
        row[f] = 0
    return row


def batting_logs_from_submission(sub: dict, roster: dict) -> list[dict]:
    game_id = game_id_for(sub)
    tally = sub.get("playerTally", {})

    # order -> (name, position短縮) を lineup から。同 order で name が複数(交代)なら
    # atBats の batter を優先し、行を分ける
    lineup_by_order = {r["order"]: r for r in sub["lineup"]}
    subbed_in = {s.get("order") for s in sub.get("substitutions", []) if s.get("type") == "bat"}

    rows: dict[str, dict] = {}

    def ensure(name: str, order: int, position: str, started: str) -> dict:
        if name not in rows:
            r = _blank_batting(game_id, name, roster)
            r["order"] = order
            r["position"] = position
            r["started"] = started
            rows[name] = r
        return rows[name]

    # まず lineup の全員を pa=0 で用意
    for lr in sub["lineup"]:
        short = POS_FULL_TO_SHORT.get(lr.get("position", ""), "")
        ensure(lr["name"], lr["order"], short, "先発")

    # atBats を打者ごとに集計
    for ab in sub["atBats"]:
        name = ab.get("batter") or lineup_by_order.get(ab["order"], {}).get("name", "")
        if not name:
            continue
        started = "途中" if ab["order"] in subbed_in and name not in {l["name"] for l in sub["lineup"]} else "先発"
        lr = lineup_by_order.get(ab["order"], {})
        short = POS_FULL_TO_SHORT.get(lr.get("position", ""), "")
        row = ensure(name, ab["order"], short, started)
        res = ab["result"]
        row["pa"] += 1
        if res not in ("四球", "死球", "犠打", "犠飛"):
            row["ab"] += 1
        if res in HIT_RESULTS:
            row["h"] += 1
        if res == "二塁打":
            row["double"] += 1
        elif res == "三塁打":
            row["triple"] += 1
        elif res == "本塁打":
            row["hr"] += 1
        elif res == "四球":
            row["bb"] += 1
        elif res == "死球":
            row["hbp"] += 1
        elif res == "三振":
            row["so"] += 1
        elif res == "犠打":
            row["sac"] += 1
        elif res == "犠飛":
            row["sf"] += 1
        elif res == "失策出塁":
            row["error_reach"] += 1

    # タリー(打点/得点/失策)を反映
    for name, t in tally.items():
        row = rows.get(name) or ensure(name, 0, "", "途中")
        row["rbi"] = int(t.get("rbi", 0))
        row["r"] = int(t.get("run", 0))
        row["e"] = int(t.get("error", 0))

    return list(rows.values())
