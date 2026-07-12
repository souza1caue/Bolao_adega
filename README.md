# Bolao Adega Camisa 10

Sistema web para controle de bolao de futebol, desenvolvido com Python,
Streamlit e Supabase. O projeto foi criado para uma adega com tematica de
futebol, permitindo que usuarios acompanhem o placar, palpites, historico dos
ganhadores e premio acumulado, enquanto administradores controlam jogos,
participantes e encerramento das partidas.

Aplicacao publicada:

```text
https://bolao-adega-camisa10.streamlit.app
```

## Objetivo

O objetivo do projeto e simular um sistema real e simples de gestao de boloes
para uso em uma adega/bar. O administrador cadastra a partida, adiciona os
participantes e atualiza o placar manualmente. Os usuarios comuns acessam a
pagina publica para acompanhar os palpites, ver quem ainda tem chance e
consultar o historico dos boloes finalizados.

## Funcionalidades

- Area publica para acompanhamento do bolao.
- Placar principal com times e gols da partida.
- Ranking visual dos participantes e seus palpites.
- Indicacao de participantes com placar exato, ainda com chance ou sem chance.
- Calculo automatico do premio acumulado com base no valor por palpite.
- Historico de boloes finalizados, vencedores, participantes e valores pagos.
- Area administrativa protegida por senha.
- Cadastro manual de times, placar e participantes.
- Finalizacao de partida com dupla confirmacao.
- Inicio de novo bolao removendo participantes do jogo anterior.
- Exclusao de historicos especificos apenas na area administrativa.
- Persistencia em nuvem usando Supabase.
- Fallback para armazenamento local em ambiente de desenvolvimento.
- Layout responsivo para uso em computador e celular.

## Tecnologias

- Python
- Streamlit
- Pandas
- Supabase
- PostgreSQL
- HTML e CSS customizados dentro do Streamlit
- Streamlit Community Cloud

## Arquitetura

O projeto usa o Streamlit como interface web e o Supabase como banco de dados
em nuvem.

```text
Usuario/Admin
     |
     v
Streamlit App
     |
     v
Supabase / PostgreSQL
```

Responsabilidades principais:

```text
app.py                  Aplicacao Streamlit e regras do bolao
assets/                 Imagens e identidade visual
data/                   Arquivo local de fallback
docs/modelo-dados.md    Documentacao do modelo de dados
requirements.txt        Dependencias Python
```

## Modelo de dados

O banco no Supabase e composto por tres tabelas principais:

```text
bolao_state
```

Guarda o estado atual do sistema, como jogo em andamento, placar atual,
participantes cadastrados e configuracoes gerais.

```text
bolao_pools
```

Guarda cada bolao finalizado como um registro proprio.

```text
bolao_pool_participants
```

Guarda os participantes e palpites ligados a cada bolao finalizado.

Relacionamento principal:

```text
bolao_pools 1 ---- N bolao_pool_participants
```

A documentacao completa do MER esta em:

```text
docs/modelo-dados.md
```

## Configuracao local

1. Clone o repositorio.

```powershell
git clone https://github.com/souza1caue/Bolao_adega.git
cd Bolao_adega
```

2. Instale as dependencias.

```powershell
pip install -r requirements.txt
```

3. Rode a aplicacao.

```powershell
streamlit run app.py
```

Sem secrets configurados, o app usa o arquivo local `data/bolao.json` como
armazenamento de desenvolvimento.

## Configuracao do Supabase

No Streamlit Cloud ou no arquivo local `.streamlit/secrets.toml`, configure:

```toml
SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
SUPABASE_KEY = "SUA_SB_SECRET_KEY_OU_LEGACY_SERVICE_ROLE_KEY"
BOLAO_ADMIN_PASSWORD = "CAMISA10MJHS"
```

Use uma chave `sb_secret_...` da area de API Keys do Supabase ou a chave
`service_role` legacy. Nao use a `publishable key`, pois ela nao deve ter
permissao de escrita para salvar os dados do bolao.

## SQL das tabelas

Execute no SQL Editor do Supabase:

```sql
create table if not exists bolao_state (
  id text primary key,
  state jsonb not null,
  updated_at timestamptz default now()
);

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

## Regras do bolao

- O premio acumulado e calculado automaticamente:

```text
total de participantes x valor por palpite
```

- Ao finalizar a partida, vence quem acertar exatamente o placar final.
- Se houver mais de um vencedor, o premio e dividido igualmente.
- Se ninguem acertar o placar final, o sistema registra que nao houve vencedor.

## Acesso administrativo

Usuarios comuns visualizam apenas:

- Area principal
- Historico
- Login admin

Apos login, o administrador acessa:

- Controle da partida
- Participantes
- Historico com exclusao de registros
- Sair admin

A senha administrativa vem da variavel `BOLAO_ADMIN_PASSWORD`. Se ela nao
estiver configurada, o app usa a senha fixa padrao `CAMISA10MJHS`.

## Deploy

O deploy foi feito no Streamlit Community Cloud, conectado ao repositorio do
GitHub. As variaveis sensiveis ficam nos Secrets do Streamlit Cloud e nao sao
versionadas no repositorio.

Arquivos sensiveis ignorados:

```text
.streamlit/secrets.toml
data/*.json
```

## Aprendizados demonstrados

Este projeto demonstra:

- Desenvolvimento de aplicacao web com Streamlit.
- Separacao entre area publica e area administrativa.
- Controle de estado em aplicacoes interativas.
- Persistencia local e em nuvem.
- Integracao com Supabase via REST API.
- Modelagem simples de banco relacional.
- Deploy de aplicacao Python em ambiente publico.
- Customizacao visual e responsividade dentro do Streamlit.

## Proximas melhorias

- Atualizacao automatica da tela publica em tempo real.
- Cadastro de usuarios com autenticacao individual.
- Painel financeiro com controle de pagamentos.
- Melhor separacao do codigo em modulos.
- Testes automatizados para regras de vencedores e premio.
