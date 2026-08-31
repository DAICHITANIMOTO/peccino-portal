/**
 * Peccino 成績入力アプリ → GitHub 中継 Worker (Cloudflare Workers)
 *
 * 役割: 入力アプリからの POST を受け、合言葉を照合して
 *       peccino-portal リポジトリの submitted-games/ にファイルを追加/更新/削除するだけ。
 *       データは何も保存しない(通すだけ)。
 *
 * エンドポイント:
 *   GET  /health            -> { ok: true, time }
 *   POST /submit            body { secret, id, gameJson, gameText }
 *                             submitted-games/<id>.json と <id>.txt を作成/上書き
 *   POST /delete            body { secret, id }
 *                             上記2ファイルを削除
 *
 * 必要な Secret (Cloudflare の Variables and Secrets で設定):
 *   GH_TOKEN       GitHub fine-grained PAT。対象リポジトリ peccino-portal のみ、
 *                  権限 Contents: Read and write のみ。
 *   SUBMIT_SECRET  送信用の合言葉。入力アプリの閲覧合言葉(peccino2026)と同じでよい。
 */

const REPO = "DAICHITANIMOTO/peccino-portal";
const BRANCH = "main";
const DIR = "submitted-games";
const ALLOWED_ORIGIN = "https://daichitanimoto.github.io";
const GH_API = "https://api.github.com";

// id は 2026-08-30_相手名 or 2026-08-30_相手名_2 の形。パス区切り・ドット始まりを禁止。
const ID_RE = /^\d{4}-\d{2}-\d{2}_[^/\\.\s][^/\\]{0,48}$/;

const CORS = {
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};

// 簡易レート制限(isolate ローカル・ベストエフォート)。趣味用途なので厳密でなくてよい。
const hits = new Map();
function rateLimited(ip) {
  const now = Date.now();
  const windowMs = 60_000;
  const max = 8;
  const arr = (hits.get(ip) || []).filter((t) => now - t < windowMs);
  arr.push(now);
  hits.set(ip, arr);
  if (hits.size > 500) hits.clear(); // メモリ暴走防止
  return arr.length > max;
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}

function b64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function ghHeaders(env) {
  return {
    Authorization: `Bearer ${env.GH_TOKEN}`,
    "User-Agent": "peccino-worker",
    Accept: "application/vnd.github+json",
  };
}

// 既存ファイルの sha を取得(無ければ null)
async function getSha(env, path) {
  const res = await fetch(
    `${GH_API}/repos/${REPO}/contents/${encodeURIComponent(path).replace(/%2F/g, "/")}?ref=${BRANCH}`,
    { headers: ghHeaders(env) }
  );
  if (res.status === 200) {
    const j = await res.json();
    return j.sha || null;
  }
  if (res.status === 404) return null;
  throw new Error(`GitHub GET ${path}: ${res.status} ${await res.text()}`);
}

async function putFile(env, path, content, message) {
  const sha = await getSha(env, path);
  const body = { message, content: b64(content), branch: BRANCH };
  if (sha) body.sha = sha;
  const res = await fetch(
    `${GH_API}/repos/${REPO}/contents/${encodeURIComponent(path).replace(/%2F/g, "/")}`,
    { method: "PUT", headers: { ...ghHeaders(env), "Content-Type": "application/json" }, body: JSON.stringify(body) }
  );
  if (!res.ok) throw new Error(`GitHub PUT ${path}: ${res.status} ${await res.text()}`);
}

async function deleteFile(env, path, message) {
  const sha = await getSha(env, path);
  if (!sha) return false;
  const res = await fetch(
    `${GH_API}/repos/${REPO}/contents/${encodeURIComponent(path).replace(/%2F/g, "/")}`,
    { method: "DELETE", headers: { ...ghHeaders(env), "Content-Type": "application/json" }, body: JSON.stringify({ message, sha, branch: BRANCH }) }
  );
  if (!res.ok) throw new Error(`GitHub DELETE ${path}: ${res.status} ${await res.text()}`);
  return true;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, time: new Date().toISOString() });
    }

    if (request.method === "POST" && (url.pathname === "/submit" || url.pathname === "/delete")) {
      const ip = request.headers.get("CF-Connecting-IP") || "unknown";
      if (rateLimited(ip)) return json({ ok: false, error: "しばらく待ってから再試行してください" }, 429);

      let payload;
      try {
        payload = await request.json();
      } catch {
        return json({ ok: false, error: "JSON を読めませんでした" }, 400);
      }

      if (!env.SUBMIT_SECRET || !safeEqual(String(payload.secret || ""), env.SUBMIT_SECRET)) {
        return json({ ok: false, error: "合言葉が違います" }, 401);
      }

      const id = String(payload.id || "");
      if (!ID_RE.test(id) || id.includes("..")) {
        return json({ ok: false, error: "id の形式が不正です" }, 400);
      }

      try {
        if (url.pathname === "/submit") {
          if (typeof payload.gameJson !== "object" || payload.gameJson === null) {
            return json({ ok: false, error: "gameJson がありません" }, 400);
          }
          const text = typeof payload.gameText === "string" ? payload.gameText : "";
          await putFile(env, `${DIR}/${id}.json`, JSON.stringify(payload.gameJson, null, 2), `試合記録: ${id} (入力アプリから)`);
          await putFile(env, `${DIR}/${id}.txt`, text || "(テキストなし)", `試合記録テキスト: ${id} (入力アプリから)`);
          return json({ ok: true, id });
        } else {
          const a = await deleteFile(env, `${DIR}/${id}.json`, `試合記録を削除: ${id}`);
          const b = await deleteFile(env, `${DIR}/${id}.txt`, `試合記録テキストを削除: ${id}`);
          return json({ ok: true, id, deleted: [a && `${id}.json`, b && `${id}.txt`].filter(Boolean) });
        }
      } catch (e) {
        return json({ ok: false, error: String(e && e.message || e) }, 502);
      }
    }

    return json({ ok: false, error: "not found" }, 404);
  },
};
