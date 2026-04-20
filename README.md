# 🏪 Store Intelligence — Apex Retail CV Pipeline

**End-to-End CCTV Analytics: Raw Footage → Live Store Metrics**

---

## Quick Start (5 Commands)

```bash
git clone <repo-url> store-intelligence && cd store-intelligence
cp .env.example .env
docker compose up -d
python pipeline/run.sh --clips-dir ./data/clips --store-id STORE_BLR_002
open http://localhost:8000/docs   # Swagger UI
```

> **Dashboard**: http://localhost:3000  
> **API Docs**: http://localhost:8000/docs  
> **Health**: http://localhost:8000/health

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

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI application |
| `postgres` | 5432 | Primary event store |
| `redis` | 6379 | Real-time metrics cache |
| `dashboard` | 3000 | Live web dashboard |

---

## Test Suite

```bash
# Run all tests with coverage report
docker compose exec api pytest tests/ -v --cov=app --cov-report=html

# Run specific test files
docker compose exec api pytest tests/test_pipeline.py -v
docker compose exec api pytest tests/test_metrics.py -v
docker compose exec api pytest tests/test_anomalies.py -v

# Coverage report
open htmlcov/index.html
```

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
