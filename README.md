# tradbot

Bot de trading modulaire en Python, orienté crypto via [ccxt](https://github.com/ccxt/ccxt). Architecture event-driven avec séparation stricte entre le code live et le moteur de backtest.

## Prérequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Podman](https://podman.io/) (ou Docker) pour Redis et PostgreSQL

## Installation

```bash
uv sync
cp .env.example .env   # renseigner les clés API et tokens
```

Lancer Redis et PostgreSQL :

```bash
podman compose up -d
# ou : docker compose up -d
```

## Configuration (.env)

```bash
EXCHANGE_API_KEY=       # clé API de l'exchange
EXCHANGE_API_SECRET=    # secret API de l'exchange

REDIS_URL=redis://localhost:6379
POSTGRES_URL=postgresql://tradbot:tradbot@localhost:5432/tradbot

TELEGRAM_TOKEN=         # token du bot Telegram (via @BotFather)
TELEGRAM_CHAT_ID=       # ton chat ID Telegram
MONITOR_PORT=8080       # port du endpoint HTTP /status
```

Si `TELEGRAM_TOKEN` est vide, les alertes sont désactivées silencieusement.

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

La boucle se synchronise automatiquement sur les bougies de l'exchange (ex : toutes les 24h pour `1d`).

**Arrêter le bot** :

```bash
# Via signal (Ctrl+C ou SIGTERM)
kill <pid>

# Via fichier sentinel (pratique pour un arrêt à distance)
touch /tmp/tradbot.stop
```

### Monitoring

**Alertes Telegram** — le bot envoie une notification à chaque trade exécuté, drawdown max atteint, ou erreur réseau répétée.

**Endpoint HTTP** — état du portfolio en temps réel :

```bash
curl http://localhost:8080/status
```

```json
{
  "symbol": "BTC/USDT",
  "capital": 9850.0,
  "position": 0.003,
  "portfolio_value": 10045.0,
  "peak_capital": 10200.0,
  "drawdown": -0.034,
  "last_signal": "HOLD",
  "last_price": 65000.0,
  "last_tick": "2026-05-13T15:10:14Z"
}
```

### Tests

```bash
uv run pytest tests/ -v
uv run pytest tests/test_strategy.py::test_buy_signal_when_fast_above_slow -v
```

## Architecture

```
CcxtFeed → Strategy.on_data() → RiskManager.check_market()
                                          ↓
                              RiskManager.validate() → ExecutionEngine.execute()
                                                                ↓
                                                    PortfolioStore (Redis)
                                                    PgStore (PostgreSQL)
                                                    Alerter (Telegram)
                                                    Status (HTTP /status)
```

| Répertoire | Rôle |
|---|---|
| `tradbot/data/` | Récupération OHLCV via ccxt (`CcxtFeed`) |
| `tradbot/strategy/` | Signaux de trading (`Signal`, `SignalEvent`, `Strategy`) |
| `tradbot/risk/` | Validation des ordres — drawdown, exposition, volume, limite trades/h |
| `tradbot/execution/` | Envoi des ordres (`PaperBroker` ou broker réel) |
| `tradbot/storage/` | Persistance Redis (portfolio) et PostgreSQL (trades, equity) |
| `tradbot/monitoring/` | Logs JSON structurés, alertes Telegram, endpoint HTTP status |
| `backtest/` | Moteur de backtest indépendant — même code de stratégie qu'en live |

## Stratégies disponibles

| Classe | Description |
|---|---|
| `DualMACrossover(fast, slow)` | Achat quand MM(fast) > MM(slow), vente sinon. Défaut : 50/200. |
| `RSIMeanReversion(period, oversold, overbought)` | Mean reversion sur RSI avec filtre de tendance. |

### Résultats backtest — DualMA 50/200 sur BTC/USDT 1j (2018–2026)

| Métrique | Valeur |
|---|---|
| Capital final (depuis 10 000 $) | 77 770 $ |
| CAGR | 27.8 %/an |
| Drawdown max | -63.7 % |
| Sharpe ratio | 0.63 |
| Nombre de trades | 16 |

> Les backtests incluent frais (0.1 %) et slippage (0.1 %) par défaut. Pour des conditions plus prudentes : `run_backtest(df, strategy, fee_rate=0.002, slippage_pct=0.002)`.

## Risk Manager

Quatre checks appliqués à chaque signal avant exécution :

| Check | Paramètre | Défaut |
|---|---|---|
| Drawdown max | `max_drawdown_pct` | 10 % |
| Trades par heure | `max_trades_per_hour` | 10 |
| Exposition totale | `max_exposure_pct` | 95 % |
| Volume anormal | `min_volume_factor` | 10 % de la moyenne 20 bougies |

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
