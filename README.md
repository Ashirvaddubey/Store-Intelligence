# 🏪 Store Intelligence — Apex Retail CCTV Analytics

**End-to-End Computer Vision Pipeline: Raw CCTV Footage → Live Store Metrics**

> YOLOv8 + ByteTrack + Re-ID → FastAPI + PostgreSQL + Redis → Live WebSocket Dashboard

---

## 🚀 Quick Links

| Resource | URL |
|----------|-----|
| 🔴 **Live Dashboard** (Docker) | http://localhost:3000 |
| 🟡 **Demo Dashboard** (no backend) | `dashboard/public/demo.html` |
| 📖 **Swagger UI** | http://localhost:8000/docs |
| 📄 **ReDoc** | http://localhost:8000/redoc |
| 🏥 **Health Check** | http://localhost:8000/health |
| 📘 **Full API Reference** | [docs/API.md](docs/API.md) |
| 🏗️ **Architecture** | [docs/DESIGN.md](docs/DESIGN.md) |
| 🧠 **Technical Choices** | [docs/CHOICES.md](docs/CHOICES.md) |
| 🐙 **GitHub Repo** | https://github.com/Ashirvaddubey/Store-Intelligence |

---

## ⚡ Quick Start — Docker (Recommended)

```powershell
git clone https://github.com/Ashirvaddubey/Store-Intelligence store-intelligence
cd store-intelligence
Copy-Item .env.example .env
docker compose up -d --build
Start-Process http://localhost:3000
```

> **Windows DNS fix:** If Docker fails to pull images, add `"dns":["8.8.8.8","1.1.1.1"]`
> to `%APPDATA%\Docker\daemon.json` and restart Docker Desktop.

Once running:

| URL | What you get |
|-----|--------------|
| http://localhost:3000 | Live dashboard (WebSocket-driven) |
| http://localhost:8000/docs | Interactive Swagger UI |
| http://localhost:8000/health | JSON health probe |
| http://localhost:8000/ | Root landing page (all links) |

---

## 🖥️ Quick Start — Local Dev (no Docker)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r app/requirements.txt

$env:DATABASE_URL = "sqlite+aiosqlite:///./dev.db"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs — SQLite is created automatically, Redis is optional
(metrics cache degrades gracefully to DB-only mode).

---

## 🏗️ Architecture

```
CCTV Clips
    │
    ▼
pipeline/detect.py          YOLOv8-m  →  ByteTrack  →  cosine Re-ID
    │
    ▼
pipeline/emit.py            Structured JSONL events per visitor track
    │
    ▼
POST /events/ingest         FastAPI — dedup, validate, batch-write
    │
    ├──▶ PostgreSQL          Persistent event + session store
    └──▶ Redis               Real-time metrics cache + pub/sub
             │
             ▼
   GET /stores/{id}/metrics      Live KPIs  (visitors, dwell, conversion)
   GET /stores/{id}/funnel       Entry → Zone → Billing → Exit funnel
   GET /stores/{id}/heatmap      Zone frequency grid
   GET /stores/{id}/anomalies    Threshold-based anomaly alerts
             │
             ▼
    WS  /ws/{store_id}           Push updates every 2 s
             │
             ▼
   dashboard/server.js           Node.js WebSocket proxy → browser
```

---

## 🔌 API Endpoints

| # | Method | Endpoint | Description |
|---|--------|----------|-------------|
| 1 | `GET`  | `/` | Landing page — directory of all URLs |
| 2 | `POST` | `/events/ingest` | Batch ingest up to 500 events |
| 3 | `GET`  | `/stores/{id}/metrics` | Real-time KPIs |
| 4 | `GET`  | `/stores/{id}/funnel` | Conversion funnel |
| 5 | `GET`  | `/stores/{id}/heatmap` | Zone frequency heatmap |
| 6 | `GET`  | `/stores/{id}/anomalies` | Active anomaly alerts |
| 7 | `GET`  | `/health` | Service health + feed staleness |
| 8 | `WS`   | `/ws/{store_id}` | Live WebSocket feed |

**Sample store ID:** `STORE_BLR_002`

### Ingest events
```powershell
$body = @{ events = @(
  @{ event_id="evt-001"; store_id="STORE_BLR_002"; camera_id="CAM_ENTRY_01";
     visitor_id="vis-1"; event_type="ENTRY"; timestamp="2026-04-24T10:00:00Z";
     zone_id="ENTRY"; dwell_ms=0; is_staff=$false; confidence=0.92;
     raw_payload=@{} }
)} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method POST http://localhost:8000/events/ingest `
  -ContentType "application/json" -Body $body
```

### Get live metrics
```powershell
Invoke-RestMethod http://localhost:8000/stores/STORE_BLR_002/metrics
```

Full request/response schemas → [docs/API.md](docs/API.md)

---

## 🐳 Docker Services

| Service | Port | Health Check | Description |
|---------|------|-------------|-------------|
| `api` | 8000 | `GET /health` | FastAPI application (2 workers) |
| `postgres` | 5432 | `pg_isready` | Primary event store |
| `redis` | 6379 | `redis-cli ping` | Metrics cache + pub/sub (256 MB LRU) |
| `dashboard` | 3000 | `GET /health` | Node.js WebSocket proxy |

```powershell
# Check all container health
docker compose ps

# Tail API logs
docker compose logs -f api

# Run tests inside the container
docker compose exec api pytest tests/ -v --cov=app --cov-report=html

# Rebuild a single service after code changes
docker compose up -d --build api

# Full reset (removes volumes)
docker compose down -v
```

---

## 🧪 Test Suite

```powershell
# Inside Docker
docker compose exec api pytest tests/ -v --cov=app --cov-report=html

# Local (with venv active)
pytest tests/ -v --cov=app --cov-report=html --cov-fail-under=70

# Individual suites
pytest tests/test_events.py -v
pytest tests/test_stores.py -v
pytest tests/test_health.py -v
pytest tests/test_runtime.py -v

# View HTML report
Start-Process htmlcov/index.html
```

**Results:** 100 tests · **73.13% coverage** · gate ≥ 70% ✅

---

## 🎥 Detection Pipeline

### Install pipeline deps
```powershell
pip install -r app/requirements.txt
# GPU (optional):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Process a single clip
```powershell
python pipeline/detect.py `
  --video data/clips/STORE_BLR_002/CAM_ENTRY_01.mp4 `
  --store-id STORE_BLR_002 `
  --camera-id CAM_ENTRY_01 `
  --layout data/store_layout.json `
  --output data/events/entry_events.jsonl
```

### Process all clips
```powershell
bash pipeline/run.sh `
  --clips-dir data/clips `
  --layout data/store_layout.json `
  --output-dir data/events `
  --api-url http://localhost:8000
```

### Replay events (simulated real-time)
```powershell
python pipeline/replay.py `
  --events-dir data/events `
  --api-url http://localhost:8000 `
  --speed 10
```

---

## 📁 Project Structure

```
store-intelligence/
├── app/
│   ├── main.py              FastAPI entrypoint, middleware, lifespan
│   ├── db.py                SQLAlchemy async (Postgres + SQLite fallback)
│   ├── cache.py             Redis cache layer (graceful no-Redis mode)
│   ├── metrics.py           KPI computation
│   ├── funnel.py            Conversion funnel
│   ├── heatmap.py           Zone heatmap
│   ├── anomalies.py         Threshold anomaly detectors
│   ├── ingestion.py         Dedup + partial-success ingest
│   ├── pos_correlation.py   POS CSV join
│   ├── requirements.txt
│   └── Dockerfile
├── pipeline/
│   ├── detect.py            YOLOv8 + ByteTrack frame processor
│   ├── emit.py              Event emitter
│   ├── replay.py            Historical replay tool
│   └── load_pos.py          POS CSV CLI loader
├── dashboard/
│   ├── server.js            Express + WebSocket proxy
│   ├── public/index.html    Live dashboard
│   ├── public/demo.html     Standalone demo (no backend needed)
│   └── Dockerfile
├── tests/
│   ├── test_events.py
│   ├── test_stores.py
│   ├── test_health.py
│   └── test_runtime.py
├── docs/
│   ├── API.md               Full API reference
│   ├── DESIGN.md            Architecture & system design
│   └── CHOICES.md           Technical decision rationale
├── infra/
│   └── init.sql             PostgreSQL schema
├── data/
│   ├── clips/               CCTV clips (not committed)
│   ├── store_layout.json    Zone polygon definitions
│   └── pos_transactions.csv Sample POS data
├── docker-compose.yml
├── .env.example
├── .dockerignore
├── pytest.ini
└── SUBMISSION.txt
```

---

## 🛡️ Edge Case Handling

| Edge Case | Handling |
|-----------|----------|
| Group entry | ByteTrack assigns separate track IDs; each emits its own `ENTRY` |
| Staff exclusion | Colour histogram + zone pattern heuristic; `is_staff=true` excluded from all customer metrics |
| Re-entry | 60 s cooldown after EXIT; same Re-ID fingerprint → `REENTRY` event |
| Partial occlusion | Confidence < 0.5 still emitted but flagged; never silently dropped |
| Camera overlap | Cross-camera Re-ID with cosine similarity; dedup at ingest |
| Empty periods | All counters return `0`; never `null` or `5xx` on zero-traffic stores |
| No Redis | Cache layer degrades gracefully; all endpoints still work via DB |
| SQLite (local) | Auto-creates tables on startup; no Postgres/Alembic needed |

---

## 🔬 Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI 0.111 (Python 3.11) |
| Detection | YOLOv8-m + ByteTrack + cosine Re-ID |
| Database | PostgreSQL 15 (prod) · SQLite (local dev) |
| Cache / PubSub | Redis 7 (256 MB LRU, graceful fallback) |
| Dashboard | Node.js 20 + Express + WebSocket |
| Logging | structlog — JSON with `trace_id`, `event_count`, `latency_ms` |
| Tests | pytest-asyncio + httpx + aiosqlite |
| Containers | Docker Compose (4 services, all health-checked) |


---

## Quick Start (5 Commands)

```powershell
git clone https://github.com/Ashirvaddubey/Store-Intelligence store-intelligence
cd store-intelligence
Copy-Item .env.example .env
docker compose up -d --build
Start-Process http://localhost:3000
```

> **Note (Windows):** If Docker Desktop fails to pull images on first run, add  
> `"dns":["8.8.8.8","1.1.1.1"]` to `%APPDATA%\Docker\daemon.json` and restart Docker Desktop.

> **Live Dashboard**: http://localhost:3000  
> **Demo Dashboard** (no backend needed): open `dashboard/public/demo.html` in any browser  
> **API Docs (Swagger)**: http://localhost:8000/docs  
> **API Docs (ReDoc)**: http://localhost:8000/redoc  
> **Health**: http://localhost:8000/health

Then run the detection pipeline in a second terminal:

```powershell
bash pipeline/run.sh --clips-dir data/clips --layout data/store_layout.json --output-dir data/events --api-url http://localhost:8000
```

---

## Architecture Overview

```
CCTV Clips → detect.py (YOLOv8 + ByteTrack) → emit.py (Events)
                                                      ↓
                                          POST /events/ingest
                                                      ↓
                                    FastAPI + PostgreSQL + Redis
                                                      ↓
                              /metrics  /funnel  /heatmap  /anomalies
                                                      ↓
                                         Live Dashboard (WebSocket)
```

---

## Running the Detection Pipeline

### Prerequisites
```bash
pip install -r pipeline/requirements.txt
# GPU: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Process a single clip
```bash
python pipeline/detect.py \
  --video data/clips/STORE_BLR_002/CAM_ENTRY_01.mp4 \
  --store-id STORE_BLR_002 \
  --camera-id CAM_ENTRY_01 \
  --layout data/store_layout.json \
  --output data/events/entry_events.jsonl
```

### Process all clips for all stores
```bash
bash pipeline/run.sh \
  --clips-dir data/clips \
  --layout data/store_layout.json \
  --output-dir data/events \
  --api-url http://localhost:8000
```

### Windows PowerShell alternative
```powershell
bash pipeline/run.sh --clips-dir data/clips --layout data/store_layout.json --output-dir data/events --api-url http://localhost:8000
```

### Replay events into API (simulated real-time)
```bash
python pipeline/replay.py \
  --events-dir data/events \
  --api-url http://localhost:8000 \
  --speed 10   # 10x faster than real time
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/events/ingest` | Batch ingest up to 500 events |
| `GET`  | `/stores/{id}/metrics` | Real-time store metrics |
| `GET`  | `/stores/{id}/funnel` | Conversion funnel |
| `GET`  | `/stores/{id}/heatmap` | Zone frequency heatmap |
| `GET`  | `/stores/{id}/anomalies` | Active anomaly alerts |
| `GET`  | `/health` | Service health + feed staleness |
| `GET`  | `/ws/{store_id}` | WebSocket for live dashboard |

### Example: Ingest Events
```bash
curl -X POST http://localhost:8000/events/ingest \
  -H "Content-Type: application/json" \
  -d '{"events": [...]}'
```

### Example: Get Metrics
```bash
curl http://localhost:8000/stores/STORE_BLR_002/metrics
```

---

## Data Directory Layout

```
data/
├── clips/
│   └── STORE_BLR_002/
│       ├── CAM_ENTRY_01.mp4
│       ├── CAM_FLOOR_01.mp4
│       └── CAM_BILLING_01.mp4
├── store_layout.json
├── pos_transactions.csv
├── sample_events.jsonl
└── events/          ← pipeline output goes here
```

---

## Services (docker compose)

| Service | Port | Health Check | Description |
|---------|------|-------------|-------------|
| `api` | 8000 | `GET /health` | FastAPI application |
| `postgres` | 5432 | `pg_isready` | Primary event store |
| `redis` | 6379 | `redis-cli ping` | Real-time metrics cache |
| `dashboard` | 3000 | `GET /health` | Live web dashboard |

```powershell
# Check all containers are healthy
docker compose ps

# Stream live API logs
docker compose logs -f api

# Run tests inside the API container
docker compose exec api pytest tests/ -v --cov=app --cov-report=html

# Rebuild a single service after code changes
docker compose up -d --build api

# Tear down and wipe volumes (fresh start)
docker compose down -v
```

---

## Test Suite

```powershell
# Run all tests with coverage report
docker compose exec api pytest tests/ -v --cov=app --cov-report=html

# Run specific test files
docker compose exec api pytest tests/test_pipeline.py -v
docker compose exec api pytest tests/test_metrics.py -v
docker compose exec api pytest tests/test_anomalies.py -v

# View HTML coverage report
Start-Process htmlcov/index.html
```

Current gate: **≥ 70% coverage** (passing at **73.13%**, 100 tests).

---

## Part E — Live Dashboard

The dashboard at **http://localhost:3000** shows:
- Real-time visitor count (WebSocket push every 2s)
- Live conversion rate gauge
- Zone heatmap grid (colour-coded by dwell)
- Anomaly alert feed
- Queue depth indicator for billing zones

To drive the dashboard with your own clips:
```bash
python pipeline/replay.py --events-dir data/events --speed 5
```

---

## Notes on Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Group entry | ByteTrack assigns separate track IDs per bounding box; each emits its own `ENTRY` |
| Staff exclusion | Colour histogram + zone pattern heuristic; `is_staff=true` excluded from all customer metrics |
| Re-entry | 60s cooldown window after EXIT; same Re-ID fingerprint within cooldown → `REENTRY` event |
| Partial occlusion | Confidence < 0.5 still emitted but flagged; never silently dropped |
| Camera overlap | Cross-camera Re-ID with cosine similarity of appearance embeddings; dedup at ingest |
| Empty periods | All counters return 0; API never returns null or 5xx on zero-traffic stores |
