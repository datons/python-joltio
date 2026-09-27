# joltio

Python client for [Joltio Data](https://joltio.app/data). The canonical endpoint is `https://api.joltio.app/data`.

## Installation

```bash
pip install joltio
```

## Quick start

```python
from joltio import Client

client = Client(api_key="jol_live_...")

# Query the electricity market clearing price
df = client.data.query(
    "SELECT datetime, price "
    "FROM omie.prices "
    "WHERE country = 'ES' AND datetime >= now() - INTERVAL 7 DAY "
    "LIMIT 100"
)

# Dataset metadata (schema, programs, stats)
meta = client.data.metadata()

# Search for units, companies, technologies
results = client.data.search("iberdrola")
```

## Authentication

Request a personal Data key from your Joltio workspace administrator.

Pass it directly or set `JOLTIO_API_KEY`. `DATONS_API_KEY` remains a fallback during migration.

```bash
export JOLTIO_API_KEY="jol_live_..."
```

```python
from joltio import Client

client = Client()  # picks up JOLTIO_API_KEY
```
