# tradbot

Bot de trading modulaire en Python, orienté crypto via [ccxt](https://github.com/ccxt/ccxt). Architecture event-driven avec séparation stricte entre le code live et le moteur de backtest.

> N.B.: Ce code est une mise en pratique de mon article: https://blog.ansicode.fr/posts/2026-05-13-la-theorie-derriere-les-bots-de-trading/

## Prérequis

- [Podman](https://podman.io/) + `podman compose`

Pour le développement local uniquement :

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Démarrage rapide (container)

```bash
cp .env.example .env   # renseigner les clés API et tokens
podman compose up -d --build
```

Le bot démarre automatiquement après que Redis et PostgreSQL soient prêts.

```bash
# Logs en temps réel
podman compose logs -f bot

# Arrêt propre
podman compose down
```

## Configuration (.env)

```bash
EXCHANGE_API_KEY=       # clé API de l'exchange
EXCHANGE_API_SECRET=    # secret API de l'exchange
SYMBOLS=BTC/USDC,ETH/USDC,SOL/USDC,BNB/USDC   # paires surveillées

REDIS_URL=redis://localhost:6379
POSTGRES_URL=postgresql://tradbot:tradbot@localhost:5432/tradbot

TELEGRAM_TOKEN=         # token du bot Telegram (via @BotFather)
TELEGRAM_CHAT_ID=       # ton chat ID Telegram
MONITOR_PORT=8080       # port du endpoint HTTP /status
```

`REDIS_URL` et `POSTGRES_URL` sont automatiquement surchargées par le compose pour pointer vers les services internes. Si `TELEGRAM_TOKEN` est vide, les alertes sont désactivées silencieusement.

## Utilisation

### Télécharger les données historiques

```bash
# Via container
podman compose run --rm bot uv run python scripts/download_data.py

# En local
uv run python scripts/download_data.py
```

Récupère l'historique journalier de chaque paire configurée dans `SYMBOLS` depuis 2018 et le sauvegarde dans `data/historical/`.

### Lancer un backtest

```bash
uv run python scripts/run_backtest.py           # métriques globales + détail des trades
uv run python scripts/run_backtest.py --yearly  # tableau année par année
uv run python scripts/run_backtest.py --all     # les deux
```

Le backtest génère automatiquement les graphiques dans `data/historical/`.

### Lancer le bot (paper trading)

```bash
# Via compose (recommandé)
podman compose up -d --build

# En local
uv run python main.py
```

Le bot tourne en mode sandbox par défaut (`ExchangeConfig.sandbox = True`). Aucun ordre réel n'est envoyé tant que `PaperBroker` est utilisé dans `main.py`.

La boucle se synchronise automatiquement sur les bougies de l'exchange (ex : toutes les 24h pour `1d`). Ctrl+C ou SIGTERM déclenchent un arrêt propre dans la seconde.

**Arrêt via fichier sentinel** (pratique pour un arrêt à distance sans tuer le process) :

```bash
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
  "symbol": "BTC/USDC",
  "capital": 9850.0,
  "position": 0.003,
  "portfolio_value": 10045.0,
  "peak_capital": 10200.0,
  "drawdown": -0.034,
  "last_signal": "HOLD",
  "last_price": 81500.0,
  "last_tick": "2026-05-15T08:00:00Z"
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
| `scripts/` | Outils CLI : téléchargement de données, backtest, visualisation |

## Stratégies disponibles

| Classe | Description |
|---|---|
| `DualMACrossover(fast, slow)` | Achat quand MM(fast) > MM(slow), vente sinon. Défaut : 50/200. |
| `RSIMeanReversion(period, oversold, overbought)` | Mean reversion sur RSI avec filtre de tendance. |

### Résultats backtest — DualMA 50/200 (2018–2026, frais 0,1 %, slippage 0,1 %)

| Paire | Capital final | CAGR | Drawdown max | Sharpe | Calmar |
|---|---|---|---|---|---|
| BNB/USDC | 106 531 $ | +37,6 % | -73,9 % | 0,68 | 0,51 |
| BTC/USDC | 25 705 $ | +13,6 % | -62,2 % | 0,44 | 0,22 |
| ETH/USDC | 24 570 $ | +12,9 % | -78,4 % | 0,44 | 0,16 |
| SOL/USDC | 7 956 $ | -4,8 % | -63,7 % | 0,13 | -0,08 |

*SOL/USDC : historique depuis septembre 2021 uniquement.*

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
        return SignalEvent(Signal.BUY, symbol="BTC/USDC", price=df["close"].iloc[-1])
```

La même instance tourne sans modification dans `run_backtest()` et dans `main.py`.
