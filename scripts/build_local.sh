#!/usr/bin/env bash
# submitted-games を反映して index.html を再ビルドする(ローカル用)。
# GitHub Actions も同じ2コマンドを実行する。
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/merge_submitted.py --base data/dataset.json --submitted submitted-games --out /tmp/peccino_merged.json
python scripts/embed_dataset.py --dataset /tmp/peccino_merged.json --html index.html
echo "done: index.html を更新しました"
