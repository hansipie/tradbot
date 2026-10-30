# tradbot

Bot de surveillance de swaps crypto. Il lit les swaps suivis dans CryptoUpdate et envoie une alerte Telegram quand le swap retour rendrait assez d'unités en plus (seuil configurable, frais déduits).

## Fonctionnement

```
CryptoUpdate ──POST /swaps (HTTPS + Bearer)──▶ bot ──▶ PostgreSQL ──▶ Telegram
               (secours manuel : scripts/sync_swaps.py)
```

- Un swap A→B est **ouvert** tant que le B reçu n'a pas été dépensé (consommation FIFO par wallet, dépenses partielles gérées).
- Gain = `B restant × taux B→A × (1 − frais) ÷ A donné − 1`, avec le taux ccxt (paire directe, inverse ou via USDT).
- Une alerte par swap au franchissement du seuil, réarmée quand le gain repasse 0,5 point sous le seuil.
- `GET /status` (port 8080) liste les swaps ouverts et leur gain ; il exige le même Bearer que `POST /swaps` dès que `SWAPS_API_TOKEN` est défini.
- Commandes Telegram (chat configuré uniquement) : `/status`, `/swaps`, `/clear_swaps`, `/help`. `/clear_swaps` vide la copie PostgreSQL des swaps et demande une confirmation (`/clear_swaps confirm`) ; les swaps reviennent à la prochaine synchronisation de CryptoUpdate.
- Chaque synchronisation reçue déclenche un message Telegram : détail des swaps reçus et des swaps supprimés de la copie (10 listés au maximum, puis « … et N autre(s) »).
- Arrêt propre : `SIGTERM`/`SIGINT`, ou création du fichier `/tmp/tradbot.stop`.

## Configuration

```bash
cp .env.example .env
```

| Variable | Défaut | Rôle |
|---|---|---|
| `CRYPTOUPDATE_DB` | `../CryptoUpdate/data/db.sqlite3` | base source des swaps |
| `SWAP_MIN_GAIN_PCT` | 2 | seuil d'alerte (%) |
| `SWAP_FEE_PCT` | 0.5 | frais estimés du swap retour (%) |
| `SWAP_CHECK_INTERVAL_MIN` | 15 | intervalle de vérification |
| `SWAPS_API_TOKEN` | vide | secret Bearer de `POST /swaps` (vide = endpoint désactivé) |
| `POSTGRES_URL` | localhost | base PostgreSQL |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | vides | alertes (désactivées si vides) |
| `NOTIFY_LIFECYCLE` | false | message Telegram à chaque démarrage/arrêt |
| `MONITOR_PORT` | 8080 | port de l'endpoint (hors container ; le compose force 8080 en interne) |

## Recevoir les swaps de CryptoUpdate

1. Génère un secret : `openssl rand -hex 32`, puis renseigne-le comme `SWAPS_API_TOKEN` dans Coolify.
2. Dans Coolify, attribue un domaine au service `bot` (port 8080) : Traefik fournit le HTTPS. Le compose n'expose pas de port sur l'hôte ; pour accéder à `/status` en local, ajoute `ports: ["8080:8080"]` dans un `docker-compose.override.yml`.
3. Dans le `settings.json` de CryptoUpdate (ou via `TRADBOT_URL` / `TRADBOT_TOKEN`) :

```json
"Tradbot": { "url": "https://tradbot.exemple.fr", "token": "<le même secret>" }
```

CryptoUpdate envoie alors la liste complète des swaps (8 champs, sans notes ni avoirs) après chaque ajout, modification ou suppression ; un swap absent de la liste est supprimé de la copie du bot. Une liste vide est refusée (422) pour éviter d'effacer toute la table : pour tout supprimer, utilise `/clear_swaps`. L'envoi est en arrière-plan : une panne du bot n'empêche jamais d'enregistrer un swap.

## Utilisation

```bash
podman compose up -d postgres
uv run python scripts/sync_swaps.py   # à relancer après chaque nouveau swap (ou via cron)
uv run python main.py
```

Ou tout en container : `podman compose up -d --build`.

## Tests

```bash
uv run pytest tests/ -v
```
