import asyncio
import json
import logging
import os
import struct
from typing import Optional, Callable, Dict, Any, List, Tuple

from dbus_fast.aio import MessageBus
from dbus_fast import BusType, Message, MessageType, Variant

log = logging.getLogger("huion.ble")

BLUEZ = "org.bluez"
CONFIG_PATH = os.path.expanduser("~/.config/huion/config.json")

# Vendor GATT Service and Characteristics
VENDOR_SVC_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1_UUID       = "0000ffe1-0000-1000-8000-00805f9b34fb"  # notify (data stream)
FFE2_UUID       = "0000ffe2-0000-1000-8000-00805f9b34fb"  # write / indicate (commands)

# Standard Battery Service
BATTERY_SVC_UUID  = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"  # Battery Level (0-100)

# Tablet Live Mode Commands
MARKER_START       = 0xCD
CMD_TABLET_NAME    = 0xC9  # get device name
CMD_TABLET_INFO    = 0xC8  # get device info
CMD_TABLET_VERIFY  = 0xCA  # verify manufacturer
CMD_TABLET_BATTERY = 0xD1  # battery query / keepalive
CMD_NOTE_HEARTBEAT = 0x80  # keep notebook mode paired without live streaming

def build_tablet_cmd(cmd_id: int) -> bytes:
    return bytes([MARKER_START, cmd_id, 0, 0, 0, 0, 0, 0])

def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "mac_address": "",
        "output_dir": os.path.expanduser("~/Documents/CYC-Caleb/00 Inbox/Raw PNGs"),
        "auto_pair": True,
        "pin": ""
    }

def save_config(config: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


class BleDeviceConnection:
    """Manages Bluetooth Low Energy communication with Huion Note X10 via BlueZ D-Bus."""

    def __init__(self, mac: Optional[str] = None):
        self.config = load_config()
        self.mac = (mac or self.config.get("mac_address") or "").strip().upper()
        self.bus: Optional[MessageBus] = None
        self.adapter_path: Optional[str] = None
        self.dev_path: Optional[str] = None
        self.ffe1_path: Optional[str] = None
        self.ffe2_path: Optional[str] = None
        self.battery_path: Optional[str] = None
        self._on_notify_cb: Optional[Callable[[bytes], None]] = None
        self._on_disconnect_cb: Optional[Callable[[], None]] = None
        self._ka_task: Optional[asyncio.Task] = None
        self._closed = False

    async def connect_bus(self) -> None:
        if not self.bus:
            self.bus = await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=True).connect()

    async def find_device(self, timeout_sec: float = 8.0) -> str:
        await self.connect_bus()

        path = await self._find_known_device_path()
        if path:
            return path

        if not self.adapter_path:
            self.adapter_path = await self._find_adapter_path()

        log.info(f"Scanning for Huion Note X10 on adapter {self.adapter_path}...")
        try:
            await self.bus.call(Message(
                destination=BLUEZ, path=self.adapter_path,
                interface="org.bluez.Adapter1", member="StartDiscovery"
            ))
        except Exception as e:
            log.debug(f"StartDiscovery notice: {e}")

        for _ in range(int(timeout_sec * 2)):
            await asyncio.sleep(0.5)
            path = await self._find_known_device_path()
            if path:
                try:
                    await self.bus.call(Message(
                        destination=BLUEZ, path=self.adapter_path,
                        interface="org.bluez.Adapter1", member="StopDiscovery"
                    ))
                except Exception:
                    pass
                return path

        raise TimeoutError("Huion Note X10 not found. Touch the pen to the pad or press the power button to wake it.")

    async def _find_adapter_path(self) -> str:
        reply = await self.bus.call(Message(
            destination=BLUEZ, path="/",
            interface="org.freedesktop.DBus.ObjectManager", member="GetManagedObjects"
        ))
        if reply.message_type == MessageType.METHOD_RETURN:
            objects = reply.body[0]
            for path, ifaces in objects.items():
                if "org.bluez.Adapter1" in ifaces:
                    return path
        return "/org/bluez/hci0"

    async def _find_known_device_path(self) -> Optional[str]:
        reply = await self.bus.call(Message(
            destination=BLUEZ, path="/",
            interface="org.freedesktop.DBus.ObjectManager", member="GetManagedObjects"
        ))
        if reply.message_type != MessageType.METHOD_RETURN:
            return None

        objects = reply.body[0]
        for path, ifaces in objects.items():
            if "org.bluez.Device1" in ifaces:
                dev = ifaces["org.bluez.Device1"]
                addr = dev.get("Address", Variant("s", "")).value.upper()
                name = dev.get("Name", Variant("s", "")).value

                if self.mac and addr == self.mac:
                    self.dev_path = path
                    self.adapter_path = dev.get("Adapter", Variant("o", "/org/bluez/hci0")).value
                    return path
                if not self.mac and ("Huion" in name or "HUION" in name or "T218" in name):
                    self.mac = addr
                    self.config["mac_address"] = addr
                    save_config(self.config)
                    self.dev_path = path
                    self.adapter_path = dev.get("Adapter", Variant("o", "/org/bluez/hci0")).value
                    return path
        return None

    async def connect(self, retries: int = 4) -> bool:
        if not self.dev_path:
            self.dev_path = await self.find_device()

        log.info(f"Connecting to Huion Note at {self.mac} ({self.dev_path})...")

        # Ensure adapter is powered
        if self.adapter_path:
            try:
                await self.bus.call(Message(
                    destination=BLUEZ, path=self.adapter_path,
                    interface="org.freedesktop.DBus.Properties", member="Set",
                    signature="ssv", body=["org.bluez.Adapter1", "Powered", Variant("b", True)]
                ))
            except Exception:
                pass

        connected = False
        for attempt in range(retries):
            # On retry attempts, clear any stale state and trigger brief discovery to listen for tablet advertisements
            if attempt > 0:
                try:
                    await self.bus.call(Message(
                        destination=BLUEZ, path=self.dev_path,
                        interface="org.bluez.Device1", member="Disconnect"
                    ))
                except Exception:
                    pass

                if self.adapter_path:
                    try:
                        await self.bus.call(Message(
                            destination=BLUEZ, path=self.adapter_path,
                            interface="org.bluez.Adapter1", member="StartDiscovery"
                        ))
                        await asyncio.sleep(1.2)
                        await self.bus.call(Message(
                            destination=BLUEZ, path=self.adapter_path,
                            interface="org.bluez.Adapter1", member="StopDiscovery"
                        ))
                    except Exception:
                        pass

            reply = await self.bus.call(Message(
                destination=BLUEZ, path=self.dev_path,
                interface="org.bluez.Device1", member="Connect"
            ))
            if reply.message_type == MessageType.METHOD_RETURN or (reply.error_name and "AlreadyConnected" in reply.error_name):
                connected = True
                break
            else:
                log.debug(f"Connect attempt {attempt + 1} notice: {reply.error_name}")
                await asyncio.sleep(0.5)

        if not connected:
            # Check if property says Connected anyway
            is_conn = await self._get_device_prop("Connected")
            if not is_conn:
                raise ConnectionError(
                    "Could not connect to Huion Note. Please wake the tablet by touching the pen to the paper surface or pressing the page button."
                )

        # Wait for GATT ServicesResolved
        for _ in range(50):
            resolved = await self._get_device_prop("ServicesResolved")
            if resolved:
                break
            await asyncio.sleep(0.1)

        # Resolve FFE1 and FFE2 paths
        await self._resolve_characteristics()
        return True

    async def _get_device_prop(self, prop_name: str) -> Any:
        reply = await self.bus.call(Message(
            destination=BLUEZ, path=self.dev_path,
            interface="org.freedesktop.DBus.Properties", member="Get",
            signature="ss", body=["org.bluez.Device1", prop_name]
        ))
        if reply.message_type == MessageType.METHOD_RETURN and reply.body:
            return reply.body[0].value
        return None

    async def _resolve_characteristics(self) -> None:
        for _ in range(20):
            reply = await self.bus.call(Message(
                destination=BLUEZ, path="/",
                interface="org.freedesktop.DBus.ObjectManager", member="GetManagedObjects"
            ))
            if reply.message_type == MessageType.METHOD_RETURN and reply.body:
                objects = reply.body[0]
                for path, ifaces in objects.items():
                    if "org.bluez.GattCharacteristic1" in ifaces and path.startswith(self.dev_path):
                        ch = ifaces["org.bluez.GattCharacteristic1"]
                        uuid = ch.get("UUID", Variant("s", "")).value.lower()
                        if uuid == FFE1_UUID:
                            self.ffe1_path = path
                        elif uuid == FFE2_UUID:
                            self.ffe2_path = path
                        elif uuid == BATTERY_CHAR_UUID:
                            self.battery_path = path

            if self.ffe1_path and self.ffe2_path:
                return
            await asyncio.sleep(0.2)

        if not self.ffe1_path or not self.ffe2_path:
            raise RuntimeError(f"Could not resolve GATT characteristics FFE1/FFE2 on {self.dev_path}")

    async def read_battery(self) -> Optional[int]:
        """Read battery level (0-100) from the standard BLE Battery Service.

        Returns None if the characteristic is unavailable or the read fails.
        Falls back to parsing 0xD1 keepalive responses if 0x2A19 is absent.
        """
        if not self.battery_path or not self.bus:
            return None
        try:
            reply = await self.bus.call(Message(
                destination=BLUEZ, path=self.battery_path,
                interface="org.bluez.GattCharacteristic1", member="ReadValue",
                signature="a{sv}", body=[{}]
            ))
            if reply.message_type == MessageType.METHOD_RETURN and reply.body:
                raw = bytes(reply.body[0])
                if raw:
                    return int(raw[0])
        except Exception as e:
            log.debug(f"Battery read error: {e}")
        return None

    async def setup_signals(self, on_notify: Callable[[bytes], None], on_disconnect: Callable[[], None]) -> None:
        self._on_notify_cb = on_notify
        self._on_disconnect_cb = on_disconnect

        def _msg_handler(msg: Message) -> None:
            if msg.member == "PropertiesChanged" and msg.interface == "org.freedesktop.DBus.Properties":
                if not msg.body or len(msg.body) < 2:
                    return
                changed = msg.body[1]
                if not isinstance(changed, dict):
                    return
                if "Value" in changed and msg.path and self.dev_path and self.dev_path in msg.path:
                    val = bytes(changed["Value"].value)
                    if self._on_notify_cb:
                        self._on_notify_cb(val)
                elif msg.path == self.dev_path and "Connected" in changed:
                    if not changed["Connected"].value and self._on_disconnect_cb:
                        self._on_disconnect_cb()

        self.bus.add_message_handler(_msg_handler)
        try:
            await self.bus.call(Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch", signature="s",
                body=[f"type='signal',sender='{BLUEZ}',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',path_namespace='{self.dev_path}'"]
            ))
        except Exception as e:
            log.debug(f"AddMatch notice: {e}")

    async def write_cmd(self, data: bytes) -> bool:
        if not self.ffe2_path:
            return False
        reply = await self.bus.call(Message(
            destination=BLUEZ, path=self.ffe2_path,
            interface="org.bluez.GattCharacteristic1", member="WriteValue",
            signature="aya{sv}", body=[bytearray(data), {"type": Variant("s", "command")}]
        ))
        return reply.message_type == MessageType.METHOD_RETURN

    async def start_notifications(self) -> None:
        for path in (self.ffe1_path, self.ffe2_path):
            reply = await self.bus.call(Message(
                destination=BLUEZ, path=path,
                interface="org.bluez.GattCharacteristic1", member="StartNotify"
            ))
            if reply.message_type == MessageType.ERROR:
                err = reply.error_name or ""
                if "InProgress" not in err and "AlreadyNotifying" not in err:
                    log.debug(f"StartNotify on {path}: {err}")

    async def enter_live_tablet_mode(self) -> None:
        """Enable notifications and send the handshake that switches the X10 to live streaming."""
        await self.start_notifications()
        if self._ka_task:
            self._ka_task.cancel()
        # 3-step Pen Tablet Handshake:
        await self.write_cmd(build_tablet_cmd(CMD_TABLET_NAME))
        await asyncio.sleep(0.05)
        await self.write_cmd(build_tablet_cmd(CMD_TABLET_INFO))
        await asyncio.sleep(0.05)
        await self.write_cmd(build_tablet_cmd(CMD_TABLET_VERIFY))
        await asyncio.sleep(0.05)

        self._ka_task = asyncio.create_task(self._live_keepalive_loop())
        log.info("Entered live tablet streaming mode.")

    async def enter_notes_mode(self) -> None:
        """Keep the X10 paired without enabling live pen streaming."""
        await self.start_notifications()
        if self._ka_task:
            self._ka_task.cancel()
        heartbeat = bytes([MARKER_START, CMD_NOTE_HEARTBEAT, 0x08, 0, 0, 0, 0, 0xED])
        await self.write_cmd(heartbeat)
        self._ka_task = asyncio.create_task(self._notes_keepalive_loop(heartbeat))

    async def _notes_keepalive_loop(self, heartbeat: bytes) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(5.0)
                await self.write_cmd(heartbeat)
        except asyncio.CancelledError:
            pass

    async def _live_keepalive_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(5.0)
                await self.write_cmd(build_tablet_cmd(CMD_TABLET_BATTERY))
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        self._closed = True
        if self._ka_task:
            self._ka_task.cancel()
        if self.bus:
            for path in (self.ffe1_path, self.ffe2_path):
                if path:
                    try:
                        await self.bus.call(Message(
                            destination=BLUEZ, path=path,
                            interface="org.bluez.GattCharacteristic1", member="StopNotify"
                        ))
                    except Exception:
                        pass
            if self.dev_path:
                try:
                    await self.bus.call(Message(
                        destination=BLUEZ, path=self.dev_path,
                        interface="org.bluez.Device1", member="Disconnect"
                    ))
                except Exception:
                    pass
            try:
                self.bus.disconnect()
            except Exception:
                pass


class HuionBleTransport:
    """Adapter implementing huion_notes.session.Transport using dynamic BleDeviceConnection."""

    def __init__(self, mac: str, keepalive: float = 5.0):
        self.conn = BleDeviceConnection(mac)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False
        self._keepalive = keepalive
        self._ka_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        await self.conn.connect()
        await self.conn.setup_signals(self._on_value, self._on_disconnect)
        await self.conn.start_notifications()
        self._ka_task = asyncio.create_task(self._keepalive_loop())

    def _on_value(self, data: bytes) -> None:
        self._queue.put_nowait(bytes(data))

    def _on_disconnect(self) -> None:
        self._closed = True
        self._queue.put_nowait(None)

    async def send(self, frame: bytes) -> None:
        if not await self.conn.write_cmd(frame):
            raise RuntimeError("write failed (device disconnected?)")

    async def recv(self, timeout: Optional[float] = None) -> bytes:
        item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
        if item is None:
            raise RuntimeError("device disconnected")
        return item

    async def _keepalive_loop(self) -> None:
        heartbeat_frame = bytes([0xCD, 0x80, 0x08, 0, 0, 0, 0, 0xED])
        try:
            while not self._closed:
                await asyncio.sleep(self._keepalive)
                await self.conn.write_cmd(heartbeat_frame)
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        self._closed = True
        if self._ka_task:
            self._ka_task.cancel()
        await self.conn.close()
