from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse, urlunparse
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None


DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "bolao.json"
LOGO_FILE = Path("assets") / "emblema-adega-camisa10.png"
SUPABASE_TABLE = "bolao_state"
SUPABASE_RECORD_ID = "default"
SUPABASE_POOLS_TABLE = "bolao_pools"
SUPABASE_POOL_PARTICIPANTS_TABLE = "bolao_pool_participants"

DEFAULT_STATE: dict[str, Any] = {
    "game": {
        "home_team": "Time da Casa",
        "away_team": "Visitante",
        "home_score": 0,
        "away_score": 0,
        "finished": False,
        "history_recorded": False,
        "history_record_id": None,
    },
    "entry_fee": 0.0,
    "participants": [],
    "history": [],
}


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    state.setdefault("game", {})
    state.setdefault("participants", [])
    state.setdefault("entry_fee", 0.0)
    state.setdefault("history", [])
    for key, value in DEFAULT_STATE["game"].items():
        state["game"].setdefault(key, value)
    for record in state["history"]:
        record.setdefault("id", str(uuid4()))
        for participant in record.get("participants", []):
            participant.setdefault("id", str(uuid4()))
    return state


def state_copy(state: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(state))


def secret_value(name: str) -> str:
    if os.getenv(name):
        return os.getenv(name, "")

    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""


def normalize_supabase_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path == "/rest/v1":
        path = ""

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def supabase_config() -> tuple[str, str]:
    return normalize_supabase_url(secret_value("SUPABASE_URL")), secret_value("SUPABASE_KEY").strip()


def supabase_enabled() -> bool:
    url, key = supabase_config()
    return bool(url and key)


def admin_password() -> str:
    return secret_value("BOLAO_ADMIN_PASSWORD") or "camisa10mjhs"


def supabase_headers(key: str) -> dict[str, str]:
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    if "." in key and not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"

    return headers


def supabase_request(method: str, path: str, payload: Any | None = None) -> Any:
    url, key = supabase_config()
    request = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        method=method,
        headers=supabase_headers(key),
    )

    if payload is not None:
        request.data = json.dumps(payload).encode("utf-8")

    with urllib.request.urlopen(request, timeout=12) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else None


def load_state_from_supabase() -> dict[str, Any] | None:
    rows = supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?id=eq.{SUPABASE_RECORD_ID}&select=state",
    )
    if not rows:
        return None
    return normalize_state(rows[0]["state"])


def save_state_to_supabase(state: dict[str, Any]) -> None:
    supabase_request(
        "POST",
        SUPABASE_TABLE,
        {
            "id": SUPABASE_RECORD_ID,
            "state": normalize_state(state_copy(state)),
        },
    )


def load_state_from_file() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return state_copy(DEFAULT_STATE)

    with DATA_FILE.open("r", encoding="utf-8") as file:
        return normalize_state(json.load(file))


def save_state_to_file(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(normalize_state(state_copy(state)), file, ensure_ascii=False, indent=2)


def load_state() -> dict[str, Any]:
    if supabase_enabled():
        try:
            state = load_state_from_supabase()
            if state is not None:
                return state

            state = normalize_state(state_copy(DEFAULT_STATE))
            save_state_to_supabase(state)
            return state
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as error:
            st.warning(f"Falha ao carregar dados do Supabase. Usando armazenamento local. Detalhe: {error}")

    state = load_state_from_file()
    if not DATA_FILE.exists():
        save_state_to_file(state)
    return state


def save_state(state: dict[str, Any]) -> None:
    state = normalize_state(state_copy(state))

    if supabase_enabled():
        try:
            save_state_to_supabase(state)
            return
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as error:
            st.warning(f"Falha ao salvar no Supabase. Salvando localmente. Detalhe: {error}")

    save_state_to_file(state)


def enable_public_auto_refresh() -> None:
    if st_autorefresh is None:
        st.caption("Atualizacao automatica indisponivel neste ambiente.")
        return

    st_autorefresh(interval=2000, key="public_live_score_refresh")


def supabase_error_detail(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        body = error.read().decode("utf-8", errors="ignore")
        return f"HTTP {error.code}: {body or error.reason}"
    return str(error)


def history_supabase_error(error: Exception) -> bool:
    return isinstance(
        error,
        (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError),
    )


def save_history_record_to_supabase(record: dict[str, Any]) -> None:
    supabase_request(
        "POST",
        SUPABASE_POOLS_TABLE,
        {
            "id": record["id"],
            "home_team": record["game"]["home_team"],
            "away_team": record["game"]["away_team"],
            "home_score": int(record["game"]["home_score"]),
            "away_score": int(record["game"]["away_score"]),
            "entry_fee": float(record["entry_fee"]),
            "prize_pool": float(record["prize_pool"]),
            "prize_per_winner": float(record.get("prize_per_winner", 0.0)),
            "winners": record.get("winners", []),
            "finished_at": record["finished_at"],
        },
    )

    participant_rows = []
    winner_names = set(record.get("winners", []))
    for participant in record.get("participants", []):
        participant_rows.append(
            {
                "id": participant.get("id", str(uuid4())),
                "pool_id": record["id"],
                "name": participant["name"],
                "guess_home_score": int(participant["guess_home_score"]),
                "guess_away_score": int(participant["guess_away_score"]),
                "is_winner": participant["name"] in winner_names,
            }
        )

    if participant_rows:
        supabase_request("POST", SUPABASE_POOL_PARTICIPANTS_TABLE, participant_rows)


def load_history_from_supabase() -> list[dict[str, Any]]:
    pools = supabase_request(
        "GET",
        f"{SUPABASE_POOLS_TABLE}?select=*&order=created_at.desc",
    )
    if not pools:
        return []

    pool_ids = [pool["id"] for pool in pools]
    participants = supabase_request(
        "GET",
        (
            f"{SUPABASE_POOL_PARTICIPANTS_TABLE}"
            f"?pool_id=in.({','.join(pool_ids)})&select=*"
        ),
    )

    participants_by_pool: dict[str, list[dict[str, Any]]] = {}
    for participant in participants or []:
        participants_by_pool.setdefault(participant["pool_id"], []).append(
            {
                "id": participant.get("id", ""),
                "name": participant["name"],
                "guess_home_score": participant["guess_home_score"],
                "guess_away_score": participant["guess_away_score"],
            }
        )

    history = []
    for pool in pools:
        history.append(
            {
                "id": pool["id"],
                "finished_at": pool["finished_at"],
                "game": {
                    "home_team": pool["home_team"],
                    "away_team": pool["away_team"],
                    "home_score": pool["home_score"],
                    "away_score": pool["away_score"],
                },
                "entry_fee": float(pool.get("entry_fee", 0.0)),
                "prize_pool": float(pool.get("prize_pool", 0.0)),
                "prize_per_winner": float(pool.get("prize_per_winner", 0.0)),
                "winners": pool.get("winners", []),
                "participants": participants_by_pool.get(pool["id"], []),
            }
        )

    return list(reversed(history))


def load_history(state: dict[str, Any]) -> list[dict[str, Any]]:
    if supabase_enabled():
        try:
            split_history = load_history_from_supabase()
            split_history_ids = {record["id"] for record in split_history}
            legacy_history = [
                record
                for record in state.get("history", [])
                if record.get("id") not in split_history_ids
            ]
            return legacy_history + split_history
        except Exception as error:
            if history_supabase_error(error):
                st.warning(
                    "Falha ao carregar historico separado do Supabase. "
                    f"Usando historico antigo. Detalhe: {supabase_error_detail(error)}"
                )
            else:
                raise

    return state.get("history", [])


def delete_history_from_supabase(record_id: str) -> None:
    supabase_request(
        "DELETE",
        f"{SUPABASE_POOL_PARTICIPANTS_TABLE}?pool_id=eq.{record_id}",
    )
    supabase_request("DELETE", f"{SUPABASE_POOLS_TABLE}?id=eq.{record_id}")


def delete_history_record(state: dict[str, Any], record_id: str) -> None:
    if supabase_enabled():
        try:
            delete_history_from_supabase(record_id)
        except Exception as error:
            if history_supabase_error(error):
                st.warning(f"Falha ao apagar historico no Supabase. Detalhe: {supabase_error_detail(error)}")
            else:
                raise

    state["history"] = [
        record for record in state.get("history", []) if record.get("id") != record_id
    ]
    save_state(state)


def format_currency(value: float | int) -> str:
    formatted = f"{float(value):,.2f}"
    return f"R$ {formatted}".replace(",", "X").replace(".", ",").replace("X", ".")


def logo_markup() -> str:
    if not LOGO_FILE.exists():
        return '<div class="brand-logo-slot brand-logo-fallback">10</div>'

    encoded_logo = base64.b64encode(LOGO_FILE.read_bytes()).decode("ascii")
    return (
        '<div class="brand-logo-slot">'
        f'<img src="data:image/png;base64,{encoded_logo}" alt="Adega Camisa 10">'
        "</div>"
    )


def calculate_prize_pool(state: dict[str, Any]) -> float:
    return len(state["participants"]) * float(state.get("entry_fee", 0.0))


def reset_game(state: dict[str, Any]) -> None:
    state["game"] = json.loads(json.dumps(DEFAULT_STATE["game"]))


def start_new_pool(state: dict[str, Any]) -> None:
    state["participants"] = []
    reset_game(state)


def confirmation_key(name: str) -> str:
    version = st.session_state.setdefault("_confirmation_version", 0)
    return f"{name}_{version}"


def reset_confirmation_widgets() -> None:
    st.session_state["_confirmation_version"] = (
        st.session_state.get("_confirmation_version", 0) + 1
    )


def admin_game_widgets_ready() -> bool:
    return all(
        key in st.session_state
        for key in (
            "admin_home_team",
            "admin_away_team",
            "admin_home_score",
            "admin_away_score",
        )
    )


def admin_game_widget_values() -> dict[str, Any]:
    return {
        "home_team": st.session_state.get("admin_home_team", "").strip() or "Time da Casa",
        "away_team": st.session_state.get("admin_away_team", "").strip() or "Visitante",
        "home_score": int(st.session_state.get("admin_home_score", 0)),
        "away_score": int(st.session_state.get("admin_away_score", 0)),
    }


def sync_admin_game_widgets(state: dict[str, Any]) -> bool:
    if not admin_game_widgets_ready():
        return False

    game = state["game"]
    values = admin_game_widget_values()
    changed = any(game[key] != values[key] for key in values)
    if not changed:
        return False

    game.update(values)
    if game.get("finished"):
        game["finished"] = False
        game["history_recorded"] = False
    st.session_state["_admin_game_snapshot"] = (
        game["home_team"],
        game["away_team"],
        int(game["home_score"]),
        int(game["away_score"]),
    )
    save_state(state)
    return True


def prepare_admin_game_widgets(game: dict[str, Any]) -> None:
    snapshot = (
        game["home_team"],
        game["away_team"],
        int(game["home_score"]),
        int(game["away_score"]),
    )
    if (
        admin_game_widgets_ready()
        and st.session_state.get("_admin_game_snapshot") == snapshot
    ):
        return

    st.session_state["admin_home_team"] = game["home_team"]
    st.session_state["admin_away_team"] = game["away_team"]
    st.session_state["admin_home_score"] = int(game["home_score"])
    st.session_state["admin_away_score"] = int(game["away_score"])
    st.session_state["_admin_game_snapshot"] = snapshot


def exact_score_winners(state: dict[str, Any]) -> list[dict[str, Any]]:
    game = state["game"]
    return [
        participant
        for participant in state["participants"]
        if participant["guess_home_score"] == game["home_score"]
        and participant["guess_away_score"] == game["away_score"]
    ]


def prize_per_winner(state: dict[str, Any]) -> float:
    winners = exact_score_winners(state)
    if not winners:
        return 0.0
    return calculate_prize_pool(state) / len(winners)


def build_history_record(state: dict[str, Any]) -> dict[str, Any]:
    game = state["game"]
    winners = exact_score_winners(state)
    participants = json.loads(json.dumps(state["participants"]))
    for participant in participants:
        participant.setdefault("id", str(uuid4()))

    return {
        "id": str(uuid4()),
        "finished_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "game": {
            "home_team": game["home_team"],
            "away_team": game["away_team"],
            "home_score": game["home_score"],
            "away_score": game["away_score"],
        },
        "entry_fee": float(state.get("entry_fee", 0.0)),
        "prize_pool": calculate_prize_pool(state),
        "prize_per_winner": prize_per_winner(state),
        "winners": [winner["name"] for winner in winners],
        "participants": participants,
    }


def save_finished_game_to_history(state: dict[str, Any]) -> None:
    # History must reflect the values currently visible in the admin editor,
    # even when Streamlit has not yet propagated the last field edit.
    sync_admin_game_widgets(state)
    state["game"]["finished"] = True

    if state["game"].get("history_recorded"):
        return

    record = build_history_record(state)
    if supabase_enabled():
        try:
            save_history_record_to_supabase(record)
        except Exception as error:
            if history_supabase_error(error):
                st.warning(
                    "Falha ao salvar historico separado no Supabase. "
                    f"Salvando no formato antigo. Detalhe: {supabase_error_detail(error)}"
                )
                state["history"].append(record)
            else:
                raise
    else:
        state["history"].append(record)

    state["game"]["history_recorded"] = True
    state["game"]["history_record_id"] = record["id"]


def reopen_game(state: dict[str, Any]) -> None:
    record_id = state["game"].get("history_record_id")
    if record_id:
        delete_history_record(state, record_id)

    state["game"]["finished"] = False
    state["game"]["history_recorded"] = False
    state["game"]["history_record_id"] = None
    save_state(state)


def guess_status(participant: dict[str, Any], game: dict[str, Any]) -> dict[str, Any]:
    guess_home = participant["guess_home_score"]
    guess_away = participant["guess_away_score"]
    actual_home = game["home_score"]
    actual_away = game["away_score"]
    exact_score = guess_home == actual_home and guess_away == actual_away

    if exact_score:
        label = "Vencedor" if game.get("finished") else "Placar atual"
        return {"label": label, "order": 0, "style": "exact"}

    if game.get("finished"):
        return {"label": "Sem chance", "order": 2, "style": "out"}

    if guess_home >= actual_home and guess_away >= actual_away:
        return {"label": "Ainda pode acertar", "order": 1, "style": "alive"}

    return {"label": "Sem chance", "order": 2, "style": "out"}


def participants_table(state: dict[str, Any]) -> pd.DataFrame:
    rows = []
    game = state["game"]

    for participant in state["participants"]:
        status = guess_status(participant, game)
        rows.append(
            {
                "Participante": participant["name"],
                "Palpite": (
                    f'{participant["guess_home_score"]} x '
                    f'{participant["guess_away_score"]}'
                ),
                "Time casa": game["home_team"],
                "Time visitante": game["away_team"],
                "Gols casa": participant["guess_home_score"],
                "Gols visitante": participant["guess_away_score"],
                "Situacao": status["label"],
                "_order": status["order"],
                "_style": status["style"],
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Participante",
                "Palpite",
                "Time casa",
                "Time visitante",
                "Gols casa",
                "Gols visitante",
                "Situacao",
                "_order",
                "_style",
            ]
        )

    table = pd.DataFrame(rows)
    return table.sort_values(
        by=["_order", "Participante"],
        ascending=[True, True],
        ignore_index=True,
    )


def render_scoreboard(game: dict[str, Any]) -> None:
    st.markdown(
        (
            '<section class="score-shell">'
            '<div class="score-meta">'
            '<span class="match-label">Placar do jogo</span>'
            "</div>"
            '<div class="scoreboard">'
            '<div class="team">'
            f'<span>{escape(game["home_team"])}</span>'
            f'<strong>{game["home_score"]}</strong>'
            "</div>"
            '<div class="separator">x</div>'
            '<div class="team">'
            f'<span>{escape(game["away_team"])}</span>'
            f'<strong>{game["away_score"]}</strong>'
            "</div>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def render_match_metrics(total_participants: int, prize_pool: float | int) -> None:
    st.markdown(
        (
            '<section class="match-metrics">'
            '<div class="metric-card">'
            "<span>Total de participantes</span>"
            f"<strong>{total_participants}</strong>"
            "</div>"
            '<div class="metric-card metric-prize">'
            "<span>Premio acumulado</span>"
            f"<strong>{format_currency(prize_pool)}</strong>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def render_final_result(state: dict[str, Any]) -> None:
    if not state["game"].get("finished"):
        return

    winners = exact_score_winners(state)
    prize_share = prize_per_winner(state)

    if not winners:
        st.markdown(
            (
                '<section class="result-panel result-empty">'
                "<span>Partida finalizada</span>"
                "<strong>Nao houve vencedor</strong>"
                "<p>Nenhum participante acertou o placar final.</p>"
                "</section>"
            ),
            unsafe_allow_html=True,
        )
        return

    winner_names = ", ".join(escape(winner["name"]) for winner in winners)
    st.markdown(
        (
            '<section class="result-panel result-winners">'
            "<span>Partida finalizada</span>"
            f"<strong>{len(winners)} vencedor(es)</strong>"
            f"<p>{winner_names}</p>"
            f"<em>{format_currency(prize_share)} para cada vencedor</em>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def render_leaderboard(table: pd.DataFrame) -> None:
    if table.empty:
        st.info("Nenhum participante cadastrado ainda.")
        return

    rows = []
    for _, row in table.iterrows():
        rows.append(
            (
                f'<article class="rank-row rank-{escape(row["_style"])}">'
                '<div class="rank-person">'
                f'<strong>{escape(row["Participante"])}</strong>'
                f'<span>{escape(row["Situacao"])}</span>'
                "</div>"
                '<div class="rank-guess">'
                f'<span class="rank-team rank-home">{escape(row["Time casa"])}</span>'
                '<strong>'
                f'{int(row["Gols casa"])} x {int(row["Gols visitante"])}'
                "</strong>"
                f'<span class="rank-team rank-away">{escape(row["Time visitante"])}</span>'
                "</div>"
                "</article>"
            )
        )

    st.markdown(
        f'<section class="leaderboard">{"".join(rows)}</section>',
        unsafe_allow_html=True,
    )


def render_admin_match_controls(state: dict[str, Any]) -> None:
    game = state["game"]
    prepare_admin_game_widgets(game)

    with st.container(key="admin_score_editor"):
        st.markdown('<span class="admin-scoreboard-marker"></span>', unsafe_allow_html=True)
        st.markdown('<div class="score-meta"><span class="match-label">Placar do jogo</span></div>', unsafe_allow_html=True)

        home_col, separator_col, away_col = st.columns([1, 0.18, 1], gap="small")
        with home_col:
            st.text_input(
                "Time da casa",
                key="admin_home_team",
                disabled=game.get("finished", False),
                on_change=sync_admin_game_widgets,
                args=(state,),
            )
            st.number_input(
                "Gols casa",
                min_value=0,
                max_value=99,
                step=1,
                key="admin_home_score",
                disabled=game.get("finished", False),
                on_change=sync_admin_game_widgets,
                args=(state,),
            )
        with separator_col:
            st.markdown('<div class="admin-score-separator">x</div>', unsafe_allow_html=True)
        with away_col:
            st.text_input(
                "Time visitante",
                key="admin_away_team",
                disabled=game.get("finished", False),
                on_change=sync_admin_game_widgets,
                args=(state,),
            )
            st.number_input(
                "Gols visitante",
                min_value=0,
                max_value=99,
                step=1,
                key="admin_away_score",
                disabled=game.get("finished", False),
                on_change=sync_admin_game_widgets,
                args=(state,),
            )

        st.markdown('<div class="admin-panel-title">Finalizacao</div>', unsafe_allow_html=True)
        finish_column, reopen_column = st.columns(2, gap="small")
        with finish_column:
            if st.button("Finalizar partida", disabled=game.get("finished", False)):
                sync_admin_game_widgets(state)
                game["finished"] = True
                save_finished_game_to_history(state)
                save_state(state)
                st.success("Partida finalizada.")
                st.rerun()
        with reopen_column:
            if st.button("Reabrir partida", disabled=not game.get("finished", False)):
                reopen_game(state)
                st.success("Partida reaberta.")
                st.rerun()

    st.markdown('<section class="admin-new-pool">', unsafe_allow_html=True)
    st.markdown('<div class="admin-panel-title">Iniciar outro bolao</div>', unsafe_allow_html=True)
    st.caption("Finalize a partida atual antes de iniciar outro bolao.")
    confirm_new_pool = st.checkbox(
        "Confirmo que desejo iniciar outro bolao e remover os participantes atuais.",
        key=confirmation_key("confirm_new_pool"),
        disabled=not game.get("finished", False),
    )
    if st.button(
        "Iniciar outro bolao",
        type="primary",
        disabled=not game.get("finished", False),
    ):
        if not confirm_new_pool:
            st.warning("Confirme que deseja remover os participantes e iniciar outro bolao.")
            return

        start_new_pool(state)
        save_state(state)
        reset_confirmation_widgets()
        st.success("Novo bolao iniciado.")
        st.rerun()
    st.markdown("</section>", unsafe_allow_html=True)


def main_panel(state: dict[str, Any], is_admin: bool = False) -> None:
    game = state["game"]
    ranking = participants_table(state)

    score_column, rank_column = st.columns([1.12, 0.88], gap="large")

    with score_column:
        if is_admin:
            render_admin_match_controls(state)
        else:
            render_scoreboard(game)
        render_match_metrics(len(state["participants"]), calculate_prize_pool(state))
        render_final_result(state)

    with rank_column:
        st.markdown('<h2 class="section-title">Mesa do bolao</h2>', unsafe_allow_html=True)
        render_leaderboard(ranking)


def participants_panel(state: dict[str, Any]) -> None:
    game = state["game"]
    entry_fee = float(state.get("entry_fee", 0.0))

    st.markdown('<h2 class="section-title">Participantes</h2>', unsafe_allow_html=True)
    config_column, participant_column = st.columns([0.85, 1.15], gap="large")

    with config_column:
        st.markdown('<div class="admin-panel-title">Valor do palpite</div>', unsafe_allow_html=True)
        with st.form("entry_fee_form"):
            new_entry_fee = st.number_input(
                "Valor por cadastro de palpite",
                min_value=0.0,
                value=entry_fee,
                step=5.0,
                format="%.2f",
            )

            if st.form_submit_button("Salvar valor", type="primary"):
                state["entry_fee"] = float(new_entry_fee)
                save_state(state)
                st.success("Valor por palpite atualizado.")
                st.rerun()

    with participant_column:
        st.markdown('<div class="admin-panel-title">Novo participante</div>', unsafe_allow_html=True)
        with st.form("participant_form", clear_on_submit=True):
            name = st.text_input("Nome do participante")
            guess_col_1, guess_col_2 = st.columns(2)
            with guess_col_1:
                guess_home = st.number_input(
                    f'Palpite {game["home_team"]}',
                    min_value=0,
                    max_value=99,
                    value=0,
                    step=1,
                )
            with guess_col_2:
                guess_away = st.number_input(
                    f'Palpite {game["away_team"]}',
                    min_value=0,
                    max_value=99,
                    value=0,
                    step=1,
                )

            if st.form_submit_button("Adicionar participante"):
                participant_name = name.strip()
                if not participant_name:
                    st.warning("Informe o nome do participante.")
                elif any(
                    item["name"].lower() == participant_name.lower()
                    for item in state["participants"]
                ):
                    st.warning("Ja existe um participante com esse nome.")
                else:
                    state["participants"].append(
                        {
                            "name": participant_name,
                            "guess_home_score": int(guess_home),
                            "guess_away_score": int(guess_away),
                        }
                    )
                    save_state(state)
                    st.success("Participante cadastrado.")
                    st.rerun()

    st.divider()
    st.markdown('<h2 class="section-title">Participantes cadastrados</h2>', unsafe_allow_html=True)
    if not state["participants"]:
        st.caption("Nenhum participante cadastrado.")
        return

    for index, participant in enumerate(state["participants"]):
        col_name, col_guess, col_action = st.columns([2, 1, 0.8])
        col_name.write(participant["name"])
        col_guess.write(
            f'{participant["guess_home_score"]} x {participant["guess_away_score"]}'
        )
        if col_action.button("Remover", key=f"remove_{index}"):
            state["participants"].pop(index)
            save_state(state)
            st.rerun()


def history_panel(state: dict[str, Any], allow_delete: bool = False) -> None:
    st.markdown('<h2 class="section-title">Historico de boloes</h2>', unsafe_allow_html=True)

    history = load_history(state)
    if not history:
        st.info("Nenhum bolao finalizado ainda.")
        return

    for record in reversed(history):
        game = record["game"]
        title = (
            f'{game["home_team"]} {game["home_score"]} x '
            f'{game["away_score"]} {game["away_team"]}'
        )
        winner_names = record.get("winners", [])
        winners_text = ", ".join(escape(name) for name in winner_names) or "Nao houve vencedor"

        participant_rows = []
        for participant in record.get("participants", []):
            is_winner = participant["name"] in winner_names
            participant_rows.append(
                "<tr>"
                f"<td>{escape(participant['name'])}</td>"
                f"<td>{participant['guess_home_score']} x {participant['guess_away_score']}</td>"
                f"<td>{'Vencedor' if is_winner else 'Participou'}</td>"
                "</tr>"
            )

        participants_table_html = (
            "<table>"
            "<thead><tr><th>Participante</th><th>Palpite</th><th>Resultado</th></tr></thead>"
            f"<tbody>{''.join(participant_rows)}</tbody>"
            "</table>"
            if participant_rows
            else "<p>Este bolao foi finalizado sem participantes.</p>"
        )

        header = title
        if allow_delete:
            expander_col, date_col, action_col = st.columns([0.74, 0.16, 0.10], gap="small")
        else:
            expander_col, date_col = st.columns([0.78, 0.22], gap="small")
            action_col = None

        with expander_col:
            with st.expander(header):
                st.markdown(
                    (
                        '<article class="history-card history-card-open">'
                        '<div class="history-card-grid">'
                        f"<div><span>Premio total</span><strong>{format_currency(record['prize_pool'])}</strong></div>"
                        f"<div><span>Vencedores</span><strong>{len(winner_names)}</strong></div>"
                        f"<div><span>Valor por vencedor</span><strong>{format_currency(record.get('prize_per_winner', 0.0))}</strong></div>"
                        "</div>"
                        '<div class="history-card-summary">'
                        f"<p><strong>Vencedores:</strong> {winners_text}</p>"
                        f"<p><strong>Valor por palpite:</strong> {format_currency(record['entry_fee'])}</p>"
                        "</div>"
                        f'<div class="history-table">{participants_table_html}</div>'
                        "</article>"
                    ),
                    unsafe_allow_html=True,
                )

        with date_col:
            st.markdown(
                f'<div class="history-date-chip">{escape(record["finished_at"])}</div>',
                unsafe_allow_html=True,
            )

        if action_col is not None:
            with action_col:
                if st.button("Excluir", key=f"delete_history_{record['id']}", help="Apagar este historico"):
                    delete_history_record(state, record["id"])
                    st.success("Historico apagado.")
                    st.rerun()


def admin_login_panel() -> None:
    st.markdown('<h2 class="section-title">Acesso do administrador</h2>', unsafe_allow_html=True)
    st.caption("Entre para cadastrar jogos, participantes, placares e finalizar partidas.")

    with st.form("admin_login_form"):
        password = st.text_input("Senha do administrador", type="password")
        login_clicked = st.form_submit_button("Entrar", type="primary")

        if login_clicked:
            if password == admin_password():
                st.session_state["admin_authenticated"] = True
                st.session_state["admin_section"] = "Painel do Bolão"
                st.success("Acesso liberado.")
                st.rerun()
            else:
                st.warning("Senha incorreta.")


def admin_logout_panel() -> None:
    st.markdown('<h2 class="section-title">Sessao administrativa</h2>', unsafe_allow_html=True)
    st.caption("Use esta opcao ao terminar os cadastros ou ajustes da partida.")

    if st.button("Sair do administrador"):
        st.session_state["admin_authenticated"] = False
        reset_confirmation_widgets()
        st.rerun()


def change_admin_section(state: dict[str, Any]) -> None:
    """Persist match edits before Streamlit removes the previous section widgets."""
    sync_admin_game_widgets(state)


def admin_area(state: dict[str, Any]) -> None:
    try:
        admin_sections = [
            "Painel do Bolão",
            "Participantes",
            "Historico",
            "Sair admin",
        ]
        if st.session_state.get("admin_section") not in admin_sections:
            st.session_state["admin_section"] = "Painel do Bolão"

        section = st.radio(
            "Area administrativa",
            admin_sections,
            horizontal=True,
            key="admin_section",
            label_visibility="collapsed",
            on_change=change_admin_section,
            args=(state,),
        )

        previous_section = st.session_state.get("_last_admin_section")
        if previous_section == "Painel do Bolão" and section != "Painel do Bolão":
            sync_admin_game_widgets(state)
        st.session_state["_last_admin_section"] = section

        if section == "Painel do Bolão":
            main_panel(state, is_admin=True)
        elif section == "Participantes":
            participants_panel(state)
        elif section == "Historico":
            history_panel(state, allow_delete=True)
        elif section == "Sair admin":
            admin_logout_panel()
    except Exception as error:
        st.error(f"Falha ao carregar a area administrativa: {error}")
        st.caption("Saia do administrador e entre novamente. Se persistir, reinicie o app.")
        if st.button("Sair do administrador", key="admin_area_error_logout"):
            st.session_state["admin_authenticated"] = False
            reset_confirmation_widgets()
            st.rerun()


def apply_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Bangers&display=swap');

            :root {
                color-scheme: dark;
                --bg: #04110b;
                --ink: #fff8ed;
                --muted: #c5d6bf;
                --line: #24492f;
                --panel: #071c11;
                --panel-2: #0d2b19;
                --field: #06140d;
                --wine: #14532d;
                --wine-dark: #06200f;
                --green: #19a45b;
                --green-soft: #0c351f;
                --green-strong: #146c3b;
                --red: #ef5f56;
                --red-soft: #3a1718;
                --amber: #ffd21f;
                --amber-soft: #3f3108;
                --blue: #1f5fd1;
                --blue-soft: #0a1f48;
                --grass: #0d3a22;
                --navy: #06170e;
                --graffiti-font: "Bangers", "Impact", "Arial Black", sans-serif;
            }

            html,
            body,
            [data-testid="stAppViewContainer"],
            [data-testid="stAppViewContainer"] > .main {
                background-color: var(--bg) !important;
                color: var(--ink) !important;
                color-scheme: dark !important;
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(255, 210, 31, .18), transparent 28rem),
                    radial-gradient(circle at bottom right, rgba(31, 95, 209, .16), transparent 24rem),
                    linear-gradient(180deg, #062013 0%, var(--bg) 100%);
                color: var(--ink);
                font-family: var(--graffiti-font);
            }

            .stApp * {
                font-family: var(--graffiti-font);
                letter-spacing: .035em;
            }

            .block-container {
                max-width: 1220px;
                padding-bottom: 3rem;
                padding-top: .85rem;
            }

            header[data-testid="stHeader"],
            div[data-testid="stToolbar"] {
                display: none;
            }

            h1 {
                color: var(--ink);
                font-size: 2.05rem !important;
                font-weight: 800 !important;
                margin-bottom: .2rem !important;
            }

            .brand-hero {
                align-items: center;
                background:
                    linear-gradient(135deg, rgba(255, 210, 31, .98), rgba(26, 116, 62, .92) 58%, rgba(31, 95, 209, .80)),
                    var(--panel);
                border: 1px solid #d4aa13;
                border-radius: 8px;
                box-shadow: 0 20px 42px rgba(0, 0, 0, .38);
                display: grid;
                gap: 1rem;
                grid-template-columns: 4rem minmax(0, 1fr);
                margin-bottom: 1.1rem;
                overflow: hidden;
                padding: .95rem 1.05rem;
                position: relative;
            }

            .brand-hero::after {
                background:
                    linear-gradient(90deg, transparent 0 47%, rgba(255, 255, 255, .08) 47% 53%, transparent 53%),
                    repeating-linear-gradient(90deg, rgba(255, 255, 255, .045) 0 1px, transparent 1px 84px);
                content: "";
                inset: 0;
                pointer-events: none;
                position: absolute;
            }

            .brand-kicker {
                color: #161006;
                display: block;
                font-size: .74rem;
                font-weight: 900;
                letter-spacing: .08em;
                position: relative;
                text-transform: uppercase;
                z-index: 1;
            }

            .brand-title {
                color: #100b05;
                display: block;
                font-size: clamp(1.65rem, 4vw, 2.45rem);
                font-weight: 900;
                line-height: 1;
                margin-top: .2rem;
                position: relative;
                z-index: 1;
            }

            .brand-logo-slot {
                align-items: center;
                background: rgba(255, 255, 255, .34);
                border: 1px solid rgba(16, 11, 5, .16);
                border-radius: 999px;
                color: #100b05;
                display: flex;
                font-size: 1.3rem;
                font-weight: 900;
                height: 4rem;
                justify-content: center;
                overflow: hidden;
                position: relative;
                width: 4rem;
                z-index: 1;
            }

            .brand-logo-slot img {
                border-radius: 999px;
                display: block;
                height: 100%;
                object-fit: cover;
                transform: scale(1.12);
                width: 100%;
            }

            .brand-logo-fallback {
                box-shadow: inset 0 0 0 2px rgba(16, 11, 5, .10);
            }

            .brand-copy {
                min-width: 0;
                position: relative;
                z-index: 1;
            }

            .brand-subtitle {
                color: var(--muted);
                display: block;
                font-size: 1rem;
                font-weight: 700;
                margin-top: .55rem;
                max-width: 720px;
                position: relative;
                z-index: 1;
            }

            [data-testid="stCaptionContainer"] {
                color: var(--muted);
            }

            label,
            p,
            span,
            div {
                text-shadow: none;
            }

            [data-testid="stMetric"] {
                background: var(--panel);
                border: 1px solid var(--line);
                border-radius: 8px;
                padding: .85rem 1rem;
            }

            [data-testid="stMetricLabel"] p {
                color: var(--muted);
                font-weight: 800;
            }

            [data-testid="stMetricValue"] {
                color: var(--ink);
            }

            .stTabs [data-baseweb="tab-list"] {
                gap: .35rem;
                margin-top: 1.1rem;
            }

            .stTabs [data-baseweb="tab"] {
                background: #092216;
                border-radius: 8px 8px 0 0;
                border: 1px solid #1a5131;
                color: #ffffff !important;
                font-weight: 700;
                height: 2.75rem;
                opacity: 1 !important;
                padding: 0 1rem;
            }

            .stTabs [data-baseweb="tab"] *,
            .stTabs [data-baseweb="tab"] p {
                color: #ffffff !important;
                opacity: 1 !important;
            }

            .stTabs [aria-selected="false"],
            .stTabs [aria-selected="false"] *,
            .stTabs [aria-selected="false"] p {
                color: #ffffff !important;
                opacity: 1 !important;
                text-shadow: 0 1px 2px rgba(0, 0, 0, .75);
            }

            .stTabs [aria-selected="true"] {
                background: #3f3108;
                border-color: var(--amber);
                color: #ffffff !important;
                opacity: 1 !important;
            }

            div[data-testid="stRadio"] div[role="radiogroup"] {
                display: flex;
                flex-wrap: wrap;
                gap: .35rem;
                margin-top: 1.1rem;
            }

            div[data-testid="stRadio"] label {
                background: #092216;
                border: 1px solid #1a5131;
                border-radius: 8px 8px 0 0;
                color: #ffffff !important;
                min-height: 2.75rem;
                opacity: 1 !important;
                padding: 0 1rem;
            }

            div[data-testid="stRadio"] label:has(input[aria-checked="true"]) {
                background: #3f3108;
                border-color: var(--amber);
                border-bottom-color: var(--red);
                box-shadow: inset 0 -2px 0 var(--red);
            }

            div[data-testid="stRadio"] label > div:first-child {
                display: none !important;
            }

            div[data-testid="stRadio"] label > div:first-child,
            div[data-testid="stRadio"] label > div:first-child * {
                height: 0 !important;
                margin: 0 !important;
                min-height: 0 !important;
                min-width: 0 !important;
                opacity: 0 !important;
                padding: 0 !important;
                width: 0 !important;
            }

            div[data-testid="stRadio"] input,
            div[data-testid="stRadio"] svg,
            div[data-testid="stRadio"] label [data-baseweb="radio"],
            div[data-testid="stRadio"] label [role="radio"],
            div[data-testid="stRadio"] label [aria-checked] {
                display: none !important;
                height: 0 !important;
                opacity: 0 !important;
                width: 0 !important;
            }

            div[data-testid="stRadio"] label p,
            div[data-testid="stRadio"] label span,
            div[data-testid="stRadio"] label div {
                color: #ffffff !important;
                font-weight: 700;
                opacity: 1 !important;
                text-shadow: 0 1px 2px rgba(0, 0, 0, .75);
            }

            .section-title {
                color: var(--ink);
                font-size: 1.1rem;
                font-weight: 800;
                letter-spacing: .05em;
                margin: .25rem 0 .85rem;
            }

            .score-shell,
            .leaderboard,
            .match-metrics,
            div[data-testid="stForm"],
            div[data-testid="stDataFrame"],
            div[data-testid="stVerticalBlock"] > div:has(.admin-panel-title) {
                border-radius: 8px;
            }

            .score-shell {
                background: var(--panel);
                border: 1px solid var(--line);
                box-shadow: 0 18px 36px rgba(0, 0, 0, .34);
                overflow: hidden;
            }

            .score-meta,
            .match-metrics {
                align-items: center;
                display: flex;
                justify-content: space-between;
                padding: 1rem 1.15rem;
            }

            .score-meta {
                border-bottom: 1px solid var(--line);
            }

            .match-label {
                color: var(--amber);
                font-size: .85rem;
                font-weight: 800;
                letter-spacing: .08em;
                text-transform: uppercase;
            }

            .admin-score-separator {
                align-items: center;
                color: var(--amber);
                display: flex;
                font-size: 2rem;
                font-weight: 900;
                min-height: 8rem;
                justify-content: center;
                text-transform: uppercase;
            }

            .scoreboard {
                align-items: center;
                background:
                    linear-gradient(90deg, transparent 0 48%, rgba(255, 255, 255, .08) 48% 52%, transparent 52%),
                    repeating-linear-gradient(90deg, rgba(255, 255, 255, .035) 0 1px, transparent 1px 72px),
                    linear-gradient(135deg, rgba(5, 34, 18, .98), rgba(14, 94, 47, .98)),
                    var(--navy);
                border: 1px solid #1f6f42;
                border-radius: 8px;
                color: #f8fafc;
                display: grid;
                gap: 1rem;
                grid-template-columns: 1fr auto 1fr;
                min-height: 260px;
                padding: 1.5rem;
            }

            .team {
                align-items: center;
                display: flex;
                flex-direction: column;
                gap: .75rem;
                min-width: 0;
                text-align: center;
            }

            .team span {
                color: #e4f6df;
                font-size: 1.2rem;
                font-weight: 700;
                letter-spacing: .055em;
                overflow-wrap: anywhere;
            }

            .team strong {
                font-size: clamp(4.5rem, 9vw, 7.75rem);
                line-height: .9;
            }

            .separator {
                color: var(--amber);
                font-size: 2rem;
                font-weight: 700;
            }

            .st-key-admin_score_editor {
                background:
                    linear-gradient(90deg, transparent 0 48%, rgba(255, 255, 255, .08) 48% 52%, transparent 52%),
                    repeating-linear-gradient(90deg, rgba(255, 255, 255, .035) 0 1px, transparent 1px 72px),
                    linear-gradient(135deg, rgba(5, 34, 18, .98), rgba(14, 94, 47, .98)),
                    var(--navy) !important;
                border: 1px solid #1f6f42 !important;
                box-shadow: 0 18px 36px rgba(0, 0, 0, .34);
                min-height: 260px;
                overflow: hidden;
            }

            .st-key-admin_score_editor [data-testid="stVerticalBlock"] {
                gap: .6rem;
            }

            .st-key-admin_score_editor div[data-testid="stTextInput"] label,
            .st-key-admin_score_editor div[data-testid="stNumberInput"] label {
                height: 0;
                margin: 0;
                min-height: 0;
                overflow: hidden;
                visibility: hidden;
            }

            .st-key-admin_score_editor [data-baseweb="input"],
            .st-key-admin_score_editor [data-baseweb="input"] > div {
                background: transparent !important;
                border: 0 !important;
                box-shadow: none !important;
            }

            .st-key-admin_score_editor div[data-testid="stTextInput"] input {
                -webkit-text-fill-color: #e4f6df;
                background: transparent !important;
                border: 0 !important;
                box-shadow: none !important;
                color: #e4f6df !important;
                font-family: 'Bangers', Impact, sans-serif;
                font-size: 1.2rem;
                font-weight: 700;
                letter-spacing: .055em;
                min-height: auto;
                padding: 0;
                text-align: center;
                text-transform: uppercase;
            }

            .st-key-admin_score_editor div[data-testid="stNumberInput"] {
                margin-top: .25rem;
            }

            .st-key-admin_score_editor div[data-testid="stNumberInput"] input {
                -webkit-text-fill-color: #f8fafc;
                background: transparent !important;
                border: 0 !important;
                box-shadow: none !important;
                color: #f8fafc !important;
                font-family: 'Bangers', Impact, sans-serif;
                font-size: clamp(2.4rem, 5vw, 3.6rem);
                font-weight: 900;
                height: auto;
                letter-spacing: 0;
                line-height: .9;
                min-height: 3.25rem;
                padding: 0;
                text-align: center;
            }

            .st-key-admin_score_editor div[data-testid="stNumberInput"] button {
                -webkit-text-fill-color: #ffffff;
                background: rgba(255, 255, 255, .1) !important;
                border-color: rgba(255, 255, 255, .14) !important;
                color: #ffffff !important;
            }

            .match-metrics {
                display: grid;
                gap: .75rem;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                margin-top: .9rem;
                padding: 0;
            }

            .metric-card {
                background: var(--panel);
                border: 1px solid var(--line);
                border-left: 5px solid var(--green);
                border-radius: 8px;
                min-height: 98px;
                padding: 1rem;
            }

            .metric-card span,
            .rank-person span {
                color: var(--muted);
                display: block;
                font-size: .8rem;
                font-weight: 700;
                letter-spacing: .06em;
            }

            .metric-card strong {
                color: var(--ink);
                display: block;
                font-size: clamp(1.85rem, 4vw, 2.35rem);
                line-height: 1.1;
                margin-top: .25rem;
                overflow-wrap: anywhere;
            }

            .metric-card {
                background: linear-gradient(180deg, #0d331f, #071c11);
                border-left-color: var(--amber);
            }

            .metric-prize {
                background: linear-gradient(180deg, #47380a, #171407);
                border-left-color: var(--amber);
            }

            .result-panel {
                border: 1px solid var(--line);
                border-left: 5px solid var(--amber);
                border-radius: 8px;
                margin-top: .9rem;
                padding: 1rem;
            }

            .result-panel span {
                color: var(--muted);
                display: block;
                font-size: .8rem;
                font-weight: 800;
                letter-spacing: .06em;
                text-transform: uppercase;
            }

            .result-panel strong {
                color: var(--ink);
                display: block;
                font-size: 1.45rem;
                margin-top: .2rem;
            }

            .result-panel p {
                color: #dce9df;
                font-weight: 700;
                margin: .35rem 0 0;
            }

            .result-panel em {
                color: #fff1c7;
                display: block;
                font-style: normal;
                font-weight: 900;
                margin-top: .45rem;
            }

            .result-winners {
                background: linear-gradient(180deg, #0d3d25, #071c11);
                border-left-color: var(--amber);
            }

            .result-empty {
                background: linear-gradient(180deg, #351919, #171012);
                border-left-color: var(--red);
            }

            .leaderboard {
                background: var(--panel);
                border: 1px solid #1a5131;
                box-shadow: 0 18px 36px rgba(0, 0, 0, .34);
                display: flex;
                flex-direction: column;
                gap: .55rem;
                padding: .75rem;
            }

            .rank-row {
                align-items: center;
                border: 1px solid transparent;
                border-radius: 8px;
                display: grid;
                gap: .55rem .75rem;
                grid-template-columns: minmax(0, 1fr);
                grid-template-rows: auto auto;
                min-height: 86px;
                padding: .8rem;
            }

            .rank-exact {
                background: linear-gradient(180deg, #1b7d45, #12502d);
                border-color: #37c875;
            }

            .rank-alive {
                background: linear-gradient(180deg, #103d27, #0a2819);
                border-color: #288d55;
            }

            .rank-out {
                background: linear-gradient(180deg, #391718, #251013);
                border-color: #94413c;
            }

            .rank-person {
                align-self: center;
                min-width: 0;
            }

            .rank-person strong {
                color: var(--ink);
                display: block;
                font-size: .98rem;
                letter-spacing: .045em;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .rank-guess {
                align-items: center;
                background: rgba(255, 255, 255, .10);
                border: 1px solid rgba(255, 255, 255, .12);
                border-radius: 999px;
                color: #ffffff;
                display: grid;
                font-size: .92rem;
                font-weight: 900;
                grid-column: 1 / 2;
                grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
                letter-spacing: .06em;
                min-height: 2rem;
                padding: .25rem .75rem;
            }

            .rank-guess strong {
                color: #ffffff;
                display: block;
                font-size: .95rem;
                padding: 0 .65rem;
                text-align: center;
                white-space: nowrap;
            }

            .rank-team {
                color: #fff8ed;
                display: block;
                font-size: .72rem;
                letter-spacing: .045em;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                text-transform: uppercase;
                white-space: nowrap;
            }

            .rank-home {
                text-align: left;
            }

            .rank-away {
                text-align: right;
            }

            div[data-testid="stForm"] {
                background: var(--panel);
                border: 1px solid var(--line);
                box-shadow: 0 18px 36px rgba(0, 0, 0, .28);
                padding: 1rem;
            }

            div[data-testid="stTextInput"] label,
            div[data-testid="stNumberInput"] label {
                color: var(--ink);
                font-weight: 800;
            }

            div[data-testid="stTextInput"] input,
            div[data-testid="stNumberInput"] input {
                -webkit-text-fill-color: var(--ink);
                background: var(--field) !important;
                border: 1px solid #4a3436;
                border-radius: 8px;
                color: var(--ink) !important;
                font-size: 1.05rem;
                font-weight: 700;
            }

            div[data-testid="stTextInput"] [data-baseweb="input"],
            div[data-testid="stNumberInput"] [data-baseweb="input"],
            div[data-testid="stTextInput"] [data-baseweb="input"] > div,
            div[data-testid="stNumberInput"] [data-baseweb="input"] > div {
                background: var(--field) !important;
                border-color: #4a3436 !important;
                color: var(--ink) !important;
            }

            .st-key-admin_score_editor [data-baseweb="input"],
            .st-key-admin_score_editor [data-baseweb="input"] > div,
            .st-key-admin_score_editor [data-baseweb="base-input"],
            .st-key-admin_score_editor [data-baseweb="base-input"] > div,
            .st-key-admin_score_editor div[data-testid="stTextInput"] > div,
            .st-key-admin_score_editor div[data-testid="stTextInput"] > div > div,
            .st-key-admin_score_editor div[data-testid="stNumberInput"] > div,
            .st-key-admin_score_editor div[data-testid="stNumberInput"] > div > div {
                background: rgba(2, 18, 11, .76) !important;
                background-color: rgba(2, 18, 11, .76) !important;
                border: 1px solid rgba(255, 255, 255, .12) !important;
                border-radius: 8px !important;
                box-shadow: none !important;
                color: #f8fafc !important;
            }

            .st-key-admin_score_editor input {
                -webkit-appearance: none !important;
                -webkit-text-fill-color: #f8fafc !important;
                appearance: none !important;
                background: rgba(2, 18, 11, .76) !important;
                border: 0 !important;
                border-radius: 8px !important;
                box-shadow: none !important;
                caret-color: var(--amber);
                color: #f8fafc !important;
                color-scheme: dark;
            }

            .st-key-admin_score_editor div[data-testid="stTextInput"] input,
            .st-key-admin_score_editor div[data-testid="stNumberInput"] input {
                -webkit-text-fill-color: #f8fafc !important;
                background-color: rgba(2, 18, 11, .76) !important;
                color: #f8fafc !important;
                opacity: 1 !important;
            }

            .st-key-admin_score_editor div[data-testid="stNumberInput"] button,
            .st-key-admin_score_editor div[data-testid="stNumberInput"] button:hover,
            .st-key-admin_score_editor div[data-testid="stNumberInput"] button:focus {
                -webkit-text-fill-color: #ffffff !important;
                background: #123d26 !important;
                border-color: #346c4b !important;
                color: #ffffff !important;
                opacity: 1 !important;
            }

            .st-key-admin_score_editor div[data-testid="stNumberInput"] button svg {
                fill: #ffffff !important;
                color: #ffffff !important;
                stroke: #ffffff !important;
            }

            div[data-testid="stTextInput"] input::placeholder,
            div[data-testid="stNumberInput"] input::placeholder {
                color: #7f8e86;
                opacity: 1;
            }

            div[data-testid="stTextInput"] input:focus,
            div[data-testid="stNumberInput"] input:focus {
                border-color: var(--green);
                box-shadow: 0 0 0 1px var(--green);
            }

            div[data-testid="stNumberInput"] button {
                -webkit-text-fill-color: #f1dfcc;
                background: #261719 !important;
                border-color: #4a3436 !important;
                color: #f1dfcc !important;
            }

            div[data-testid="stNumberInput"] button:hover,
            div[data-testid="stNumberInput"] button:focus {
                -webkit-text-fill-color: #ffffff;
                background: #0c351f !important;
                border-color: var(--green) !important;
                color: #ffffff !important;
            }

            .admin-panel-title {
                color: var(--ink);
                font-size: 1rem;
                font-weight: 800;
                margin: 0 0 .65rem;
            }

            .stButton > button,
            .stFormSubmitButton > button {
                border-radius: 8px;
                -webkit-text-fill-color: #171006;
                background: linear-gradient(180deg, #ffd21f, #d9a90f) !important;
                border-color: var(--amber) !important;
                color: #171006 !important;
                font-size: 1.05rem;
                font-weight: 800;
            }

            .stButton > button *,
            .stFormSubmitButton > button * {
                -webkit-text-fill-color: #171006;
                color: #171006 !important;
            }

            .stButton > button:hover,
            .stFormSubmitButton > button:hover,
            .stFormSubmitButton > button[kind="primary"] {
                -webkit-text-fill-color: #171006;
                background: linear-gradient(180deg, #ffe36a, #e6b717) !important;
                border-color: #ffe36a !important;
                color: #171006 !important;
            }

            .stButton > button:focus,
            .stButton > button:active,
            .stFormSubmitButton > button:focus,
            .stFormSubmitButton > button:active {
                -webkit-text-fill-color: #171006;
                color: #171006 !important;
            }

            div[data-testid="stCheckbox"] label,
            div[data-testid="stCheckbox"] label p,
            div[data-testid="stCheckbox"] label span {
                color: var(--ink) !important;
                opacity: 1 !important;
            }

            div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > div {
                background-color: var(--field) !important;
                border-color: #6b8171 !important;
                color: #171006 !important;
            }

            div[data-testid="stCheckbox"] input:checked + div,
            div[data-testid="stCheckbox"] [aria-checked="true"] > div {
                background-color: var(--amber) !important;
                border-color: var(--amber) !important;
            }

            .stButton > button:disabled,
            .stFormSubmitButton > button:disabled {
                -webkit-text-fill-color: #d9dfd9 !important;
                background: #26382d !important;
                border-color: #536b5a !important;
                color: #d9dfd9 !important;
                opacity: 1 !important;
            }

            .stButton > button:disabled *,
            .stFormSubmitButton > button:disabled * {
                -webkit-text-fill-color: #d9dfd9 !important;
                color: #d9dfd9 !important;
            }

            div[data-testid="stDataFrame"] {
                border: 1px solid var(--line);
                overflow: hidden;
            }

            .stAlert {
                background: var(--panel-2);
                color: var(--ink);
            }

            .history-card,
            .history-card * {
                font-family: Arial, Helvetica, sans-serif;
                letter-spacing: 0;
            }

            .history-card {
                background: var(--panel);
                border: 1px solid #1a5131;
                border-radius: 8px;
                box-shadow: 0 18px 36px rgba(0, 0, 0, .28);
                margin-bottom: .9rem;
                overflow: hidden;
            }

            div[data-testid="stExpander"] {
                background: var(--panel);
                border: 1px solid #1a5131;
                border-radius: 8px;
                box-shadow: 0 12px 28px rgba(0, 0, 0, .22);
                margin-bottom: .75rem;
                overflow: hidden;
            }

            div[data-testid="stExpander"],
            div[data-testid="stExpander"] * {
                font-family: Arial, Helvetica, sans-serif !important;
                letter-spacing: 0 !important;
                text-shadow: none !important;
            }

            div[data-testid="stExpander"] details {
                border: 0;
            }

            div[data-testid="stExpander"] summary {
                color: var(--ink);
                font-family: Arial, Helvetica, sans-serif;
                font-size: .96rem;
                font-weight: 800;
                letter-spacing: 0;
                line-height: 1.35;
                min-height: auto;
                padding: .9rem 3rem .9rem 1rem;
                white-space: normal;
            }

            div[data-testid="stExpander"] summary * {
                color: var(--ink) !important;
                font-family: Arial, Helvetica, sans-serif !important;
                letter-spacing: 0 !important;
                line-height: 1.35 !important;
                overflow-wrap: anywhere;
                white-space: normal !important;
                word-break: normal;
            }

            div[data-testid="stExpander"] summary p {
                color: var(--ink) !important;
                font-family: Arial, Helvetica, sans-serif !important;
                line-height: 1.3;
                margin: 0;
                overflow-wrap: anywhere;
                white-space: normal;
                word-break: normal;
            }

            .history-date-chip {
                align-items: center;
                background: rgba(5, 34, 18, .72);
                border: 1px solid #1a5131;
                border-radius: 8px;
                color: var(--ink);
                display: flex;
                font-family: Arial, Helvetica, sans-serif;
                font-size: .88rem;
                font-weight: 800;
                justify-content: center;
                line-height: 1.25;
                margin-bottom: .75rem;
                min-height: 3.45rem;
                padding: .75rem .85rem;
                text-align: center;
                white-space: normal;
                word-break: normal;
            }

            .history-card-open {
                border: 0;
                box-shadow: none;
                margin-bottom: 0;
            }

            .history-card-header {
                align-items: flex-start;
                border-bottom: 1px solid var(--line);
                display: flex;
                gap: .75rem;
                justify-content: space-between;
                padding: .9rem 1rem;
            }

            .history-card-header strong {
                color: var(--ink);
                font-size: 1rem;
                line-height: 1.25;
            }

            .history-card-header span {
                color: var(--muted);
                flex: 0 0 auto;
                font-size: .86rem;
                line-height: 1.25;
            }

            .history-card-grid {
                display: grid;
                gap: .65rem;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                padding: .9rem 1rem 0;
            }

            .history-card-grid div {
                background: rgba(255, 210, 31, .07);
                border: 1px solid rgba(255, 210, 31, .16);
                border-radius: 8px;
                padding: .75rem;
            }

            .history-card-grid span {
                color: var(--muted);
                display: block;
                font-size: .78rem;
                font-weight: 700;
                margin-bottom: .25rem;
            }

            .history-card-grid strong {
                color: var(--ink);
                font-size: 1.05rem;
            }

            .history-card-summary {
                color: var(--ink);
                padding: .8rem 1rem 0;
            }

            .history-card-summary p {
                color: var(--ink);
                margin: .25rem 0;
            }

            .history-table {
                padding: .85rem 1rem 1rem;
            }

            .history-table table {
                border-collapse: collapse;
                color: var(--ink);
                width: 100%;
            }

            .history-table th,
            .history-table td {
                border-bottom: 1px solid var(--line);
                font-size: .9rem;
                padding: .55rem .45rem;
                text-align: left;
            }

            .history-table th {
                color: var(--muted);
                font-weight: 800;
            }

            @media (max-width: 720px) {
                .block-container {
                    padding: .75rem .75rem 2rem;
                }

                .brand-hero {
                    gap: .7rem;
                    grid-template-columns: 3.1rem minmax(0, 1fr);
                    margin-bottom: .75rem;
                    padding: .75rem;
                }

                .brand-logo-slot {
                    font-size: 1rem;
                    height: 3.1rem;
                    width: 3.1rem;
                }

                .brand-kicker {
                    font-size: .62rem;
                    line-height: 1.25;
                }

                .brand-title {
                    font-size: 1.45rem;
                    line-height: 1.05;
                }

                .stTabs [data-baseweb="tab-list"] {
                    flex-wrap: nowrap;
                    gap: .25rem;
                    overflow-x: auto;
                    padding-bottom: .25rem;
                }

                .stTabs [data-baseweb="tab"] {
                    flex: 0 0 auto;
                    height: 2.5rem;
                    padding: 0 .75rem;
                    white-space: nowrap;
                }

                .stTabs [data-baseweb="tab"],
                .stTabs [data-baseweb="tab"] *,
                .stTabs [data-baseweb="tab"] p {
                    color: #ffffff !important;
                    opacity: 1 !important;
                    text-shadow: 0 1px 2px rgba(0, 0, 0, .65);
                }

                div[data-testid="stRadio"] div[role="radiogroup"] {
                    flex-wrap: nowrap;
                    gap: .25rem;
                    overflow-x: auto;
                    padding-bottom: .25rem;
                }

                div[data-testid="stRadio"] label {
                    flex: 0 0 auto;
                    min-height: 2.5rem;
                    padding: 0 .75rem;
                    white-space: nowrap;
                }

                .section-title {
                    font-size: 1rem;
                    margin-top: .75rem;
                }

                .score-meta {
                    align-items: flex-start;
                    flex-direction: column;
                    gap: .45rem;
                    padding: .75rem .9rem;
                }

                .scoreboard {
                    gap: .5rem;
                    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
                    min-height: 150px;
                    padding: .9rem;
                }

                .team span {
                    font-size: .92rem;
                }

                .team strong {
                    font-size: 4rem;
                }

                .separator {
                    font-size: 1.35rem;
                    line-height: 1;
                }

                .admin-score-separator {
                    font-size: 1.35rem;
                    line-height: 1;
                    min-height: 5rem;
                }

                .st-key-admin_score_editor {
                    min-height: 150px;
                    padding: .9rem;
                }

                .st-key-admin_score_editor div[data-testid="stTextInput"] input {
                    font-size: .92rem;
                }

                .st-key-admin_score_editor div[data-testid="stNumberInput"] input {
                    font-size: 2.8rem;
                    min-height: 3.1rem;
                }

                .match-metrics {
                    grid-template-columns: 1fr;
                }

                .metric-card {
                    min-height: auto;
                    padding: .85rem;
                }

                .metric-card strong {
                    font-size: 1.85rem;
                }

                .leaderboard {
                    gap: .45rem;
                    padding: .6rem;
                }

                .rank-row {
                    grid-template-columns: minmax(0, 1fr);
                    min-height: auto;
                    padding: .7rem;
                }

                .rank-guess {
                    grid-column: 1 / 2;
                    min-height: 1.85rem;
                    padding: .25rem .55rem;
                }

                .rank-guess strong {
                    font-size: .88rem;
                    padding: 0 .45rem;
                }

                .rank-team {
                    font-size: .64rem;
                }

                div[data-testid="stForm"] {
                    padding: .85rem;
                }

                .stButton > button,
                .stFormSubmitButton > button {
                    min-height: 2.75rem;
                    width: 100%;
                }

                .history-card-header {
                    flex-direction: column;
                    gap: .25rem;
                }

                .history-card-grid {
                    grid-template-columns: 1fr;
                }

                .history-table {
                    overflow-x: auto;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Bolao Adega Camisa 10",
        page_icon="BA",
        layout="wide",
    )
    apply_styles()

    state = load_state()

    st.markdown(
        (
            '<header class="brand-hero">'
            f"{logo_markup()}"
            '<div class="brand-copy">'
            '<span class="brand-kicker">cerveja, futebol e resenha</span>'
            '<span class="brand-title">Bolão Adega Camisa 10</span>'
            "</div>"
            "</header>"
        ),
        unsafe_allow_html=True,
    )

    is_admin = st.session_state.get("admin_authenticated", False)

    if is_admin:
        admin_area(state)
    else:
        public_sections = ["Painel do Bolão", "Login admin"]
        section = st.radio(
            "Navegacao",
            public_sections,
            horizontal=True,
            key="public_section",
            label_visibility="collapsed",
        )

        if section == "Painel do Bolão":
            enable_public_auto_refresh()
            main_panel(state)
        elif section == "Login admin":
            admin_login_panel()


if __name__ == "__main__":
    main()
