// Worker のロジック検証。GitHub API 呼び出しはモック。 実行: node worker/test.mjs
import worker from "./index.js";

let pass = 0, fail = 0;
function ok(name, cond, extra = "") {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ✗ ${name} ${extra}`); }
}

const ORIGIN = "https://daichitanimoto.github.io";
const SECRET = "peccino2026";
const env = { GH_TOKEN: "ghp_fake", SUBMIT_SECRET: SECRET };

// --- GitHub API モック ---
const ghCalls = [];
const realFetch = globalThis.fetch;
function mockGitHub({ existingSha = null } = {}) {
  globalThis.fetch = async (u, opts = {}) => {
    const url = typeof u === "string" ? u : u.url;
    ghCalls.push({ method: opts.method || "GET", url, body: opts.body ? JSON.parse(opts.body) : null });
    if (!url.startsWith("https://api.github.com/")) throw new Error("unexpected fetch " + url);
    const method = opts.method || "GET";
    if (method === "GET") {
      return existingSha
        ? new Response(JSON.stringify({ sha: existingSha }), { status: 200 })
        : new Response("not found", { status: 404 });
    }
    if (method === "PUT") return new Response(JSON.stringify({ content: { sha: "newsha" } }), { status: 201 });
    if (method === "DELETE") return new Response(JSON.stringify({ commit: {} }), { status: 200 });
    return new Response("?", { status: 500 });
  };
}
function restoreFetch() { globalThis.fetch = realFetch; }

let ipCounter = 0;
function req(method, path, body, headers = {}) {
  // 各リクエストにユニークIPを振る(レート制限テスト以外はぶつからないように)
  const ip = headers["CF-Connecting-IP"] || `10.0.0.${++ipCounter}`;
  return new Request("https://w.example.dev" + path, {
    method,
    headers: { "Content-Type": "application/json", "CF-Connecting-IP": ip, ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
const decUrl = (u) => decodeURIComponent(u);

const GAME = { app: "peccino-score-input", game: { date: "2026-08-30", opponent: "神戸グフ" }, atBats: [] };

console.log("== Worker 検証 ==");

// health
{
  const r = await worker.fetch(req("GET", "/health"), env);
  const j = await r.json();
  ok("GET /health → ok:true", r.status === 200 && j.ok === true);
  ok("health に CORS ヘッダ", r.headers.get("Access-Control-Allow-Origin") === ORIGIN);
}

// OPTIONS preflight
{
  const r = await worker.fetch(req("OPTIONS", "/submit"), env);
  ok("OPTIONS → 204 + CORS", r.status === 204 && r.headers.get("Access-Control-Allow-Origin") === ORIGIN);
}

// submit: 誤った合言葉
{
  mockGitHub();
  const r = await worker.fetch(req("POST", "/submit", { secret: "wrong", id: "2026-08-30_神戸グフ", gameJson: GAME, gameText: "t" }), env);
  ok("誤合言葉 → 401", r.status === 401);
  restoreFetch();
}

// submit: 不正 id
{
  mockGitHub();
  for (const badId of ["../etc", "2026-8-30_x", "no-date", "2026-08-30_a/b", "2026-08-30_..", ".2026-08-30_x"]) {
    const r = await worker.fetch(req("POST", "/submit", { secret: SECRET, id: badId, gameJson: GAME, gameText: "t" }), env);
    ok(`不正 id "${badId}" → 400`, r.status === 400);
  }
  restoreFetch();
}

// submit: 正常(新規) → PUT が2回(.json と .txt)、branch=main
{
  ghCalls.length = 0;
  mockGitHub({ existingSha: null });
  const r = await worker.fetch(req("POST", "/submit", { secret: SECRET, id: "2026-08-30_神戸グフ", gameJson: GAME, gameText: "スコア表" }), env);
  const j = await r.json();
  ok("正常 submit → ok:true", r.status === 200 && j.ok === true, JSON.stringify(j));
  const puts = ghCalls.filter((c) => c.method === "PUT");
  ok("PUT が2回(.json/.txt)", puts.length === 2, `puts=${puts.length}`);
  ok(".json への PUT パス", decUrl(puts[0].url).endsWith("/contents/submitted-games/2026-08-30_神戸グフ.json"), decUrl(puts[0].url));
  ok(".txt への PUT パス", decUrl(puts[1].url).endsWith("/contents/submitted-games/2026-08-30_神戸グフ.txt"));
  ok("PUT body branch=main・sha無し(新規)", puts[0].body.branch === "main" && puts[0].body.sha === undefined);
  const decoded = Buffer.from(puts[0].body.content, "base64").toString("utf-8");
  ok("PUT content が gameJson を整形したもの", JSON.parse(decoded).game.opponent === "神戸グフ");
  ok(".txt content が gameText", Buffer.from(puts[1].body.content, "base64").toString("utf-8") === "スコア表");
  ok("submit に CORS ヘッダ", r.headers.get("Access-Control-Allow-Origin") === ORIGIN);
  restoreFetch();
}

// submit: 既存あり → PUT に sha 付き(上書き)
{
  ghCalls.length = 0;
  mockGitHub({ existingSha: "abc123" });
  const r = await worker.fetch(req("POST", "/submit", { secret: SECRET, id: "2026-08-30_神戸グフ_2", gameJson: GAME, gameText: "t" }), env);
  ok("既存 submit → ok", r.status === 200);
  const puts = ghCalls.filter((c) => c.method === "PUT");
  ok("上書き時は PUT body に sha 付き", puts[0].body.sha === "abc123");
  restoreFetch();
}

// submit: gameJson 欠落
{
  mockGitHub();
  const r = await worker.fetch(req("POST", "/submit", { secret: SECRET, id: "2026-08-30_x" }), env);
  ok("gameJson 欠落 → 400", r.status === 400);
  restoreFetch();
}

// delete: 正常
{
  ghCalls.length = 0;
  mockGitHub({ existingSha: "s1" });
  const r = await worker.fetch(req("POST", "/delete", { secret: SECRET, id: "2026-08-30_神戸グフ" }), env);
  const j = await r.json();
  ok("delete → ok・deleted 2件", r.status === 200 && j.deleted.length === 2, JSON.stringify(j));
  ok("DELETE が2回", ghCalls.filter((c) => c.method === "DELETE").length === 2);
  restoreFetch();
}

// delete: ファイル無し → ok・deleted 0件
{
  ghCalls.length = 0;
  mockGitHub({ existingSha: null });
  const r = await worker.fetch(req("POST", "/delete", { secret: SECRET, id: "2026-08-30_無い" }), env);
  const j = await r.json();
  ok("存在しない delete → ok・deleted 0件", r.status === 200 && j.deleted.length === 0);
  restoreFetch();
}

// GitHub API がエラー → 502
{
  globalThis.fetch = async () => new Response("boom", { status: 500 });
  const r = await worker.fetch(req("POST", "/submit", { secret: SECRET, id: "2026-08-30_x", gameJson: GAME, gameText: "t" }), env);
  ok("GitHub API 失敗 → 502", r.status === 502);
  restoreFetch();
}

// レート制限
{
  mockGitHub();
  let got429 = false;
  for (let i = 0; i < 12; i++) {
    const r = await worker.fetch(req("POST", "/submit", { secret: "wrong", id: "2026-08-30_x", gameJson: GAME, gameText: "t" }, { "CF-Connecting-IP": "9.9.9.9" }), env);
    if (r.status === 429) got429 = true;
  }
  ok("同一IPで連打 → 429 が出る", got429);
  restoreFetch();
}

// 未知パス
{
  const r = await worker.fetch(req("GET", "/nope"), env);
  ok("未知パス → 404", r.status === 404);
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
