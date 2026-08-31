# FilamentDB public ingestion API

The public API is intentionally isolated from the main Flask web service. The normal UI remains behind Pangolin; this service exposes only the ingestion API and health endpoint.

## Service

- Host: `127.0.0.1`
- Port: `5001`
- Public DNS: `filamentdb-api.learnops.duckdns.org` (configure Caddy/DNS for this host)
- Authentication header: `X-Proxy-Secret`
- Server secret: existing `FILAMENTDB_PROXY_SECRET` from `config.env`

## Endpoints

### `GET /v1/health`

Public liveness check. It does not expose database information.

### `GET /v1/health/ready`

Public readiness check. It verifies that the API secret is configured and the price database is reachable, without exposing the secret or database contents.

### `GET /v1/catalog/filaments`

Requires `X-Proxy-Secret`. Returns only tracked filament keys and basic catalog identity so a collector can use the canonical key.

### `POST /v1/ingest/prices`

Requires `X-Proxy-Secret`. Accepts one price offer and imports it directly into `price-history.db`. The request path never writes to the catalog database.

The collector sends the snapshot's `collected_at` value so the historical record retains the original acquisition timestamp.

Example:

```bash
curl -X POST 'https://filamentdb-api.learnops.duckdns.org/v1/ingest/prices' \\
  -H 'Content-Type: application/json' \\
  -H 'X-Proxy-Secret: YOUR_EXISTING_FILAMENTDB_PROXY_SECRET' \\
  -d '{
    "filament_key": "pla|esun|pla+hs",
    "store": "Mercado Livre",
    "url": "https://example.com/produto",
    "title": "eSUN PLA+ HS 1kg",
    "price": 89.90,
    "currency": "BRL",
    "quantity": 1,
    "unit_weight_g": 1000,
    "price_basis": "total",
    "available": true,
    "source": "Mercado Livre"
  }'
```

The API validates the payload, requires the filament to exist and have `tracking=1`, normalizes the offer, deduplicates the current offer identity, records the price snapshot, and commits the transaction before returning `201`.

## Secrets and GitHub Actions

The production server keeps the existing secret in `config.env`:

```env
FILAMENTDB_PROXY_SECRET=um-segredo-forte-e-privado
```

GitHub Actions must store the **same value** as the repository secret `FILAMENTDB_API_SECRET`. Do not put the secret in `vars`, source files, workflow literals, snapshots, or documentation.

The repository variable `FILAMENTDB_API_URL` may contain the public API URL. The current workflow has `https://filamentdb-api.learnops.duckdns.org` as a fallback, so the variable is optional while that hostname remains unchanged.

## Deploy

```bash
sudo cp systemd/filamentdb-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now filamentdb-api
sudo systemctl status filamentdb-api
```

Then configure Caddy/DNS so `filamentdb-api.learnops.duckdns.org` proxies to `127.0.0.1:5001`. Do not put Pangolin authentication in front of this hostname; the API itself authenticates with `X-Proxy-Secret`.

## Workflow flow

```text
AI price research
      ↓
validated daily snapshot
      ↓
POST /v1/ingest/prices (one offer at a time)
      ↓
price-history.db
      ↓
Git commit of the immutable snapshot
```
