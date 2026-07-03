# Bolao Adega

Sistema simples em Python e Streamlit para controlar um bolao de futebol.

## Como rodar

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## Persistencia em nuvem

Localmente o app usa `data/bolao.json`. Em deploy, configure Supabase nos secrets:

```toml
SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
SUPABASE_KEY = "SUA_SB_SECRET_KEY_OU_LEGACY_SERVICE_ROLE_KEY"
BOLAO_ADMIN_PASSWORD = "sua-senha"
```

Use a chave `sb_secret_...` da area de API Keys nova do Supabase, ou a chave
`service_role` da area legacy. Nao use a `publishable key`, pois ela nao deve
ter permissao de escrita para salvar o bolao.

Crie esta tabela no Supabase:

```sql
create table if not exists bolao_state (
  id text primary key,
  state jsonb not null,
  updated_at timestamptz default now()
);
```

Crie tambem as tabelas separadas para o historico dos boloes:

```sql
create table if not exists bolao_pools (
  id text primary key,
  home_team text not null,
  away_team text not null,
  home_score integer not null,
  away_score integer not null,
  entry_fee numeric not null default 0,
  prize_pool numeric not null default 0,
  prize_per_winner numeric not null default 0,
  winners jsonb not null default '[]'::jsonb,
  finished_at text not null,
  created_at timestamptz default now()
);

create table if not exists bolao_pool_participants (
  id text primary key,
  pool_id text not null references bolao_pools(id) on delete cascade,
  name text not null,
  guess_home_score integer not null,
  guess_away_score integer not null,
  is_winner boolean not null default false,
  created_at timestamptz default now()
);
```

O app salva o jogo atual em `bolao_state`, registro `default`. Cada bolao
finalizado vira uma linha em `bolao_pools`, e os participantes daquele bolao
ficam em `bolao_pool_participants`.

## O que ja existe

- Area principal com placar do jogo, ranking e palpites.
- Area do administrador em aba separada.
- Cadastro manual dos times, placar, status e participantes.
- Pontuacao automatica com base no placar atual.
- Persistencia local em `data/bolao.json`.

## Regra de pontuacao inicial

- 5 pontos para placar exato.
- 3 pontos para acertar vencedor ou empate.
- 1 ponto extra por cada quantidade de gols acertada.
