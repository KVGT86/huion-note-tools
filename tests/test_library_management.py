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
                                           authenticate_notes_mode=AsyncMock(), enter_live_tablet_mode=AsyncMock(),
                                           enter_notes_mode=AsyncMock())
    assert asyncio.run(bridge._async_sync_active_conn(str(tmp_output))) == []
    assert bridge.last_storage_sync == ("AA:BB:CC:DD:EE:FF", 0)
    bridge._current_conn.authenticate_notes_mode.assert_awaited_once()
    bridge._current_conn.enter_notes_mode.assert_not_awaited()
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
        async def enter_notes_mode(self):
            await self.start_notifications()
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
    ready.clear()
    bridge.stream_pen_input("AA:BB:CC:DD:EE:FF", mode="tablet")
    assert ready.wait(1) and "close" not in calls and calls[-1] == "tablet"
    bridge.stop_pen_input()


def test_bridge_is_not_ready_until_mode_handshake_finishes(monkeypatch):
    from huion_note_pipeline import ble_bridge
    entered = threading.Event()
    release = threading.Event()
    ready = threading.Event()

    class Connection:
        def __init__(self, mac):
            self.mac = mac
        async def connect(self):
            pass
        async def setup_signals(self, *_):
            pass
        async def enter_notes_mode(self):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
        async def read_battery(self):
            ready.set()
            return None
        async def close(self):
            pass

    monkeypatch.setattr(ble_bridge, "BleDeviceConnection", Connection)
    bridge = ble_bridge.DeviceBridge()
    bridge.stream_pen_input("AA:BB:CC:DD:EE:FF", mode="notes")
    assert entered.wait(1)
    assert not bridge.is_connected()
    release.set()
    assert ready.wait(1)
    assert bridge.is_connected()
    bridge.stop_pen_input()


def test_mode_switch_reuses_worker_still_connecting(monkeypatch):
    from huion_note_pipeline import ble_bridge
    first_started = threading.Event()
    release = threading.Event()
    tablet_ready = threading.Event()
    instances = []
    modes = []

    class Connection:
        def __init__(self, mac):
            self.mac = mac
            self.index = len(instances)
            instances.append(self)
        async def connect(self):
            if self.index == 0:
                first_started.set()
                while not release.is_set():
                    await asyncio.sleep(0.01)
        async def setup_signals(self, *_):
            pass
        async def enter_notes_mode(self):
            modes.append("notes")
        async def enter_live_tablet_mode(self):
            modes.append("tablet")
            tablet_ready.set()
        async def read_battery(self):
            return None
        async def close(self):
            pass

    monkeypatch.setattr(ble_bridge, "BleDeviceConnection", Connection)
    bridge = ble_bridge.DeviceBridge()
    bridge.stream_pen_input("AA:BB:CC:DD:EE:FF", mode="notes")
    assert first_started.wait(1)
    bridge.stream_pen_input("AA:BB:CC:DD:EE:FF", mode="tablet")
    release.set()
    assert tablet_ready.wait(1)
    assert modes == ["tablet"]
    assert len(instances) == 1
    assert bridge._current_conn is instances[0]
    assert bridge.is_connected()
    bridge.stop_pen_input()


def test_notes_mode_sends_idle_heartbeat():
    from huion.ble import BleDeviceConnection
    from unittest.mock import AsyncMock
    conn = BleDeviceConnection("AA:BB:CC:DD:EE:FF")
    conn.start_notifications = AsyncMock()
    conn.authenticate_notes_mode = AsyncMock()
    conn.write_cmd = AsyncMock(return_value=True)

    async def enter():
        await conn.enter_notes_mode()
        await asyncio.sleep(0)
        conn._ka_task.cancel()
        await conn._ka_task

    asyncio.run(enter())
    conn.start_notifications.assert_awaited_once()
    conn.authenticate_notes_mode.assert_awaited_once()
    conn.write_cmd.assert_awaited_once_with(bytes([0xCD, 0x80, 0x08, 0, 0, 0, 0, 0xED]))


def test_notes_mode_authenticates_before_heartbeat():
    from huion.ble import BleDeviceConnection
    conn = BleDeviceConnection("AA:BB:CC:DD:EE:FF")
    writes = []

    async def write(frame):
        writes.append(frame)
        if frame[1] == 0x81:
            conn._on_notify_cb(bytes([0xCD, 0x81, 0x08, 1, 2, 3, 0, 0xED]))
        elif frame[1] == 0x82:
            conn._on_notify_cb(bytes([0xCD, 0x81, 0x08, 1, 2, 3, 0, 0xED]))
            conn._on_notify_cb(bytes([0xCD, 0x82, 0x08, 1, 0, 0, 0, 0xED]))
        return True

    conn.write_cmd = write
    asyncio.run(conn.authenticate_notes_mode())
    assert [frame[1] for frame in writes] == [0x81, 0x82]


def test_connection_retry_does_not_disconnect_resolving_device():
    from dbus_fast import MessageType
    from huion.ble import BleDeviceConnection
    from unittest.mock import AsyncMock

    members = []

    class Bus:
        async def call(self, message):
            members.append(message.member)
            if members.count("Connect") == 1:
                return SimpleNamespace(message_type=MessageType.ERROR, error_name="org.bluez.Error.Failed")
            return SimpleNamespace(message_type=MessageType.METHOD_RETURN, error_name=None)

    conn = BleDeviceConnection("AA:BB:CC:DD:EE:FF")
    conn.bus = Bus()
    conn.dev_path = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
    conn._get_device_prop = AsyncMock(side_effect=lambda name: name == "ServicesResolved")
    conn._resolve_characteristics = AsyncMock()
    assert asyncio.run(conn.connect(retries=2))
    assert members == ["Connect", "Connect"]
