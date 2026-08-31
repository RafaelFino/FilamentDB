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

### `GET /v1/catalog/filaments`

Requires `X-Proxy-Secret`. Returns only tracked filament keys and basic catalog identity so a collector can use the canonical key.

### `POST /v1/ingest/prices`

Requires `X-Proxy-Secret`. Accepts one price offer and imports it directly into `price-history.db`. The request path never writes to the catalog database.

Example:

```bash
curl -X POST 'https://filamentdb-api.learnops.duckdns.org/v1/ingest/prices' \
  -H 'Content-Type: application/json' \
  -H 'X-Proxy-Secret: YOUR_EXISTING_FILAMENTDB_PROXY_SECRET' \
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

## Deploy

```bash
sudo cp systemd/filamentdb-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now filamentdb-api
sudo systemctl status filamentdb-api
```

Then configure Caddy/DNS so `filamentdb-api.learnops.duckdns.org` proxies to `127.0.0.1:5001`. Do not put Pangolin authentication in front of this hostname; the API itself authenticates with `X-Proxy-Secret`.
