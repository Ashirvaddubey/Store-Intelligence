# PROMPT: "Write focused pytest tests to improve coverage for a Store Intelligence
# FastAPI + pipeline project. Cover runtime behavior for middleware logging,
# websocket streaming, replay utilities, POS loading CLI, and detect.py helper/
# main flow. Prefer mocks over real network/video/model dependencies."
#
# CHANGES MADE:
# - Added a real middleware assertion for `event_count` on ingest logs
# - Tested the middleware 500-path with a temporary route instead of mocking FastAPI internals
# - Covered websocket streaming by calling the handler directly with fake pubsub/websocket objects
# - Added happy-path and failure-path tests for `pipeline.detect.main`
# - Added CLI-style tests for `pipeline.replay` and `pipeline.load_pos`

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi import WebSocketDisconnect
from httpx import ASGITransport, AsyncClient

from app.main import app
from pipeline import detect, load_pos, replay
from tests.conftest import make_event


@pytest.mark.asyncio
async def test_ingest_logging_includes_event_count(client):
    events = [make_event(), make_event()]

    with patch("app.main.log.info") as log_info:
        response = await client.post("/events/ingest", json={"events": events})

    assert response.status_code == 207
    http_request_calls = [call for call in log_info.call_args_list if call.args and call.args[0] == "http_request"]
    assert http_request_calls
    assert http_request_calls[-1].kwargs["event_count"] == 2


@pytest.mark.asyncio
async def test_middleware_returns_500_for_unhandled_exception():
    async def boom_route():
        raise RuntimeError("boom")

    app.add_api_route("/__boom_runtime_test", boom_route, methods=["GET"])
    try:
        with patch("app.main.log.error") as log_error:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/__boom_runtime_test")
    finally:
        app.router.routes.pop()

    assert response.status_code == 500
    assert response.json()["error"] == "internal_server_error"
    assert "trace_id" in response.json()
    log_error.assert_called()


class _FakePubSub:
    def __init__(self):
        self.subscribed = []
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def aclose(self):
        self.closed = True

    async def listen(self):
        yield {"type": "message", "data": json.dumps({"event_type": "ENTRY", "visitor_id": "VIS_123"})}


class _FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_websocket_feed_sends_snapshot_and_event():
    from app.routers.ws import websocket_feed

    fake_ws = _FakeWebSocket()
    fake_pubsub = _FakePubSub()

    async def fake_gather(*coroutines):
        await coroutines[0]
        for coroutine in coroutines[1:]:
            coroutine.close()
        raise WebSocketDisconnect()

    with patch("app.routers.ws.get_pubsub", return_value=fake_pubsub), \
         patch("app.routers.ws.get_metrics", side_effect=[{"store_id": "STORE_BLR_002", "unique_visitors": 1}, None]), \
         patch("app.routers.ws.asyncio.gather", side_effect=fake_gather):
        await websocket_feed(fake_ws, "STORE_BLR_002")

    assert fake_ws.accepted is True
    assert fake_pubsub.subscribed == ["store_events:STORE_BLR_002"]
    assert fake_pubsub.unsubscribed == ["store_events:STORE_BLR_002"]
    assert fake_pubsub.closed is True
    assert fake_ws.messages[0]["type"] == "metrics_snapshot"
    assert fake_ws.messages[1]["type"] == "event"
    assert fake_ws.messages[1]["data"]["visitor_id"] == "VIS_123"


def test_replay_load_all_events_sorts_and_filters(tmp_path):
    file_one = tmp_path / "a.jsonl"
    file_two = tmp_path / "b.jsonl"

    file_one.write_text(
        json.dumps({"store_id": "STORE_X", "timestamp": "2026-03-03T14:00:10Z"}) + "\n"
        + "not-json\n"
        + json.dumps({"store_id": "STORE_Y", "timestamp": "2026-03-03T14:00:05Z"}) + "\n"
    )
    file_two.write_text(
        json.dumps({"store_id": "STORE_X", "timestamp": "2026-03-03T14:00:01Z"}) + "\n"
    )

    events = replay.load_all_events(str(tmp_path), "STORE_X")

    assert [event["timestamp"] for event in events] == [
        "2026-03-03T14:00:01Z",
        "2026-03-03T14:00:10Z",
    ]


def test_replay_posts_in_batches():
    events = [
        {"timestamp": "2026-03-03T14:00:00Z", "store_id": "STORE_BLR_002"},
        {"timestamp": "2026-03-03T14:00:00Z", "store_id": "STORE_BLR_002"},
        {"timestamp": "2026-03-03T14:00:00Z", "store_id": "STORE_BLR_002"},
    ]
    seen_batch_sizes = []

    def fake_post(batch, _url):
        seen_batch_sizes.append(len(list(batch)))

    with patch("pipeline.replay._post", side_effect=fake_post) as post_mock, \
         patch("pipeline.replay.time.sleep"):
        replay.replay(events, "http://localhost:8000", speed=999999, batch_size=2)

    assert post_mock.call_count == 2
    assert sorted(seen_batch_sizes) == [1, 2]


def test_replay_main_exits_when_no_events_found(capsys):
    args = SimpleNamespace(events_dir="data/events", api_url="http://localhost:8000", speed=10, store_id=None, batch_size=20, loop=False)

    with patch("pipeline.replay.parse_args", return_value=args), \
         patch("pipeline.replay.load_all_events", return_value=[]):
        with pytest.raises(SystemExit):
            replay.main()

    captured = capsys.readouterr()
    assert "No events found" in captured.out


def test_load_pos_parse_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["load_pos.py", "--csv", "data/pos.csv", "--store-id", "STORE_BLR_002"])
    args = load_pos.parse_args()
    assert args.csv == "data/pos.csv"
    assert args.store_id == "STORE_BLR_002"


@pytest.mark.asyncio
async def test_load_pos_main_loads_and_matches(capsys):
    args = SimpleNamespace(csv="data/pos_transactions.csv", store_id="STORE_BLR_002")
    init_db = AsyncMock()
    load_transactions = AsyncMock(return_value=4)
    run_matching = AsyncMock(return_value=2)
    session = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_db_module = SimpleNamespace(init_db=init_db, AsyncSessionLocal=lambda: _SessionManager())
    fake_pos_module = SimpleNamespace(
        load_pos_transactions=load_transactions,
        run_conversion_matching=run_matching,
    )

    with patch("pipeline.load_pos.parse_args", return_value=args), \
         patch.dict(sys.modules, {"app.db": fake_db_module, "app.pos_correlation": fake_pos_module}):
        await load_pos.main()

    init_db.assert_awaited_once()
    load_transactions.assert_awaited_once_with("data/pos_transactions.csv", session)
    run_matching.assert_awaited_once_with("STORE_BLR_002", session)
    assert session.commit.await_count == 2
    assert "4 loaded, 2 sessions matched" in capsys.readouterr().out


def test_detect_load_layout_supports_list_and_dict(tmp_path):
    list_layout = tmp_path / "list_layout.json"
    dict_layout = tmp_path / "dict_layout.json"

    list_layout.write_text(json.dumps([
        {"store_id": "STORE_A", "zones": [{"zone_id": "ENTRY"}]},
    ]))
    dict_layout.write_text(json.dumps({
        "STORE_A": {"zones": [{"zone_id": "ENTRY"}]},
    }))

    assert detect.load_layout(str(list_layout), "STORE_A")["zones"][0]["zone_id"] == "ENTRY"
    assert detect.load_layout(str(dict_layout), "STORE_A")["zones"][0]["zone_id"] == "ENTRY"


def test_detect_build_clip_timestamp_uses_file_mtime(tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake-video")
    ts_expected = datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc).timestamp()
    Path(video_path).touch()
    import os
    os.utime(video_path, (ts_expected, ts_expected))

    timestamp = detect.build_clip_timestamp(None, str(video_path))

    assert timestamp == datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc)


def test_detect_main_processes_single_frame(tmp_path):
    video_path = tmp_path / "clip.mp4"
    layout_path = tmp_path / "layout.json"
    output_path = tmp_path / "events.jsonl"
    video_path.write_bytes(b"video")
    layout_path.write_text(json.dumps({"STORE_BLR_002": {"zones": []}}))

    args = SimpleNamespace(
        video=str(video_path),
        store_id="STORE_BLR_002",
        camera_id="CAM_ENTRY_01",
        layout=str(layout_path),
        output=str(output_path),
        api_url=None,
        start_time="2026-03-03T14:00:00Z",
        batch_size=50,
        conf_thresh=0.35,
        skip_frames=0,
        device="cpu",
    )

    frame = np.zeros((20, 20, 3), dtype=np.uint8)

    class _FakeCap:
        def __init__(self):
            self.calls = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == detect.cv2.CAP_PROP_FPS:
                return 15.0
            if prop == detect.cv2.CAP_PROP_FRAME_COUNT:
                return 1
            return 0

        def read(self):
            self.calls += 1
            if self.calls == 1:
                return True, frame
            return False, None

        def release(self):
            return None

    fake_box = SimpleNamespace(xyxy=[np.array([1, 1, 10, 10])], conf=[0.91])
    fake_model = MagicMock()
    fake_model.predict.return_value = [SimpleNamespace(boxes=[fake_box])]
    fake_tracker = MagicMock()
    fake_tracker.update.return_value = [{
        "visitor_id": "VIS_demo",
        "bbox": [1, 1, 10, 10],
        "confidence": 0.91,
        "is_reentry": False,
        "zone_history": [],
    }]
    fake_emitter = MagicMock()
    fake_emitter.event_count = 1
    fake_staff = MagicMock()
    fake_staff.is_staff.return_value = False
    fake_zone_mapper = MagicMock()
    fake_zone_mapper.classify.return_value = "ENTRY"

    with patch("pipeline.detect.parse_args", return_value=args), \
         patch.dict(sys.modules, {"ultralytics": SimpleNamespace(YOLO=lambda *_args, **_kwargs: fake_model)}), \
         patch("pipeline.detect.cv2.VideoCapture", return_value=_FakeCap()), \
         patch("pipeline.detect.PersonTracker", return_value=fake_tracker), \
         patch("pipeline.detect.EventEmitter", return_value=fake_emitter), \
         patch("pipeline.detect.StaffDetector", return_value=fake_staff), \
         patch("pipeline.detect.ZoneMapper", return_value=fake_zone_mapper):
        detect.main()

    fake_tracker.update.assert_called_once()
    fake_emitter.process_track.assert_called_once()
    fake_emitter.flush.assert_called_once()


def test_detect_main_exits_when_video_cannot_open(tmp_path):
    video_path = tmp_path / "missing.mp4"
    layout_path = tmp_path / "layout.json"
    output_path = tmp_path / "events.jsonl"
    layout_path.write_text(json.dumps({"STORE_BLR_002": {"zones": []}}))

    args = SimpleNamespace(
        video=str(video_path),
        store_id="STORE_BLR_002",
        camera_id="CAM_ENTRY_01",
        layout=str(layout_path),
        output=str(output_path),
        api_url=None,
        start_time="2026-03-03T14:00:00Z",
        batch_size=50,
        conf_thresh=0.35,
        skip_frames=0,
        device="cpu",
    )

    class _ClosedCap:
        def isOpened(self):
            return False

    with patch("pipeline.detect.parse_args", return_value=args), \
         patch.dict(sys.modules, {"ultralytics": SimpleNamespace(YOLO=lambda *_args, **_kwargs: MagicMock())}), \
         patch("pipeline.detect.cv2.VideoCapture", return_value=_ClosedCap()), \
         patch("pipeline.detect.sys.exit", side_effect=SystemExit):
        with pytest.raises(SystemExit):
            detect.main()
