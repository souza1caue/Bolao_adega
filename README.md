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
SUPABASE_KEY = "SUA_CHAVE_COM_PERMISSAO_DE_ESCRITA"
BOLAO_ADMIN_PASSWORD = "sua-senha"
```

Crie esta tabela no Supabase:

```sql
create table if not exists bolao_state (
  id text primary key,
  state jsonb not null,
  updated_at timestamptz default now()
);
```

O app salva todo o estado em `bolao_state`, registro `default`.

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
