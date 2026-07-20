const STATE_TABLE = "bolao_state";
const POOLS_TABLE = "bolao_pools";
const PARTICIPANTS_TABLE = "bolao_pool_participants";
const STATE_ID = "default";
const SESSION_COOKIE = "bolao_admin";
const SESSION_MAX_AGE = 60 * 60 * 8;

const DEFAULT_STATE = {
  game: {
    home_team: "Time da Casa",
    away_team: "Visitante",
    home_score: 0,
    away_score: 0,
    finished: false,
    history_recorded: false,
    history_record_id: null,
  },
  entry_fee: 0,
  participants: [],
  history: [],
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);

    try {
      validateEnvironment(env);
      const response = await route(request, env, url);
      return withSecurityHeaders(response);
    } catch (error) {
      console.error(error);
      const status = error.status || 500;
      const message = status === 500 ? "Não foi possível concluir a operação." : error.message;
      return withSecurityHeaders(json({ error: message }, status));
    }
  },
};

async function route(request, env, url) {
  const method = request.method.toUpperCase();
  const path = url.pathname;

  if (method === "GET" && path === "/api/public") {
    const [state, history] = await Promise.all([loadState(env), loadHistory(env)]);
    return json({ state: publicState(state), history });
  }
  if (method === "GET" && path === "/api/session") {
    return json({ authenticated: await isAdmin(request, env) });
  }
  if (method === "POST" && path === "/api/login") return login(request, env);
  if (method === "POST" && path === "/api/logout") return logout();

  if (!(await isAdmin(request, env))) throw httpError(401, "Sessão expirada. Entre novamente.");

  if (method === "GET" && path === "/api/admin") {
    const [state, history] = await Promise.all([loadState(env), loadHistory(env)]);
    return json({ state, history });
  }
  if (method === "PUT" && path === "/api/admin/game") return updateGame(request, env);
  if (method === "PUT" && path === "/api/admin/entry-fee") return updateEntryFee(request, env);
  if (method === "POST" && path === "/api/admin/participants") return addParticipant(request, env);
  if (method === "DELETE" && path.startsWith("/api/admin/participants/")) {
    return deleteParticipant(decodeURIComponent(path.split("/").pop()), env);
  }
  if (method === "POST" && path === "/api/admin/finish") return finishGame(env);
  if (method === "POST" && path === "/api/admin/reopen") return reopenGame(env);
  if (method === "POST" && path === "/api/admin/new-pool") return newPool(request, env);
  if (method === "DELETE" && path.startsWith("/api/admin/history/")) {
    return deleteHistory(decodeURIComponent(path.split("/").pop()), env);
  }

  throw httpError(404, "Rota não encontrada.");
}

function validateEnvironment(env) {
  if (!env.SUPABASE_URL || !env.SUPABASE_KEY || !env.BOLAO_ADMIN_PASSWORD || !env.SESSION_SECRET) {
    throw new Error("Configure SUPABASE_URL, SUPABASE_KEY, BOLAO_ADMIN_PASSWORD e SESSION_SECRET.");
  }
}

async function login(request, env) {
  const body = await readJson(request);
  if (!body.password || !(await safeEqual(String(body.password), env.BOLAO_ADMIN_PASSWORD))) {
    throw httpError(401, "Senha incorreta.");
  }
  const expires = Math.floor(Date.now() / 1000) + SESSION_MAX_AGE;
  const payload = `${expires}`;
  const signature = await sign(payload, env.SESSION_SECRET);
  const cookie = `${SESSION_COOKIE}=${payload}.${signature}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${SESSION_MAX_AGE}`;
  return json({ authenticated: true }, 200, { "Set-Cookie": cookie });
}

function logout() {
  return json({ authenticated: false }, 200, {
    "Set-Cookie": `${SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`,
  });
}

async function isAdmin(request, env) {
  const cookies = Object.fromEntries(
    (request.headers.get("Cookie") || "").split(";").map((part) => {
      const index = part.indexOf("=");
      return index < 0 ? [part.trim(), ""] : [part.slice(0, index).trim(), part.slice(index + 1)];
    }),
  );
  const token = cookies[SESSION_COOKIE];
  if (!token) return false;
  const separator = token.indexOf(".");
  if (separator < 1) return false;
  const expires = token.slice(0, separator);
  const signature = token.slice(separator + 1);
  if (!/^\d+$/.test(expires) || Number(expires) < Date.now() / 1000) return false;
  return safeEqual(signature, await sign(expires, env.SESSION_SECRET));
}

async function sign(value, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const bytes = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value)));
  return btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function safeEqual(left, right) {
  const a = new TextEncoder().encode(String(left));
  const b = new TextEncoder().encode(String(right));
  const size = Math.max(a.length, b.length);
  let difference = a.length ^ b.length;
  for (let i = 0; i < size; i += 1) difference |= (a[i] || 0) ^ (b[i] || 0);
  return difference === 0;
}

async function updateGame(request, env) {
  const body = await readJson(request);
  const state = await loadState(env);
  const homeTeam = cleanName(body.home_team, "Time da Casa");
  const awayTeam = cleanName(body.away_team, "Visitante");
  state.game = {
    ...state.game,
    home_team: homeTeam,
    away_team: awayTeam,
    home_score: nonNegativeInteger(body.home_score, "Placar da casa"),
    away_score: nonNegativeInteger(body.away_score, "Placar do visitante"),
  };
  if (state.game.finished) {
    state.game.finished = false;
    state.game.history_recorded = false;
    state.game.history_record_id = null;
  }
  await saveState(env, state);
  return json({ state });
}

async function updateEntryFee(request, env) {
  const body = await readJson(request);
  const fee = Number(body.entry_fee);
  if (!Number.isFinite(fee) || fee < 0) throw httpError(400, "Informe um valor válido.");
  const state = await loadState(env);
  state.entry_fee = Math.round(fee * 100) / 100;
  await saveState(env, state);
  return json({ state });
}

async function addParticipant(request, env) {
  const body = await readJson(request);
  const name = cleanName(body.name);
  if (!name) throw httpError(400, "Informe o nome do participante.");
  const state = await loadState(env);
  if (state.game.finished) throw httpError(409, "Inicie outro bolão antes de adicionar participantes.");
  if (state.participants.some((item) => item.name.toLocaleLowerCase("pt-BR") === name.toLocaleLowerCase("pt-BR"))) {
    throw httpError(409, "Já existe um participante com esse nome.");
  }
  state.participants.push({
    id: crypto.randomUUID(),
    name,
    guess_home_score: nonNegativeInteger(body.guess_home_score, "Palpite da casa"),
    guess_away_score: nonNegativeInteger(body.guess_away_score, "Palpite do visitante"),
  });
  await saveState(env, state);
  return json({ state }, 201);
}

async function deleteParticipant(id, env) {
  const state = await loadState(env);
  const before = state.participants.length;
  state.participants = state.participants.filter((item) => item.id !== id);
  if (before === state.participants.length) throw httpError(404, "Participante não encontrado.");
  await saveState(env, state);
  return json({ state });
}

async function finishGame(env) {
  const state = await loadState(env);
  if (state.game.finished && state.game.history_recorded) throw httpError(409, "Esta partida já foi finalizada.");
  const record = buildHistoryRecord(state);
  await saveHistory(env, record);
  state.game.finished = true;
  state.game.history_recorded = true;
  state.game.history_record_id = record.id;
  await saveState(env, state);
  return json({ state, record });
}

async function reopenGame(env) {
  const state = await loadState(env);
  if (!state.game.finished) throw httpError(409, "A partida já está aberta.");
  if (state.game.history_record_id) await removeHistory(env, state.game.history_record_id);
  state.game.finished = false;
  state.game.history_recorded = false;
  state.game.history_record_id = null;
  await saveState(env, state);
  return json({ state });
}

async function newPool(request, env) {
  const body = await readJson(request);
  if (body.confirm !== true) throw httpError(400, "Confirme a abertura do novo bolão.");
  const state = await loadState(env);
  if (!state.game.finished) throw httpError(409, "Finalize a partida atual primeiro.");
  state.participants = [];
  state.game = structuredClone(DEFAULT_STATE.game);
  await saveState(env, state);
  return json({ state });
}

async function deleteHistory(id, env) {
  await removeHistory(env, id);
  const state = await loadState(env);
  state.history = state.history.filter((record) => record.id !== id);
  if (state.game.history_record_id === id) {
    state.game.history_recorded = false;
    state.game.history_record_id = null;
  }
  await saveState(env, state);
  return json({ ok: true });
}

function normalizeState(input) {
  const state = input && typeof input === "object" ? structuredClone(input) : {};
  state.game = { ...DEFAULT_STATE.game, ...(state.game || {}) };
  state.entry_fee = Number(state.entry_fee) || 0;
  state.participants = Array.isArray(state.participants) ? state.participants : [];
  state.participants = state.participants.map((participant) => ({
    ...participant,
    id: participant.id || crypto.randomUUID(),
    name: String(participant.name || ""),
    guess_home_score: Number(participant.guess_home_score) || 0,
    guess_away_score: Number(participant.guess_away_score) || 0,
  }));
  state.history = Array.isArray(state.history) ? state.history : [];
  return state;
}

function publicState(state) {
  return {
    game: state.game,
    entry_fee: state.entry_fee,
    participants: state.participants,
    prize_pool: calculatePrize(state),
  };
}

function calculatePrize(state) {
  return state.participants.length * Number(state.entry_fee || 0);
}

function winners(state) {
  return state.participants.filter(
    (participant) => participant.guess_home_score === state.game.home_score
      && participant.guess_away_score === state.game.away_score,
  );
}

function buildHistoryRecord(state) {
  const exact = winners(state);
  const prize = calculatePrize(state);
  return {
    id: crypto.randomUUID(),
    finished_at: new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo" }).format(new Date()),
    game: {
      home_team: state.game.home_team,
      away_team: state.game.away_team,
      home_score: state.game.home_score,
      away_score: state.game.away_score,
    },
    entry_fee: Number(state.entry_fee),
    prize_pool: prize,
    prize_per_winner: exact.length ? prize / exact.length : 0,
    winners: exact.map((participant) => participant.name),
    participants: structuredClone(state.participants),
  };
}

async function loadState(env) {
  const rows = await supabase(env, "GET", `${STATE_TABLE}?id=eq.${STATE_ID}&select=state`);
  if (rows?.length) return normalizeState(rows[0].state);
  const state = normalizeState(DEFAULT_STATE);
  await saveState(env, state);
  return state;
}

async function saveState(env, state) {
  await supabase(env, "POST", STATE_TABLE, { id: STATE_ID, state: normalizeState(state) });
}

async function loadHistory(env) {
  const statePromise = loadState(env);
  const pools = await supabase(env, "GET", `${POOLS_TABLE}?select=*&order=created_at.desc`);
  const participantRows = pools?.length
    ? await supabase(env, "GET", `${PARTICIPANTS_TABLE}?pool_id=in.(${pools.map((pool) => pool.id).join(",")})&select=*`)
    : [];
  const byPool = (participantRows || []).reduce((groups, participant) => {
    (groups[participant.pool_id] ||= []).push(participant);
    return groups;
  }, {});
  const split = (pools || []).map((pool) => ({
    id: pool.id,
    finished_at: String(pool.finished_at || "").split(" ")[0],
    game: {
      home_team: pool.home_team,
      away_team: pool.away_team,
      home_score: pool.home_score,
      away_score: pool.away_score,
    },
    entry_fee: Number(pool.entry_fee || 0),
    prize_pool: Number(pool.prize_pool || 0),
    prize_per_winner: Number(pool.prize_per_winner || 0),
    winners: pool.winners || [],
    participants: (byPool[pool.id] || []).map((participant) => ({
      id: participant.id,
      name: participant.name,
      guess_home_score: participant.guess_home_score,
      guess_away_score: participant.guess_away_score,
    })),
  })).reverse();
  const state = await statePromise;
  const ids = new Set(split.map((record) => record.id));
  return [...state.history.filter((record) => !ids.has(record.id)), ...split];
}

async function saveHistory(env, record) {
  await supabase(env, "POST", POOLS_TABLE, {
    id: record.id,
    home_team: record.game.home_team,
    away_team: record.game.away_team,
    home_score: record.game.home_score,
    away_score: record.game.away_score,
    entry_fee: record.entry_fee,
    prize_pool: record.prize_pool,
    prize_per_winner: record.prize_per_winner,
    winners: record.winners,
    finished_at: record.finished_at,
  });
  if (record.participants.length) {
    await supabase(env, "POST", PARTICIPANTS_TABLE, record.participants.map((participant) => ({
      id: participant.id || crypto.randomUUID(),
      pool_id: record.id,
      name: participant.name,
      guess_home_score: participant.guess_home_score,
      guess_away_score: participant.guess_away_score,
      is_winner: record.winners.includes(participant.name),
    })));
  }
}

async function removeHistory(env, id) {
  await supabase(env, "DELETE", `${PARTICIPANTS_TABLE}?pool_id=eq.${encodeURIComponent(id)}`);
  await supabase(env, "DELETE", `${POOLS_TABLE}?id=eq.${encodeURIComponent(id)}`);
}

async function supabase(env, method, path, body) {
  const base = env.SUPABASE_URL.trim().replace(/\/$/, "").replace(/\/rest\/v1$/, "");
  const headers = {
    apikey: env.SUPABASE_KEY,
    "Content-Type": "application/json",
    Prefer: "resolution=merge-duplicates,return=representation",
  };
  if (env.SUPABASE_KEY.includes(".") && !env.SUPABASE_KEY.startsWith("sb_")) {
    headers.Authorization = `Bearer ${env.SUPABASE_KEY}`;
  }
  const response = await fetch(`${base}/rest/v1/${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) {
    console.error("Supabase", response.status, text);
    throw httpError(502, "Falha de comunicação com o banco de dados.");
  }
  return text ? JSON.parse(text) : null;
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    throw httpError(400, "Dados inválidos.");
  }
}

function cleanName(value, fallback = "") {
  const text = String(value || "").trim().replace(/\s+/g, " ").slice(0, 80);
  return text || fallback;
}

function nonNegativeInteger(value, label) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 0 || number > 99) throw httpError(400, `${label} inválido.`);
  return number;
}

function httpError(status, message) {
  return Object.assign(new Error(message), { status });
}

function json(value, status = 200, headers = {}) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers },
  });
}

function withSecurityHeaders(response) {
  const result = new Response(response.body, response);
  result.headers.set("X-Content-Type-Options", "nosniff");
  result.headers.set("X-Frame-Options", "DENY");
  result.headers.set("Referrer-Policy", "same-origin");
  return result;
}
