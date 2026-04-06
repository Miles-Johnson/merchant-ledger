# Vintage Story Merchant Ledger

Vintage Story Merchant Ledger is a pricing and recipe-costing toolkit for a roleplay server economy. It unifies Lodestone Registry (Empire) prices, FTA prices, and recipe decomposition to return deterministic costs in Copper Sovereigns.

## Tech Stack

- **Backend API:** Python (Flask) in `api/app.py`
- **Resolver/Pipeline:** Python scripts in `scripts/`
- **Frontend:** React + Vite in `webapp/`
- **Database:** PostgreSQL (configured via `.env`)

## Project Structure

- `scripts/` - ingestion, parsing, canonical linking, validation, resolver logic
- `api/` - API service
- `webapp/` - frontend app
- `data/` - source pricing CSVs and validation/debug outputs
- `migrations/` - SQL schema migration files
- `cline_docs/` - project memory bank and historical context

## Prerequisites

- Python 3.12+
- PostgreSQL
- Node.js + npm (for frontend)

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Create `.env` in project root:

```env
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db>
RECIPES_XLS_PATH=<optional legacy path>
VS_ASSETS_PATH=<vintage-story-assets-path>
```

## Run the Pipeline

Run the end-to-end pipeline:

```bash
python run_pipeline.py
```

Optional validation gate:

```bash
python scripts/final_gate_validate.py
```

## Start the API

```bash
python api/app.py
```

Default API endpoints include:

- `GET /health`
- `GET /search?q=<query>&limit=<n>`
- `POST /calculate`

## Start the Frontend

From `webapp/`:

```bash
npm install
npm run dev
```

## Notes

- This repository is tuned for a **specific Vintage Story roleplay server economy** and associated pricing sheets.
- LR (Empire) prices are primary when available, with FTA/recipe fallbacks.
