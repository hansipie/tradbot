# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commandes essentielles

```bash
# Lancer les tests
uv run pytest tests/ -v

# Lancer un test unitaire précis
uv run pytest tests/test_strategy.py::test_buy_signal_when_fast_above_slow -v

# Lancer le bot (paper trading par défaut)
uv run python main.py

# Ajouter une dépendance
uv add <package>
```

## Architecture

Le pipeline de données suit un flux linéaire et unidirectionnel :

```
CcxtFeed → Strategy.on_data() → RiskManager.validate() → ExecutionEngine.execute()
```

**`tradbot/`** — code live (bot en temps réel)
- `config.py` — configuration centrale via dataclasses (`Config`, `ExchangeConfig`, `RiskConfig`). Lire l'environnement via `.env` (copier `.env.example`).
- `data/feed.py` — `CcxtFeed` implémente le Protocol `DataFeed`. Toujours retourner un `pd.DataFrame` indexé par `pd.Timestamp` UTC avec les colonnes `open/high/low/close/volume`.
- `strategy/base.py` — définit `Signal` (enum), `SignalEvent` (dataclass) et le Protocol `Strategy`. Toute nouvelle stratégie doit implémenter `on_data(df) -> SignalEvent`.
- `strategy/dual_ma.py` — stratégie de référence (Dual MA Crossover). Toujours utiliser `.shift(1)` sur les indicateurs pour éviter le look-ahead bias.
- `risk/manager.py` — s'intercale entre la stratégie et l'exécution. Peut downgrader n'importe quel signal en `HOLD`.
- `execution/engine.py` — `PaperBroker` pour le paper trading, à remplacer par un vrai broker ccxt en live.

**`backtest/engine.py`** — moteur de backtest indépendant. Prend n'importe quelle implémentation de `Strategy`, retourne un `BacktestResult` avec `.cagr`, `.max_drawdown`, `.sharpe`.

## Règles importantes

**Look-ahead bias** : dans `on_data()`, tous les indicateurs calculés sur `df["close"]` doivent être décalés d'une période via `.shift(1)` avant lecture du dernier indice. Sans ça, le backtest triche en utilisant le close courant pour décider du trade courant.

**Même code backtest / live** : `Strategy.on_data()` reçoit un `DataFrame` dans les deux cas — le moteur de backtest passe des fenêtres glissantes, le bot live passe le OHLCV récupéré en temps réel. Ne jamais mettre de logique dépendante du contexte (live vs backtest) dans une stratégie.

**Sandbox par défaut** : `ExchangeConfig.sandbox = True`. Ne passer en live qu'explicitement.
