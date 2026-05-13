# tradbot

Bot de trading modulaire en Python, orienté crypto via [ccxt](https://github.com/ccxt/ccxt). Architecture event-driven avec séparation stricte entre le code live et le moteur de backtest.

## Prérequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
uv sync
uv pip install -e .
cp .env.example .env   # renseigner les clés API si nécessaire
```

## Utilisation

### Télécharger les données historiques

```bash
uv run python scripts/download_data.py
```

Récupère l'historique journalier BTC/USDT depuis Binance (2018 → aujourd'hui) et le sauvegarde dans `data/historical/BTC_USDT_1d.parquet`.

### Lancer un backtest

```bash
uv run python scripts/run_backtest.py
```

### Lancer le bot (paper trading)

```bash
uv run python main.py
```

Le bot tourne en mode sandbox par défaut (`ExchangeConfig.sandbox = True`). Aucun ordre réel n'est envoyé tant que `PaperBroker` est utilisé dans `main.py`.

### Tests

```bash
uv run pytest tests/ -v
uv run pytest tests/test_strategy.py::test_buy_signal_when_fast_above_slow -v
```

## Architecture

```
Données → Strategy.on_data() → RiskManager.validate() → ExecutionEngine.execute()
```

| Répertoire | Rôle |
|---|---|
| `tradbot/data/` | Récupération OHLCV via ccxt (`CcxtFeed`) |
| `tradbot/strategy/` | Signaux de trading (`Signal`, `SignalEvent`, `Strategy`) |
| `tradbot/risk/` | Validation des ordres — drawdown, sizing, limite trades/h |
| `tradbot/execution/` | Envoi des ordres (`PaperBroker` ou broker réel) |
| `tradbot/monitoring/` | Logs JSON structurés via structlog |
| `backtest/` | Moteur de backtest indépendant — même code de stratégie qu'en live |

## Stratégies disponibles

| Classe | Description |
|---|---|
| `DualMACrossover(fast, slow)` | Achat quand MM(fast) > MM(slow), vente sinon. Défaut : 50/200. |

### Résultats backtest — DualMA 50/200 sur BTC/USDT 1j (2018–2026)

| Métrique | Valeur |
|---|---|
| Capital final (depuis 10 000 $) | 77 770 $ |
| CAGR | 27.8%/an |
| Drawdown max | -63.7% |
| Sharpe ratio | 0.63 |
| Nombre de trades | 16 |

## Ajouter une stratégie

Implémenter le Protocol `Strategy` dans `tradbot/strategy/` :

```python
class MaStrategie:
    def on_data(self, df: pd.DataFrame) -> SignalEvent:
        # df : OHLCV indexé par pd.Timestamp UTC
        # Toujours utiliser .shift(1) sur les indicateurs pour éviter le look-ahead bias
        ...
        return SignalEvent(Signal.BUY, symbol="BTC/USDT", price=df["close"].iloc[-1])
```

La même instance tourne sans modification dans `run_backtest()` et dans `main.py`.
