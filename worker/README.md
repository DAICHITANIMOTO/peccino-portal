# peccino-submit Worker

入力アプリ → GitHub の中継。`submitted-games/` にファイルを追加/更新/削除するだけ。データは保存しない。

- `index.js` — Worker 本体（約120行）
- `test.mjs` — ローカル検証（`node worker/test.mjs`、GitHub API はモック）
- `wrangler.toml` — CLI 配置用（ダッシュボード配置なら不要）

## エンドポイント

| | |
|---|---|
| `GET /health` | `{ ok: true, time }` を返すだけ（死活監視用） |
| `POST /submit` | body `{ secret, id, gameJson, gameText }` → `submitted-games/<id>.json` と `<id>.txt` を作成/上書き |
| `POST /delete` | body `{ secret, id }` → 上記2ファイルを削除 |

`id` は `2026-08-30_相手名` または `2026-08-30_相手名_2`（ダブルヘッダー）の形式。パス区切り・ドット始まりは拒否。

## 必要な Secret

| 名前 | 中身 |
|---|---|
| `GH_TOKEN` | GitHub fine-grained PAT。対象リポジトリ **peccino-portal のみ**、権限 **Contents: Read and write のみ**。有効期限は最長（約1年）。 |
| `SUBMIT_SECRET` | 送信用の合言葉。入力アプリの閲覧合言葉（`peccino2026`）と同じでよい。 |

## 配置手順（Cloudflare ダッシュボード・CLI 不要）

1. https://dash.cloudflare.com にログイン → 左メニュー **Workers & Pages** → **Create** → **Create Worker**
2. 名前を `peccino-submit` にして **Deploy**（中身は後で差し替え）
3. **Edit code** を開き、既定のコードを全部消して `index.js` の中身を貼り付け → **Deploy**
4. Worker の **Settings** → **Variables and Secrets** → **Add**：
   - `GH_TOKEN`（Type: Secret）= 上で作った PAT
   - `SUBMIT_SECRET`（Type: Secret）= `peccino2026`
   - 追加後 **Deploy**
5. Worker の URL（`https://peccino-submit.<アカウント名>.workers.dev`）を控える
6. `GET <URL>/health` をブラウザで開いて `{"ok":true,...}` が出れば OK

## GitHub PAT の作り方

1. https://github.com/settings/personal-access-tokens/new （Fine-grained tokens）
2. Token name: `peccino-submit` / Expiration: 最長（〜1年）
3. Repository access → **Only select repositories** → `DAICHITANIMOTO/peccino-portal`
4. Permissions → Repository permissions → **Contents** を **Read and write**（他は No access のまま）
5. Generate token → `github_pat_...` をコピー（この画面でしか見えない）

## CLI で配置する場合

```
cd worker
npx wrangler deploy
npx wrangler secret put GH_TOKEN
npx wrangler secret put SUBMIT_SECRET
```

## メンテナンス

- PAT は最長でも約1年で失効する。失効すると送信が静かに止まるので、`.github/workflows/healthcheck.yml`（週1で `/health` を叩き、異常時に issue を立てる）を入れておくこと。
- Cloudflare が使えなくなっても `index.js` はほぼそのまま Deno Deploy / Val.town 等に移せる。データは全部 GitHub 上にあるのでロックインなし。
