# 🏪 Store Intelligence — Apex Retail CV Pipeline

**End-to-End CCTV Analytics: Raw Footage → Live Store Metrics**

---

## 🚀 Quick Links

| Resource | URL |
|----------|-----|
| 🔴 **Live Dashboard** (Docker) | http://localhost:3000 |
| 🟡 **Demo Dashboard** (no backend) | Open `dashboard/public/demo.html` in browser |
| 📖 **Swagger UI (API Docs)** | http://localhost:8000/docs |
| 📄 **ReDoc (API Docs)** | http://localhost:8000/redoc |
| 🏥 **Health Check** | http://localhost:8000/health |
| 📘 **Full API Reference** | [docs/API.md](docs/API.md) |

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
