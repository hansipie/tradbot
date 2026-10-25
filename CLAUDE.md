# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commandes essentielles

```bash
uv run pytest tests/ -v                 # tests
uv run python scripts/sync_swaps.py     # copie les swaps de CryptoUpdate vers PostgreSQL
uv run python main.py                   # bot de surveillance des swaps
uv add <package>
```

## Architecture

Le bot surveille les swaps suivis dans `../CryptoUpdate` et alerte par Telegram quand un swap retour est rentable :

```
CryptoUpdate SQLite → sync_swaps.py → PostgreSQL (swaps) → open_positions() → evaluate() → Alerter
```

- `config.py` — dataclasses (`Config`, `ExchangeConfig`, `MonitorConfig`, `SwapConfig`), lues depuis `.env`.
- `swaps/evaluator.py` — logique pure : `open_positions` (lots FIFO par wallet/token), `evaluate` (gain en unités après frais), `current_rate`.
- `data/feed.py` — `CcxtFeed` résout n'importe quelle paire (directe, inverse, via USDT).
- `storage/` — `SwapStore` (copie PostgreSQL des swaps), `PgStore` (init du schéma).
- `monitoring/` — `Alerter` (Telegram), endpoint `/status`, logs structlog.

## Règles importantes

- Le gain est mesuré en **unités du token d'origine**, pas en valeur fiat.
- La base CryptoUpdate est ouverte en lecture seule : ne jamais y écrire.
- Garder `evaluator.py` pur (sans réseau ni base) pour rester testable.
