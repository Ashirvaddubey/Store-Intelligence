# Store Intelligence API — Complete Reference

Interactive docs (Swagger UI): **http://localhost:8000/docs**  
ReDoc (read-only): **http://localhost:8000/redoc**  
OpenAPI JSON: **http://localhost:8000/openapi.json**

---

## Base URL

| Environment | URL |
|-------------|-----|
| Local (Docker) | `http://localhost:8000` |
| Local (dev server) | `http://127.0.0.1:8000` |

---

## Authentication

No authentication required for this version. All endpoints are open.

---

## Common Headers

| Header | Description |
|--------|-------------|
| `X-Trace-Id` | UUID added by middleware to every response — use for log correlation |

---

## Endpoints

### 1. `POST /events/ingest` — Batch Event Ingestion

Accepts a JSON body with a list of CCTV-derived tracking events.  
**Idempotent** by `event_id` — duplicates are counted but not re-inserted.  
**Partial success** — valid events are accepted even if some are malformed.

**Request body**

```json
{
  "events": [
    {
      "event_id":   "EVT_001",
      "store_id":   "STORE_BLR_002",
      "visitor_id": "VIS_abc123",
      "event_type": "ZONE_ENTRY",
      "zone_id":    "ELECTRONICS",
      "timestamp":  "2024-01-15T10:30:00Z",
      "dwell_ms":   45000,
      "is_staff":   false,
      "camera_id":  "CAM_03"
    }
  ]
}
```

**Fields**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `event_id` | string | ✅ | Unique identifier — duplicates are silently skipped |
| `store_id` | string | ✅ | Store identifier, e.g. `STORE_BLR_002` |
| `visitor_id` | string | ✅ | Re-ID'd visitor track ID |
| `event_type` | enum | ✅ | `ZONE_ENTRY`, `ZONE_EXIT`, `DWELL`, `BILLING_QUEUE_JOIN`, `BILLING_QUEUE_ABANDON` |
| `zone_id` | string | ✅ | Zone label from the store layout |
| `timestamp` | ISO-8601 | ✅ | UTC timestamp of the event |
| `dwell_ms` | integer | ❌ | Dwell time in milliseconds (for DWELL events) |
| `is_staff` | boolean | ❌ | Default `false`; staff events excluded from all analytics |
| `camera_id` | string | ❌ | Source camera identifier |

**Limits**: Max 500 events per request.

**Response — 207 Multi-Status**

```json
{
  "accepted": 98,
  "rejected": 2,
  "duplicates": 5,
  "errors": [
    {
      "index": 3,
      "event_id": "EVT_bad",
      "error": "event_type must be one of ZONE_ENTRY, ZONE_EXIT, ..."
    }
  ]
}
```

**Error responses**

| Status | Condition |
|--------|-----------|
| 422 | `events` missing, not a list, or all items invalid |
| 503 | Database unavailable |

---

### 2. `GET /stores/{store_id}/metrics` — Real-time Store Metrics

Returns live KPI metrics for a store. Staff events are excluded.

**Path params**: `store_id` (string)

**Query params**

| Param | Default | Range | Description |
|-------|---------|-------|-------------|
| `window_hours` | `24` | 1–168 | Lookback window in hours |

**Response — 200**

```json
{
  "store_id":        "STORE_BLR_002",
  "unique_visitors": 342,
  "conversion_rate": 0.187,
  "avg_dwell_ms":    285000,
  "queue_depth":     4,
  "abandonment_rate": 0.12,
  "window_hours":    24,
  "computed_at":     "2024-01-15T14:00:00Z"
}
```

**Field notes**

| Field | Description |
|-------|-------------|
| `unique_visitors` | Distinct `visitor_id` values in window |
| `conversion_rate` | `BILLING_QUEUE_JOIN` sessions / unique visitors |
| `avg_dwell_ms` | Mean dwell time across all DWELL events |
| `queue_depth` | Current count of people in billing queue (live) |
| `abandonment_rate` | `BILLING_QUEUE_ABANDON` / `BILLING_QUEUE_JOIN` |

**Caching**: 30-second Redis cache for `window_hours=24`. Other windows always computed fresh.

---

### 3. `GET /stores/{store_id}/funnel` — Conversion Funnel

Returns the 4-stage session funnel: Entry → Product Zone → Billing Queue → Purchase.

**Path params**: `store_id` (string)

**Query params**: `window_hours` (default 24, range 1–168)

**Response — 200**

```json
{
  "store_id": "STORE_BLR_002",
  "stages": [
    { "stage": "Store Entry",    "count": 342, "drop_off_pct": 0 },
    { "stage": "Product Zone",   "count": 246, "drop_off_pct": 28 },
    { "stage": "Billing Queue",  "count": 113, "drop_off_pct": 54 },
    { "stage": "Purchase",       "count":  64, "drop_off_pct": 43 }
  ],
  "window_hours": 24
}
```

**Note**: Re-entries are deduplicated — one visitor = one funnel unit per session.

---

### 4. `GET /stores/{store_id}/heatmap` — Zone Heatmap

Returns a per-zone heatmap scored 0–100, combining visit frequency and dwell time.

**Path params**: `store_id` (string)

**Query params**: `window_hours` (default 24, range 1–168)

**Response — 200**

```json
{
  "store_id": "STORE_BLR_002",
  "cells": [
    {
      "zone_id":          "ELECTRONICS",
      "visit_count":      89,
      "avg_dwell_ms":     312000,
      "normalised_score": 87,
      "rank":             1
    },
    {
      "zone_id":          "AISLE_B",
      "visit_count":      64,
      "avg_dwell_ms":     145000,
      "normalised_score": 52,
      "rank":             2
    }
  ],
  "data_confidence": "HIGH",
  "window_hours": 24
}
```

**`data_confidence`**: `HIGH` (≥ 20 sessions) | `LOW` (< 20 sessions).

---

### 5. `GET /stores/{store_id}/anomalies` — Active Anomalies

Detects and returns current anomalies across all configured detectors.

**Path params**: `store_id` (string)

**Response — 200**

```json
{
  "store_id": "STORE_BLR_002",
  "anomalies": [
    {
      "anomaly_type":     "LONG_QUEUE",
      "severity":         "CRITICAL",
      "description":      "Billing queue depth exceeded 8 for >5 min",
      "suggested_action": "Open additional checkout counter immediately",
      "detected_at":      "2024-01-15T14:05:30Z"
    },
    {
      "anomaly_type":     "DEAD_ZONE",
      "severity":         "WARN",
      "description":      "FRESH zone has <5 visitors in last hour",
      "suggested_action": "Review planogram and signage for fresh produce section",
      "detected_at":      "2024-01-15T13:58:00Z"
    }
  ]
}
```

**Anomaly types & severities**

| Anomaly Type | Severity | Trigger |
|--------------|----------|---------|
| `LONG_QUEUE` | CRITICAL | Queue depth > 8 for > 5 min |
| `ABANDONMENT_SPIKE` | WARN | Abandonment rate > 25% in 15 min |
| `DEAD_ZONE` | WARN | Zone < 5 visitors in last hour |
| `LOITERING_DETECTED` | INFO | Single visitor dwell > 45 min |
| `CONVERSION_DROP` | WARN | Conversion rate drops > 15% vs prior period |
| `STALE_FEED` | WARN | No events received for > 10 min |

---

### 6. `GET /health` — Service Health

Returns DB, cache connectivity, and per-store feed lag.

**Response — 200**

```json
{
  "status": "ok",
  "db": "ok",
  "cache": "ok",
  "stores": {
    "STORE_BLR_002": {
      "last_event_at": "2024-01-15T14:09:58Z",
      "feed_lag_s":    12,
      "feed_status":   "LIVE"
    }
  }
}
```

**`feed_status`**: `LIVE` (lag < 600s) | `STALE_FEED` (lag ≥ 600s).  
**`status`**: `ok` | `degraded` (if DB or cache is down).

---

### 7. `GET /ws/{store_id}` — Live WebSocket Feed

Streams real-time events and metrics snapshots to connected clients.

**URL**: `ws://localhost:8000/ws/{store_id}`

**Message types**

#### `metrics_snapshot` (sent every 30s)
```json
{
  "type": "metrics_snapshot",
  "data": {
    "store_id":        "STORE_BLR_002",
    "unique_visitors": 342,
    "conversion_rate": 0.187,
    "avg_dwell_ms":    285000,
    "queue_depth":     4,
    "abandonment_rate": 0.12
  }
}
```

#### `event` (sent on every new ingest)
```json
{
  "type": "event",
  "data": {
    "event_id":   "EVT_001",
    "store_id":   "STORE_BLR_002",
    "visitor_id": "VIS_abc123",
    "event_type": "ZONE_ENTRY",
    "zone_id":    "ELECTRONICS",
    "timestamp":  "2024-01-15T10:30:00Z"
  }
}
```

**JavaScript example**
```javascript
const ws = new WebSocket("ws://localhost:8000/ws/STORE_BLR_002");
ws.onmessage = (msg) => {
  const payload = JSON.parse(msg.data);
  if (payload.type === "metrics_snapshot") {
    updateDashboard(payload.data);
  } else if (payload.type === "event") {
    appendEventLog(payload.data);
  }
};
```

---

## Event Types Reference

| Event Type | Description |
|------------|-------------|
| `ZONE_ENTRY` | Visitor enters a zone |
| `ZONE_EXIT` | Visitor exits a zone |
| `DWELL` | Visitor stationary in a zone (includes `dwell_ms`) |
| `BILLING_QUEUE_JOIN` | Visitor joins the billing queue |
| `BILLING_QUEUE_ABANDON` | Visitor leaves queue without purchasing |

---

## Error Format

All error responses use this envelope:

```json
{
  "detail": "human-readable message or object"
}
```

For 500 errors (caught by middleware):
```json
{
  "error": "internal_server_error",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Request Logging

Every request is logged as structured JSON (via structlog):

```json
{
  "event": "http_request",
  "trace_id": "550e8400-...",
  "store_id": "STORE_BLR_002",
  "endpoint": "/stores/STORE_BLR_002/metrics",
  "method": "GET",
  "status_code": 200,
  "latency_ms": 12.4,
  "event_count": null
}
```

`event_count` is populated (non-null) only for `POST /events/ingest`.

---

## Replay Tool

Replays historical events in time order from the database through the REST API:

```bash
# Inside Docker
docker exec si_api python -m pipeline.replay --store STORE_BLR_002 --batch-size 50

# Locally
python -m pipeline.replay --store STORE_BLR_002 --speed 2.0
```

| Flag | Default | Description |
|------|---------|-------------|
| `--store` | required | Store ID to replay |
| `--batch-size` | 100 | Events per POST request |
| `--speed` | 1.0 | Replay speed multiplier |
| `--dry-run` | false | Print batches without POSTing |

---

## POS Correlation

The `load_pos` pipeline loads POS transaction CSV and joins to visitor sessions.

**CSV format**:
```csv
transaction_id,store_id,timestamp,amount,visitor_id
TXN_001,STORE_BLR_002,2024-01-15T14:10:00Z,1250.00,VIS_abc123
```

**Load via API**:
```bash
POST /events/ingest   # normal ingest flow, correlation computed at query time
```

**Auto-load on startup** (set in `.env`):
```
POS_CSV_PATH=data/pos_transactions.csv
```
