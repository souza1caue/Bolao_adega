import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/worker.js";

const initialState = () => ({
  game: { home_team: "Casa", away_team: "Fora", home_score: 1, away_score: 0, finished: false, history_recorded: false, history_record_id: null },
  entry_fee: 10,
  participants: [],
  history: [],
});

function harness() {
  const database = { state: initialState(), pools: [], participants: [] };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    const path = new URL(url).pathname.replace("/rest/v1/", "");
    const method = options.method || "GET";
    const body = options.body ? JSON.parse(options.body) : null;
    if (path.startsWith("bolao_state")) {
      if (method === "GET") return Response.json([{ state: database.state }]);
      if (method === "POST") { database.state = body.state; return Response.json([body]); }
    }
    if (path.startsWith("bolao_pools")) return Response.json(database.pools);
    if (path.startsWith("bolao_pool_participants")) return Response.json(database.participants);
    return Response.json({ message: "not found" }, { status: 404 });
  };
  const env = {
    SUPABASE_URL: "https://example.supabase.co",
    SUPABASE_KEY: "sb_secret_test",
    BOLAO_ADMIN_PASSWORD: "senha-forte",
    SESSION_SECRET: "segredo-de-sessao-longo-para-testes",
    ASSETS: { fetch: () => new Response("asset") },
  };
  return { database, env, restore: () => { globalThis.fetch = originalFetch; } };
}

test("carrega o estado público preservando o modelo atual", async () => {
  const context = harness();
  try {
    const response = await worker.fetch(new Request("https://bolao.test/api/public"), context.env);
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.state.game.home_team, "Casa");
    assert.equal(result.state.prize_pool, 0);
    assert.deepEqual(result.history, []);
  } finally { context.restore(); }
});

test("autentica por cookie assinado e cadastra participante", async () => {
  const context = harness();
  try {
    const login = await worker.fetch(new Request("https://bolao.test/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: "senha-forte" }),
    }), context.env);
    assert.equal(login.status, 200);
    const cookie = login.headers.get("set-cookie").split(";")[0];
    const add = await worker.fetch(new Request("https://bolao.test/api/admin/participants", {
      method: "POST",
      headers: { "Content-Type": "application/json", Cookie: cookie },
      body: JSON.stringify({ name: "Ana", guess_home_score: 2, guess_away_score: 1 }),
    }), context.env);
    assert.equal(add.status, 201);
    assert.equal(context.database.state.participants[0].name, "Ana");
    assert.equal(context.database.state.participants[0].guess_home_score, 2);
  } finally { context.restore(); }
});

test("rejeita senha administrativa incorreta", async () => {
  const context = harness();
  try {
    const response = await worker.fetch(new Request("https://bolao.test/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: "errada" }),
    }), context.env);
    assert.equal(response.status, 401);
  } finally { context.restore(); }
});
