# peccino-portal

草野球チーム Peccino の成績ポータル(GitHub Pages)。

- `index.html` — 公開サイト本体。`<script id="dataset-json">` に全データを埋め込み。
  **このブロックは GitHub Actions が自動更新するので手で編集しない。**
- `data/dataset.json` — ベースデータ(teams.one スクレイプ + 記録員Excel由来)。
  Claude がローカルで再スクレイプ/Excel更新したときだけ差し替える。
- `submitted-games/<日付>_<相手>.json` (+ `.txt`) — 入力アプリで記録した試合。1試合1ファイル。
  Cloudflare Worker が自動追加。手で追加/修正/削除も可。
- `scripts/merge_submitted.py` — `data/dataset.json` に `submitted-games/*` をマージ。冪等。
- `scripts/embed_dataset.py` — マージ結果を `index.html` に埋め込み。
- `scripts/build_local.sh` — 上記2つを通しで実行(ローカル用)。
- `.github/workflows/build.yml` — `submitted-games/**` 等の push で自動ビルド&コミット。

## ローカルでビルドする

```
cd /path/to/peccino-stats && source venv/bin/activate
cd portal-repo && bash scripts/build_local.sh
```

## テスト

```
cd /path/to/peccino-stats && source venv/bin/activate
python -m pytest portal-repo/scripts/tests/ -q
```
