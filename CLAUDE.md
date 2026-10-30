# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commandes essentielles

```bash
uv run pytest tests/ -v                 # tests
uv run python scripts/sync_swaps.py     # copie les swaps de CryptoUpdate vers PostgreSQL
uv run python main.py                   # bot de surveillance des swaps
uv run python scripts/backtest_swaps.py [--sqlite ../CryptoUpdate/data/db.sqlite3] [--min-gain 1 2 5] [--rules threshold cross_and trail cross] [--ma 10/30] [--details]
uv add <package>
```

## Architecture

Le bot surveille les swaps suivis dans `../CryptoUpdate` et alerte par Telegram quand un swap retour est rentable :

```
CryptoUpdate SQLite → sync_swaps.py → PostgreSQL (swaps) → open_positions() → evaluate() → Alerter
```

- `config.py` — dataclasses (`Config`, `ExchangeConfig`, `MonitorConfig`, `SwapConfig`), lues depuis `.env`.
- `swaps/evaluator.py` — logique pure : `open_positions` (lots FIFO par wallet/token), `evaluate` (gain en unités après frais), `current_rate`.
- `swaps/backtest.py` — logique pure : `run_backtest` rejoue les swaps sur des prix historiques avec `open_positions`/`evaluate` et la même logique d'alerte/ré-armement que `main._check_swaps` ; règles de sortie `ExitRule` (seuil seul ou couplé à un croisement de moyennes mobiles) ; métriques : alertes, délai avant 1re alerte, gain en unités à la 1re alerte, comparaison au swap retour réel.
- `data/feed.py` — `CcxtFeed` résout n'importe quelle paire (directe, inverse, via USDT) ; `fetch_history` pagine un historique complet.
- `data/history.py` — `HistoryCache` : cache CSV des OHLCV dans `data/ohlcv/<exchange>/` (gitignoré), seules les bougies terminées sont gardées.
- `storage/` — `SwapStore` (copie PostgreSQL des swaps), `schema.py` : `PgStore` (init du schéma).
- `monitoring/` — `Alerter` (Telegram), `commands.py` (commandes Telegram /status /swaps /clear_swaps /help), endpoint `/status`, logs structlog.

## Règles importantes

- Le gain est mesuré en **unités du token d'origine**, pas en valeur fiat.
- La base CryptoUpdate est ouverte en lecture seule : ne jamais y écrire.
- Garder `evaluator.py` pur (sans réseau ni base) pour rester testable.
