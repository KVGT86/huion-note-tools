import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from huion import ble
from huion_note_pipeline import application


X10_UUID = "76CBA0B9-48F5-4F51-9AA9-068E67E645A9"
OTHER_UUID = "23C4B24E-C981-4AAF-BD6D-758AB4616F58"


@pytest.fixture
def corebluetooth(monkeypatch):
    input_char = SimpleNamespace(properties=["notify"])
    command_char = SimpleNamespace(properties=["indicate", "write-without-response"])
    battery_char = SimpleNamespace(properties=["read"])
    client = SimpleNamespace(
        connect=AsyncMock(),
        disconnect=AsyncMock(),
        services=SimpleNamespace(get_characteristic={
            ble.FFE1_UUID: input_char,
            ble.FFE2_UUID: command_char,
            ble.BATTERY_CHAR_UUID: battery_char,
        }.get),
        is_connected=True,
        start_notify=AsyncMock(),
        read_gatt_char=AsyncMock(return_value=b"\x37"),
        write_gatt_char=AsyncMock(),
    )

    class BleakError(Exception):
        pass

    factory = Mock(return_value=client)
    device = SimpleNamespace(name=None, address=X10_UUID.lower())
    advertisement = SimpleNamespace(local_name="T218")
    scanner = SimpleNamespace(
        discover=AsyncMock(return_value={device.address: (device, advertisement)}),
        find_device_by_address=AsyncMock(return_value=device),
    )
    monkeypatch.setitem(sys.modules, "bleak", SimpleNamespace(BleakClient=factory, BleakScanner=scanner))
    monkeypatch.setitem(sys.modules, "bleak.exc", SimpleNamespace(BleakError=BleakError))
    monkeypatch.setattr(ble, "DEVICE_ADDRESS_KEY", "bluetooth_uuid")
    monkeypatch.setattr(ble, "load_config", lambda: {"mac_address": "AA:BB:CC:DD:EE:FF"})
    save_config = Mock()
    monkeypatch.setattr(ble, "save_config", save_config)
    return SimpleNamespace(client=client, factory=factory, scanner=scanner, save=save_config,
                           input_char=input_char, command_char=command_char, battery_char=battery_char)


def test_corebluetooth_discovers_and_exchanges_packets(corebluetooth):
    backend = corebluetooth
    conn = ble.CoreBluetoothConnection()
    notifications = Mock()
    disconnected = Mock()

    async def run():
        assert await conn.connect()
        await conn.setup_signals(notifications, disconnected)
        await conn.start_notifications()
        await conn.start_notifications()  # Switching X10 modes reuses the subscription.
        assert await conn.write_cmd(b"notebook command")
        assert await conn.read_battery() == 55
        char, callback = backend.client.start_notify.await_args_list[0].args
        callback(char, bytearray(b"pen data"))
        backend.factory.call_args.kwargs["disconnected_callback"](backend.client)
        await conn.close()

    asyncio.run(run())
    assert conn.mac == X10_UUID
    backend.save.assert_called_once_with({"mac_address": "AA:BB:CC:DD:EE:FF", "bluetooth_uuid": X10_UUID})
    backend.scanner.find_device_by_address.assert_not_awaited()
    assert [call.args[0] for call in backend.client.start_notify.await_args_list] == [
        backend.input_char, backend.command_char,
    ]
    notifications.assert_called_once_with(b"pen data")
    disconnected.assert_called_once()
    backend.client.write_gatt_char.assert_awaited_once_with(backend.command_char, b"notebook command", response=False)
    backend.client.disconnect.assert_awaited_once()


def test_corebluetooth_requires_selection_if_multiple_devices_advertise(corebluetooth):
    corebluetooth.scanner.discover.return_value[OTHER_UUID] = (
        SimpleNamespace(address=OTHER_UUID, name="Huion Note"),
        SimpleNamespace(local_name=None),
    )

    with pytest.raises(ConnectionError, match=f"{OTHER_UUID}.*{X10_UUID}"):
        asyncio.run(ble.CoreBluetoothConnection().connect())
    corebluetooth.factory.assert_not_called()
    corebluetooth.save.assert_not_called()


def test_corebluetooth_uses_configured_uuid(corebluetooth, monkeypatch):
    monkeypatch.setattr(ble, "load_config", lambda: {"bluetooth_uuid": X10_UUID.lower()})
    conn = ble.CoreBluetoothConnection()

    async def run():
        await conn.connect()
        await conn.close()

    asyncio.run(run())
    corebluetooth.scanner.find_device_by_address.assert_awaited_once_with(X10_UUID, timeout=8.0)
    corebluetooth.scanner.discover.assert_not_awaited()
    corebluetooth.save.assert_not_called()


def test_macos_settings_accept_uuid_and_ignore_linux_address(pipeline, tmp_output, monkeypatch):
    config = {"mac_address": "AA:BB:CC:DD:EE:FF"}
    config_path = tmp_output / "config.json"
    config_path.write_text("{}")
    monkeypatch.setattr(ble, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(ble, "IS_MACOS", True)
    monkeypatch.setattr(ble, "DEVICE_ADDRESS_KEY", "bluetooth_uuid")
    monkeypatch.setattr(application, "DEVICE_ADDRESS_KEY", "bluetooth_uuid")
    monkeypatch.setattr(application, "load_config", lambda: config.copy())
    monkeypatch.setattr(application, "save_config", config.update)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    service = application.HuionApplication(pipeline, Mock())
    assert service.mac_address == ""

    service.save_settings(str(tmp_output), "", X10_UUID.lower())
    assert service.mac_address == X10_UUID
    assert config["mac_address"] == "AA:BB:CC:DD:EE:FF"
    with pytest.raises(ValueError, match="Bluetooth UUID"):
        service.save_settings(str(tmp_output), "", config["mac_address"])


def test_macos_delete_uses_finder_trash(pipeline, tmp_output, monkeypatch):
    from pathlib import Path
    from PySide6 import QtCore

    service = application.HuionApplication(pipeline, Mock())
    svg = Path(service.save_live_page([[(1000, 1000, 2000)]]))
    note = next(n for n in service.load_notes() if n.svg_path == str(svg))
    trash = tmp_output / "finder-trash"
    trash.mkdir()

    class File:
        def __init__(self, filename):
            self.path = Path(filename)

        def moveToTrash(self):
            self.path.rename(trash / self.path.name)
            return True

    monkeypatch.setattr(application, "IS_MACOS", True)
    monkeypatch.setattr(QtCore, "QFile", File)
    deleted = service.delete_notes([note])
    assert {Path(path).name for path in deleted} == {path.name for path in trash.iterdir()}
    assert not svg.exists()
    assert note not in pipeline.registry.all()
