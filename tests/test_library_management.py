"""Local deletion and device storage estimates never share a page count."""
import asyncio
import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huion_note_pipeline.application import HuionApplication
from huion_note_pipeline import application


def test_trash_moves_companions_and_preserves_draft(pipeline, tmp_output, monkeypatch):
    service = HuionApplication(pipeline, MagicMock())
    strokes = [[(1000, 1000, 3000), (2000, 2000, 4000)]]
    svg = Path(service.save_live_page(strokes))
    note = next(n for n in service.load_notes() if n.svg_path == str(svg))
    service.save_markdown(note, "# Keep this transcript recoverable")
    backup = Path(note.markdown_path).with_suffix(".svg")
    pipeline.registry.load_from_disk(str(tmp_output))
    svg.with_suffix(".png").write_bytes(b"preview")
    trash = tmp_output / "trash-test"
    trash.mkdir()
    calls = []
    def move_files(args, **kwargs):
        calls.append(args)
        for name in args[3:]:
            shutil.move(name, str(trash / Path(name).name))
    monkeypatch.setattr(application.shutil, "which", lambda _: "/usr/bin/gio")
    monkeypatch.setattr(application.subprocess, "run", move_files)
    deleted = service.delete_notes([note])
    assert calls[0][:3] == ["gio", "trash", "--"]
    assert len(deleted) == 5
    assert not svg.exists() and not backup.exists()
    assert not pipeline.registry.all()
    assert (trash / Path(note.markdown_path).name).read_text().startswith("# Keep")
    assert service.live_draft() == [[list(p) for p in s] for s in strokes]
    assert service.save_live_page(strokes) != str(svg)
    service.bridge.clear_all_pages.assert_not_called()
    with pytest.raises(ValueError):
        service.delete_notes([note])


def test_trash_failure_keeps_files_and_registry(pipeline, tmp_output, monkeypatch):
    service = HuionApplication(pipeline, MagicMock())
    svg = Path(service.save_live_page([[(1000, 1000, 2000)]]))
    note = next(n for n in service.load_notes() if n.svg_path == str(svg))
    monkeypatch.setattr(application.shutil, "which", lambda _: "/usr/bin/gio")
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="Permission denied")
    monkeypatch.setattr(application.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="Permission denied"):
        service.delete_notes([note])
    assert svg.exists() and note in pipeline.registry.all()
    monkeypatch.setattr(application.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="no files were deleted"):
        service.delete_notes([note])


def test_storage_is_latest_complete_device_count_not_local_total(pipeline, tmp_output, monkeypatch):
    config_file = tmp_output / "config.json"
    cfg = {"mac_address": "AA:BB:CC:DD:EE:FF"}
    monkeypatch.setattr(application, "load_config", lambda: cfg.copy())
    monkeypatch.setattr(application, "save_config", lambda value: (cfg.update(value), config_file.write_text("{}")))
    monkeypatch.setattr("huion.ble.CONFIG_PATH", str(config_file))
    bridge = SimpleNamespace(_stream_thread=None, _current_conn=None, last_storage_sync=None)
    def sync(**kwargs):
        bridge.last_storage_sync = (cfg["mac_address"], 12)
        return [object()] * 12
    bridge.sync_offline_pages = sync
    service = HuionApplication(pipeline, bridge)
    assert service.device_snapshot().stored_pages is None
    service.sync()
    service.sync()
    assert service.device_snapshot().stored_pages == 12  # Not 24 cumulative imports.
    assert HuionApplication(pipeline, bridge).device_snapshot().stored_pages == 12
    bridge.last_storage_sync = None
    bridge.sync_offline_pages = lambda **kw: []  # Partial / uncertain sync.
    service.sync()
    assert service.device_snapshot().stored_pages == 12
    cfg["mac_address"] = "11:22:33:44:55:66"
    assert service.device_snapshot().stored_pages is None


def test_sync_and_free_space_uses_verified_transport_and_updates_storage(pipeline, tmp_output, monkeypatch):
    config_file = tmp_output / "config.json"
    config = {"mac_address": "AA:BB:CC:DD:EE:FF"}
    monkeypatch.setattr(application, "load_config", lambda: config.copy())
    monkeypatch.setattr(application, "save_config", lambda value: (config.update(value), config_file.write_text("{}")))
    monkeypatch.setattr("huion.ble.CONFIG_PATH", str(config_file))
    bridge = MagicMock()
    bridge.sync_offline_pages.return_value = [object(), object()]
    service = HuionApplication(pipeline, bridge)
    assert len(service.sync_and_free_space()) == 2
    assert bridge.sync_offline_pages.call_args.kwargs["delete_after_export"] is True
    assert service.device_snapshot().stored_pages == 0


def test_note_metadata_is_search_safe_and_persistent(pipeline, tmp_output, monkeypatch):
    config_file = tmp_output / "config.json"
    config = {}
    monkeypatch.setattr(application, "load_config", lambda: config.copy())
    monkeypatch.setattr(application, "save_config", lambda value: (config.clear(), config.update(value), config_file.write_text("{}")))
    monkeypatch.setattr("huion.ble.CONFIG_PATH", str(config_file))
    service = HuionApplication(pipeline, MagicMock())
    page = Path(service.save_live_page([[(1000, 1000, 3000)]]))
    note = next(n for n in service.load_notes() if n.svg_path == str(page))
    value = service.update_note_metadata(note, title="  Project   brief ", tags=["work", "work", " next  step "],
                                         collection=" Client A ", favourite=True, reviewed=True)
    assert value == {"title": "Project brief", "tags": ["work", "next step"], "collection": "Client A",
                     "favourite": True, "reviewed": True}
    assert service.note_metadata(note) == value


def test_page_header_timeout_is_not_empty_storage():
    from huion.sync_engine import OfflineSyncManager
    from unittest.mock import AsyncMock
    manager = OfflineSyncManager("AA:BB:CC:DD:EE:FF", "/tmp/unused")
    manager.transport = SimpleNamespace(send=AsyncMock(), recv=AsyncMock(side_effect=asyncio.TimeoutError))
    manager._storage_scan_complete = True
    assert asyncio.run(manager._fetch_page(0)) == (0, [])
    assert not manager._storage_scan_complete
    assert manager.storage_page_count is None


def test_storage_counts_occupied_slots_even_without_renderable_strokes(monkeypatch):
    from huion.sync_engine import OfflineSyncManager
    from unittest.mock import AsyncMock
    manager = OfflineSyncManager("AA:BB:CC:DD:EE:FF", "/tmp/unused")
    manager.transport = SimpleNamespace(connect=AsyncMock(), send=AsyncMock(), close=AsyncMock())
    manager._authenticate = AsyncMock()
    async def page(index):
        return (1, [bytes([0xCD, 0x87, 0, 1, 0] + [0] * 6)]) if index == 0 else (0, [])
    monkeypatch.setattr(manager, "_fetch_page", page)
    assert asyncio.run(manager.run_sync()) == []
    assert manager.storage_page_count == 1


def test_active_sync_records_storage_only_on_explicit_empty_reply(tmp_output):
    from huion_note_pipeline.ble_bridge import DeviceBridge
    from unittest.mock import AsyncMock
    bridge = DeviceBridge()
    async def write(frame):
        responses = {0x81: bytes([0xCD, 0x81, 6, 1, 2, 3]),
                     0x82: bytes([0xCD, 0x82, 4, 1]),
                     0x86: bytes([0xCD, 0x86, 5, 0, 0])}
        if frame[1] in responses:
            bridge._sync_queue.put_nowait(responses[frame[1]])
    bridge._current_conn = SimpleNamespace(mac="AA:BB:CC:DD:EE:FF", write_cmd=write,
                                           enter_live_tablet_mode=AsyncMock(), start_notifications=AsyncMock())
    assert asyncio.run(bridge._async_sync_active_conn(str(tmp_output))) == []
    assert bridge.last_storage_sync == ("AA:BB:CC:DD:EE:FF", 0)
    bridge._current_conn.start_notifications.assert_awaited_once()
    bridge._current_conn.enter_live_tablet_mode.assert_not_awaited()


def test_bridge_enters_live_handshake_only_for_tablet_mode(monkeypatch):
    from huion_note_pipeline import ble_bridge
    calls = []
    ready = threading.Event()

    class Connection:
        def __init__(self, mac):
            self.mac = mac
        async def connect(self):
            calls.append("connect")
        async def setup_signals(self, *_):
            pass
        async def start_notifications(self):
            calls.append("notes")
            ready.set()
        async def enter_live_tablet_mode(self):
            calls.append("tablet")
            ready.set()
        async def read_battery(self):
            return None
        async def close(self):
            calls.append("close")

    monkeypatch.setattr(ble_bridge, "BleDeviceConnection", Connection)
    bridge = ble_bridge.DeviceBridge()
    bridge.stream_pen_input("AA:BB:CC:DD:EE:FF", mode="notes")
    assert ready.wait(1) and "notes" in calls and "tablet" not in calls
    bridge.stop_pen_input()
    ready.clear()
    bridge.stream_pen_input("AA:BB:CC:DD:EE:FF", mode="tablet")
    assert ready.wait(1) and calls[-1] == "tablet"
    bridge.stop_pen_input()
