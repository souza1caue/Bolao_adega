# Bolao Adega

Sistema simples em Python e Streamlit para controlar um bolao de futebol.

## Como rodar

```powershell
pip install -r requirements.txt
streamlit run app.py
```

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
