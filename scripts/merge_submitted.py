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
