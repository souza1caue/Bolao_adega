const app = { state: null, history: [], authenticated: false, timer: null };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindNavigation();
  bindForms();
  await Promise.all([loadPublic(), checkSession()]);
  app.timer = setInterval(() => {
    if (!document.hidden && currentView() !== "admin") loadPublic(true);
  }, 5000);
}

function bindNavigation() {
  $$(".nav-button").forEach((button) => button.addEventListener("click", async () => {
    const view = button.dataset.view;
    $$(".nav-button").forEach((item) => item.classList.toggle("active", item === button));
    $$(".view").forEach((item) => item.classList.toggle("active", item.id === `view-${view}`));
    history.replaceState(null, "", `#${view}`);
    if (view === "admin" && app.authenticated) await loadAdmin();
  }));
  $$(".admin-tab").forEach((button) => button.addEventListener("click", () => {
    $$(".admin-tab").forEach((item) => item.classList.toggle("active", item === button));
    $$(".admin-view").forEach((item) => item.classList.toggle("active", item.id === `admin-${button.dataset.adminView}`));
  }));
  const hash = location.hash.slice(1);
  if (["inicio", "historico", "admin"].includes(hash)) $(`.nav-button[data-view="${hash}"]`).click();
}

function bindForms() {
  $("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = new FormData(event.currentTarget).get("password");
    await action(async () => {
      await api("/api/login", { method: "POST", body: { password } });
      event.currentTarget.reset();
      app.authenticated = true;
      showAdmin(true);
      await loadAdmin();
      toast("Acesso liberado.");
    });
  });
  $("#logout-button").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" });
    app.authenticated = false;
    showAdmin(false);
    toast("Sessão encerrada.");
  });
  $("#game-form").addEventListener("submit", (event) => submitForm(event, "/api/admin/game", "PUT", "Placar atualizado."));
  $("#fee-form").addEventListener("submit", (event) => submitForm(event, "/api/admin/entry-fee", "PUT", "Valor atualizado."));
  $("#participant-form").addEventListener("submit", (event) => submitForm(event, "/api/admin/participants", "POST", "Participante adicionado.", true));
  $("#finish-button").addEventListener("click", () => confirmAction("Finalizar partida?", "O resultado e os vencedores serão gravados no histórico.", async () => mutate("/api/admin/finish", "POST", "Partida finalizada.")));
  $("#reopen-button").addEventListener("click", () => confirmAction("Reabrir partida?", "O registro desta partida será removido do histórico para permitir correções.", async () => mutate("/api/admin/reopen", "POST", "Partida reaberta.")));
  $("#new-pool-button").addEventListener("click", () => confirmAction("Iniciar novo bolão?", "Todos os participantes atuais serão removidos e o placar será zerado.", async () => mutate("/api/admin/new-pool", "POST", "Novo bolão iniciado.", { confirm: true })));
}

async function submitForm(event, path, method, success, reset = false) {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget));
  for (const key of Object.keys(body)) if (key.includes("score") || key === "entry_fee") body[key] = Number(body[key]);
  await action(async () => {
    const result = await api(path, { method, body });
    app.state = result.state;
    if (reset) event.currentTarget.reset();
    await refreshAll();
    toast(success);
  });
}

async function mutate(path, method, success, body) {
  await action(async () => {
    const result = await api(path, { method, body });
    if (result.state) app.state = result.state;
    await refreshAll();
    toast(success);
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    credentials: "same-origin",
    headers: options.body === undefined ? {} : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/login") {
      app.authenticated = false;
      showAdmin(false);
    }
    throw new Error(result.error || "Não foi possível concluir a operação.");
  }
  return result;
}

async function action(callback) {
  try { await callback(); } catch (error) { toast(error.message, true); }
}

async function checkSession() {
  try {
    const result = await api("/api/session");
    app.authenticated = result.authenticated;
    showAdmin(app.authenticated);
  } catch { showAdmin(false); }
}

async function loadPublic(silent = false) {
  try {
    const result = await api("/api/public");
    app.state = result.state;
    app.history = result.history;
    renderPublic();
  } catch (error) {
    if (!silent) toast(error.message, true);
  }
}

async function loadAdmin() {
  await action(async () => {
    const result = await api("/api/admin");
    app.state = result.state;
    app.history = result.history;
    renderPublic();
    renderAdmin();
  });
}

async function refreshAll() {
  const result = await api("/api/admin");
  app.state = result.state;
  app.history = result.history;
  renderPublic();
  renderAdmin();
}

function renderPublic() {
  if (!app.state) return;
  const { game, participants, entry_fee: fee } = app.state;
  const prize = participants.length * Number(fee || 0);
  $("#scoreboard").classList.remove("skeleton");
  $("#scoreboard").innerHTML = `
    <div class="team"><div class="team-name">${escapeHtml(game.home_team)}</div><div class="score">${game.home_score}</div></div>
    <div><div class="score-separator">×</div><div class="score-meta">${game.finished ? "Encerrado" : "Em andamento"}</div></div>
    <div class="team"><div class="team-name">${escapeHtml(game.away_team)}</div><div class="score">${game.away_score}</div></div>
    <div class="metrics" style="grid-column:1/-1"><div class="metric"><strong>${participants.length}</strong><span>participantes</span></div><div class="metric"><strong>${money.format(prize)}</strong><span>prêmio acumulado</span></div><div class="metric"><strong>${money.format(fee)}</strong><span>por palpite</span></div></div>`;
  renderResult();
  const sorted = participants.map((participant) => ({ ...participant, status: guessStatus(participant, game) })).sort((a, b) => a.status.order - b.status.order || a.name.localeCompare(b.name, "pt-BR"));
  $("#participants").innerHTML = sorted.length ? sorted.map((participant) => `
    <article class="participant-card ${participant.status.style}"><span class="status">${participant.status.label}</span><h3>${escapeHtml(participant.name)}</h3><div class="guess">${participant.guess_home_score} × ${participant.guess_away_score}</div><small>${escapeHtml(game.home_team)} × ${escapeHtml(game.away_team)}</small></article>`).join("") : empty("Nenhum participante cadastrado ainda.");
  $("#last-update").textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  renderHistory($("#history-list"), false);
}

function renderResult() {
  const container = $("#result-banner");
  const { game, participants } = app.state;
  if (!game.finished) { container.innerHTML = ""; return; }
  const exact = participants.filter((item) => item.guess_home_score === game.home_score && item.guess_away_score === game.away_score);
  container.innerHTML = `<div class="result-banner">${exact.length ? `<strong>${exact.length === 1 ? "Vencedor" : "Vencedores"}: ${exact.map((item) => escapeHtml(item.name)).join(", ")}</strong><br><span>${money.format((participants.length * app.state.entry_fee) / exact.length)} para cada</span>` : "<strong>Ninguém acertou o placar exato.</strong>"}</div>`;
}

function guessStatus(participant, game) {
  const exact = participant.guess_home_score === game.home_score && participant.guess_away_score === game.away_score;
  if (exact) return { label: game.finished ? "Vencedor" : "Placar atual", order: 0, style: "exact" };
  if (!game.finished && participant.guess_home_score >= game.home_score && participant.guess_away_score >= game.away_score) return { label: "Ainda pode acertar", order: 1, style: "alive" };
  return { label: "Sem chance", order: 2, style: "out" };
}

function renderHistory(container, allowDelete) {
  const records = [...app.history].reverse();
  container.innerHTML = records.length ? records.map((record) => {
    const participants = record.participants || [];
    const winners = record.winners || [];
    return `<details class="history-card"><summary><div><span class="eyebrow">${escapeHtml(record.finished_at)}</span><h3>${escapeHtml(record.game.home_team)} × ${escapeHtml(record.game.away_team)}</h3></div><span class="history-score">${record.game.home_score} × ${record.game.away_score}</span></summary><div class="history-details"><div class="history-meta"><span>Prêmio <strong>${money.format(record.prize_pool)}</strong></span><span>Palpites <strong>${participants.length}</strong></span><span>Vencedor(es) <strong>${winners.length ? winners.map(escapeHtml).join(", ") : "Nenhum"}</strong></span></div>${participants.length ? `<div class="participant-grid">${participants.map((item) => `<div class="participant-card ${winners.includes(item.name) ? "exact" : ""}"><h3>${escapeHtml(item.name)}</h3><span class="guess">${item.guess_home_score} × ${item.guess_away_score}</span></div>`).join("")}</div>` : ""}${allowDelete ? `<div class="actions" style="margin-top:1rem"><button class="danger delete-history" data-id="${encodeURIComponent(record.id)}">Excluir histórico</button></div>` : ""}</div></details>`;
  }).join("") : empty("Nenhum bolão finalizado ainda.");
  if (allowDelete) $$(".delete-history", container).forEach((button) => button.addEventListener("click", () => confirmAction("Excluir este histórico?", "Esta ação não poderá ser desfeita.", async () => {
    await mutate(`/api/admin/history/${button.dataset.id}`, "DELETE", "Histórico excluído.");
  })));
}

function renderAdmin() {
  if (!app.state) return;
  const { game, participants, entry_fee: fee } = app.state;
  const form = $("#game-form");
  form.elements.home_team.value = game.home_team;
  form.elements.away_team.value = game.away_team;
  form.elements.home_score.value = game.home_score;
  form.elements.away_score.value = game.away_score;
  $("#fee-form").elements.entry_fee.value = Number(fee).toFixed(2);
  $("#game-status").textContent = game.finished ? "Finalizada" : "Em andamento";
  $("#finish-button").disabled = game.finished;
  $("#reopen-button").disabled = !game.finished;
  $("#new-pool-button").disabled = !game.finished;
  $("#participant-form").querySelector("button").disabled = game.finished;
  $("#admin-participant-count").textContent = `${participants.length} cadastrado${participants.length === 1 ? "" : "s"}`;
  $("#admin-participants").innerHTML = participants.length ? participants.map((participant) => `<div class="admin-row"><strong>${escapeHtml(participant.name)}</strong><span class="badge">${participant.guess_home_score} × ${participant.guess_away_score}</span><button class="danger delete-participant" data-id="${encodeURIComponent(participant.id)}">Excluir</button></div>`).join("") : empty("Nenhum participante cadastrado.");
  $$(".delete-participant").forEach((button) => button.addEventListener("click", () => confirmAction("Excluir participante?", "O palpite será removido do bolão atual.", async () => mutate(`/api/admin/participants/${button.dataset.id}`, "DELETE", "Participante excluído."))));
  renderHistory($("#admin-history"), true);
}

function showAdmin(authenticated) {
  $("#login-card").hidden = authenticated;
  $("#admin-app").hidden = !authenticated;
}

function confirmAction(title, message, callback) {
  const dialog = $("#confirm-dialog");
  $("#confirm-title").textContent = title;
  $("#confirm-message").textContent = message;
  dialog.returnValue = "";
  dialog.showModal();
  dialog.addEventListener("close", async function handler() {
    dialog.removeEventListener("close", handler);
    if (dialog.returnValue === "confirm") await callback();
  });
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 3500);
}

function empty(message) { return `<div class="empty">${escapeHtml(message)}</div>`; }
function currentView() { return $(".nav-button.active")?.dataset.view || "inicio"; }
