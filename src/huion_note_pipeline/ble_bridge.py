"""BLE device bridge using dbus_fast / BlueZ and Linux uinput.

Integrates all findings:
  1. Dynamic Bluetooth adapter discovery (hci0, hci1, etc.).
  2. 3-step Live Tablet Handshake (0xC9, 0xC8, 0xCA) + 0xD1 keepalive.
  3. Proper portrait coordinate rotation (out_x = y, out_y = 37400 - x) and pressure unpacking.
  4. Robust challenge-response offline sync (0x81/0x82) with packet recovery.
  5. Virtual digitizer emulation emitting into /dev/uinput via evdev.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import struct
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Callable, Dict, Any, TYPE_CHECKING

from huion.ble import BleDeviceConnection, HuionBleTransport, load_config
from huion.sync_engine import OfflineSyncManager

logger = logging.getLogger("huion_ble_bridge")

try:
    import evdev
    from evdev import UInput, AbsInfo, ecodes
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

if TYPE_CHECKING:
    from .pipeline import SyncPipeline

TABLET_MAX_X = 28200
TABLET_MAX_Y = 37400
TABLET_MAX_PRESSURE = 8191

@dataclass
class Page:
    page_id: str
    raw_data: bytes = field(default_factory=bytes)

@dataclass
class X10Device:
    address: str
    page_count: int = 0
    stored_pages: List[Page] = field(default_factory=list)

@dataclass
class PenPoint:
    x: int
    y: int
    pressure: int
    touch: bool
    button: bool
    in_range: bool


class UInputTabletEmitter:
    """Emulates a native Linux graphic tablet digitizer via /dev/uinput."""

    def __init__(
        self,
        name: str = "Huion Note X10 Pen Digitizer",
        max_x: int = TABLET_MAX_X,
        max_y: int = TABLET_MAX_Y,
        max_pressure: int = TABLET_MAX_PRESSURE,
    ) -> None:
        self.device: Optional[Any] = None
        if HAS_EVDEV:
            cap = {
                ecodes.EV_KEY: [
                    ecodes.BTN_TOUCH,
                    ecodes.BTN_TOOL_PEN,
                    ecodes.BTN_STYLUS,
                    ecodes.BTN_STYLUS2,
                ],
                ecodes.EV_ABS: [
                    (ecodes.ABS_X, AbsInfo(value=0, min=0, max=max_x, fuzz=0, flat=0, resolution=100)),
                    (ecodes.ABS_Y, AbsInfo(value=0, min=0, max=max_y, fuzz=0, flat=0, resolution=100)),
                    (ecodes.ABS_PRESSURE, AbsInfo(value=0, min=0, max=max_pressure, fuzz=0, flat=0, resolution=0)),
                ],
            }
            try:
                self.device = UInput(cap, name=name, version=0x3)
                logger.info("Instantiated /dev/uinput digitizer device.")
            except Exception as e:
                logger.debug(f"/dev/uinput not initialized: {e}")

    def emit(self, point: PenPoint) -> None:
        if not self.device:
            return
        self.device.write(ecodes.EV_ABS, ecodes.ABS_X, point.x)
        self.device.write(ecodes.EV_ABS, ecodes.ABS_Y, point.y)
        self.device.write(ecodes.EV_ABS, ecodes.ABS_PRESSURE, point.pressure)
        self.device.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1 if point.touch else 0)
        self.device.write(ecodes.EV_KEY, ecodes.BTN_TOOL_PEN, 1 if point.in_range else 0)
        self.device.syn()


class DeviceBridge:
    """Manages BLE hardware communication and feeds live points / offline notes into the pipeline."""

    def __init__(self, emit_uinput: bool = False) -> None:
        self.emit_uinput = emit_uinput
        self._emitter = UInputTabletEmitter() if emit_uinput else None
        self._on_pen_point_callbacks: List[Callable[[PenPoint], None]] = []
        self._on_button_callbacks: List[Callable[[], None]] = []
        self._pipeline: Optional[SyncPipeline] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._current_loop: Optional[asyncio.AbstractEventLoop] = None
        self._conn: Optional[BleDeviceConnection] = None
        self._current_conn: Optional[BleDeviceConnection] = None  # active live connection
        self._is_connected: bool = False
        self._last_battery: Optional[int] = None  # cached battery %
        self._sync_queue: Optional[asyncio.Queue] = None

    def get_battery(self) -> Optional[int]:
        """Return the last known battery percentage (0-100), or None if unknown."""
        return self._last_battery

    def is_connected(self) -> bool:
        """Return whether the BLE live telemetry connection is currently active."""
        return self._is_connected

    def attach_pipeline(self, pipeline: SyncPipeline) -> None:
        self._pipeline = pipeline

    def on_pen_point(self, callback: Callable[[PenPoint], None]) -> None:
        self._on_pen_point_callbacks.append(callback)

    def on_hardware_button(self, callback: Callable[[], None]) -> None:
        self._on_button_callbacks.append(callback)

    def _handle_raw_data(self, data: bytes) -> None:
        # If an offline note sync is actively running, route raw data packets to the sync queue
        if self._sync_queue is not None:
            try:
                self._sync_queue.put_nowait(bytes(data))
            except Exception:
                pass
            return

        # Live pen data: 0x55 0x54 ...
        if len(data) >= 13 and data[0] == 0x55 and data[1] == 0x54:
            status = data[2]
            raw_x = data[3] | (data[4] << 8) | (data[9] << 16)
            raw_y = data[5] | (data[6] << 8) | (data[10] << 16)
            pressure = struct.unpack_from("<H", data, 7)[0]

            # Portrait CW orientation:
            out_x = raw_y
            out_y = max(0, 37400 - raw_x)
            touch = (status == 0x81 and pressure > 0)
            in_range = (status != 0x00)

            point = PenPoint(
                x=out_x,
                y=out_y,
                pressure=pressure,
                touch=touch,
                button=False,
                in_range=in_range
            )
            if self._emitter:
                self._emitter.emit(point)
            for cb in self._on_pen_point_callbacks:
                try:
                    cb(point)
                except Exception:
                    pass

        # Hardware button event
        elif (len(data) >= 2 and data[0] == 0xCD and data[1] == 0x8A) or \
             (len(data) >= 3 and data[0] == 0x55 and data[1] == 0x54 and data[2] in (0xE0, 0xE2)):
            for cb in self._on_button_callbacks:
                try:
                    cb()
                except Exception:
                    pass

    def sync_offline_pages(self, output_dir: str, mac: str = "25:6C:BB:8D:19:50", delete_after_export: bool = False,
                           force_vectors: bool = False, progress=None) -> List[Any]:
        """Synchronizes offline notes over the existing active Bluetooth connection without disconnecting."""
        if self._current_loop and self._is_connected and self._current_conn and self._current_loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(
                self._async_sync_active_conn(output_dir, delete_after_export, force_vectors, progress),
                self._current_loop
            )
            try:
                return fut.result(timeout=45.0)
            except TimeoutError as exc:
                fut.cancel()
                raise TimeoutError("Notebook sync timed out. Already saved pages are kept; reconnect and try again.") from exc
        else:
            sync_mgr = OfflineSyncManager(mac=mac, output_dir=output_dir, pin=load_config().get("pin") or None)
            return asyncio.run(sync_mgr.run_sync(delete_after_export=delete_after_export, force_vectors=force_vectors, progress=progress))

    async def _async_sync_active_conn(self, output_dir: str, delete_after_export: bool = False,
                                      force_vectors: bool = False, progress=None) -> List[Any]:
        from huion.sync_engine import (
            START, END, OP_VERIFY_CONNECT, OP_VERIFY_RESULT, OP_REQUEST_OFFLINE_DATA,
            OP_RETURN_OFFLINE_DATA, OP_GET_PAGE_PACKAGE, OP_DELETE_PAGE, OP_CLEAR_CACHE,
            OP_MAX_DATA, OP_SET_DISTANCE, OP_VERIFY_PWD, build_frame, verify_response, decode_packet,
            points_to_strokes, NotePage, HuionDevice, ConnectionState, PageSyncStatus,
            MultiFormatRenderer, next_sync_folder
        )
        import datetime

        conn = self._current_conn
        if not conn:
            raise ConnectionError("No active BLE connection to Huion Note.")

        sync_q: asyncio.Queue = asyncio.Queue()
        self._sync_queue = sync_q

        async def _recv(timeout: float = 3.0) -> bytes:
            return await asyncio.wait_for(sync_q.get(), timeout=timeout)

        try:
            # 1. Challenge-Response Handshake
            authed = False
            for attempt in range(5):
                await conn.write_cmd(build_frame(OP_VERIFY_CONNECT))
                try:
                    while True:
                        data = await _recv(timeout=2.0)
                        if len(data) >= 6 and data[0] == START and data[1] == OP_VERIFY_CONNECT:
                            a, b, c = data[3], data[4], data[5]
                            r1, r2, r3 = verify_response(a, b, c)
                            await conn.write_cmd(build_frame(OP_VERIFY_RESULT, r1, r2, r3, 0))
                            
                            res = await _recv(timeout=2.0)
                            if len(res) >= 4 and res[0] == START and res[1] == OP_VERIFY_RESULT:
                                if res[3] == 1:
                                    authed = True
                                    break
                                pin = load_config().get("pin")
                                if res[3] == 2 and pin and len(pin) == 6:
                                    encoded = [ord(pin[i]) + (104, 117, 105, 111, 110, 35)[i] for i in range(6)]
                                    await conn.write_cmd(build_frame(OP_VERIFY_PWD, 1, *encoded[:3]))
                                    await conn.write_cmd(build_frame(OP_VERIFY_PWD, 2, *encoded[3:]))
                                    authed = True
                                    break
                    if authed:
                        break
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.2)

            if not authed:
                raise RuntimeError("Authentication failed. Make sure notebook folio is in Note Mode.")

            # 2. Distance and limits
            await conn.write_cmd(build_frame(OP_MAX_DATA))
            await asyncio.sleep(0.05)
            await conn.write_cmd(build_frame(OP_SET_DISTANCE, 1, 3, 0, 0))
            await conn.write_cmd(build_frame(OP_SET_DISTANCE, 3, 2, 0, 0))

            # 3. Pull pages
            pages_saved: List[NotePage] = []
            today = datetime.date.today().isoformat()
            renderer = MultiFormatRenderer()
            vector_folder = None

            for page_idx in range(64):
                await conn.write_cmd(bytes([START, OP_REQUEST_OFFLINE_DATA, 0x08, page_idx & 0xFF, (page_idx >> 8) & 0xFF, 0, 0, END]))
                count = 0
                try:
                    while True:
                        data = await _recv(timeout=3.0)
                        if len(data) >= 5 and data[0] == START and data[1] == OP_REQUEST_OFFLINE_DATA and data[2] == 0x05:
                            count = data[3] | (data[4] << 8)
                            break
                except asyncio.TimeoutError:
                    break

                if count == 0:
                    break

                received_packets: Dict[int, bytes] = {}
                retries = 0
                while len(received_packets) < count:
                    try:
                        data = await _recv(timeout=3.0)
                        if len(data) >= 6 and data[0] == START and data[1] in (OP_RETURN_OFFLINE_DATA, OP_GET_PAGE_PACKAGE):
                            seq = data[3] | (data[4] << 8)
                            if 1 <= seq <= count:
                                received_packets[seq] = data
                    except asyncio.TimeoutError:
                        retries += 1
                        if retries > 5:
                            raise TimeoutError("The notebook stopped sending this page. Previously saved pages are kept.")
                        missing = [s for s in range(1, count + 1) if s not in received_packets]
                        if not missing:
                            break
                        for idx in missing[:15]:
                            await conn.write_cmd(bytes([START, OP_GET_PAGE_PACKAGE, 0x08, page_idx & 0xFF, (page_idx >> 8) & 0xFF, idx & 0xFF, (idx >> 8) & 0xFF, END]))
                        await asyncio.sleep(0.2)

                ordered = [received_packets[s] for s in sorted(received_packets)]
                all_points: List[Any] = []
                for pkt in ordered:
                    all_points.extend(decode_packet(pkt))

                strokes = points_to_strokes(all_points)
                page_num = len(pages_saved) + 1

                is_raw_png = not force_vectors and ("Raw PNGs" in output_dir or output_dir.rstrip("/").endswith("Raw PNGs"))
                if is_raw_png:
                    folder = output_dir
                    os.makedirs(folder, exist_ok=True)
                    existing = set(os.listdir(folder)) if os.path.exists(folder) else set()
                    idx = 1
                    while f"{today}_{idx:02d}.png" in existing or f"{today}_{idx:02d}.png" in getattr(self, "_saved_sync_names", set()):
                        idx += 1
                    base_name = f"{today}_{idx:02d}"
                    if not hasattr(self, "_saved_sync_names"):
                        self._saved_sync_names = set()
                    self._saved_sync_names.add(f"{base_name}.png")
                    artifacts = renderer.export_all(strokes, folder, base_name, png_only=True)
                else:
                    if vector_folder is None:
                        vector_folder = next_sync_folder(output_dir, today)
                    folder = vector_folder
                    base_name = f"{today}_{page_num:02d}"
                    artifacts = renderer.export_all(strokes, folder, base_name)

                page = NotePage(
                    device=HuionDevice(mac_address=conn.mac, connection_state=ConnectionState.CONNECTED),
                    date_str=today,
                    page_number=page_num,
                    stroke_count=len(strokes),
                    status=PageSyncStatus.SAVED,
                    artifacts=artifacts
                )
                pages_saved.append(page)
                if progress:
                    progress(len(pages_saved), 0)

                if delete_after_export:
                    await conn.write_cmd(bytes([START, OP_DELETE_PAGE, 0x08, page_idx & 0xFF, (page_idx >> 8) & 0xFF, 0, 0, END]))
                    await asyncio.sleep(0.1)

            if delete_after_export and pages_saved:
                await conn.write_cmd(build_frame(OP_CLEAR_CACHE))

            return pages_saved

        finally:
            self._sync_queue = None
            # Return seamlessly to live tablet mode on the same socket
            try:
                await conn.enter_live_tablet_mode()
            except Exception:
                pass

    def stream_pen_input(self, device: Any, mode: str = "tablet") -> None:
        addr = getattr(device, "address", str(device))
        if addr == "HUION-NOTE-X10":
            return

        if self._stream_thread and self._stream_thread.is_alive():
            return

        self._stop_event.clear()

        async def _ble_worker():
            while not self._stop_event.is_set():
                conn = BleDeviceConnection(mac=addr)
                self._conn = conn
                self._current_conn = conn
                disconnected_event = asyncio.Event()
                battery_tick = 0

                try:
                    await conn.connect()
                    self._is_connected = True
                    await conn.setup_signals(self._handle_raw_data, lambda: disconnected_event.set())
                    await conn.enter_live_tablet_mode()

                    # Read battery immediately after connect
                    try:
                        batt = await conn.read_battery()
                        if batt is not None:
                            self._last_battery = batt
                    except Exception:
                        pass

                    while not self._stop_event.is_set() and not disconnected_event.is_set():
                        await asyncio.sleep(0.1)
                        battery_tick += 1
                        # Re-poll battery every 30 s (300 × 0.1 s)
                        if battery_tick >= 300:
                            battery_tick = 0
                            try:
                                batt = await conn.read_battery()
                                if batt is not None:
                                    self._last_battery = batt
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug(f"BLE bridge worker notice: {e}")
                finally:
                    self._is_connected = False
                    self._current_conn = None
                    try:
                        await conn.close()
                    except Exception:
                        pass

                if not self._stop_event.is_set():
                    await asyncio.sleep(1.0)

        def _runner():
            loop = asyncio.new_event_loop()
            self._current_loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_ble_worker())
            finally:
                loop.close()

        self._stream_thread = threading.Thread(target=_runner, daemon=True)
        self._stream_thread.start()

    def stop_pen_input(self) -> None:
        """Cleanly signals the BLE thread to shut down and awaits disconnection."""
        self._stop_event.set()
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2.5)
        self._stream_thread = None
        self._current_loop = None

    def retry_connection(self, mac: str = "25:6C:BB:8D:19:50") -> None:
        """Forces an immediate, clean reconnection cycle."""
        self._is_connected = False
        self._last_battery = None
        self.stop_pen_input()
        self.stream_pen_input(mac, mode="tablet")

    def pull(self, device: X10Device) -> List[Page]:
        """Pull stored offline notes using the robust OfflineSyncManager."""
        was_streaming = bool(self._stream_thread and self._stream_thread.is_alive())
        if was_streaming:
            self.stop_pen_input()

        import time
        time.sleep(0.5)

        out_dir = getattr(self._pipeline.config, "output_directory", "./notes_output") if self._pipeline else "./notes_output"
        sync_mgr = OfflineSyncManager(mac=device.address, output_dir=out_dir)

        try:
            pages = asyncio.run(sync_mgr.run_sync(delete_after_export=False))
            device_pages = []
            for p in pages:
                svg_path = os.path.join(p.artifacts.folder_path, p.artifacts.svg_filename)
                raw_bytes = Path(svg_path).read_bytes() if os.path.exists(svg_path) else b""
                device_pages.append(Page(page_id=f"{p.date_str}_{p.page_number:02d}", raw_data=raw_bytes))
            
            device.stored_pages = device_pages
            device.page_count = len(device_pages)
            return device_pages
        except Exception as e:
            logger.warning(f"Error during offline page pull: {e}")
            return []
        finally:
            if was_streaming:
                self.stream_pen_input(device)

    def clear_synced_pages(self, device: X10Device, synced_page_ids: Set[str]) -> None:
        device.stored_pages = [p for p in device.stored_pages if p.page_id not in synced_page_ids]
        device.page_count = len(device.stored_pages)

    def clear_all_pages(self, device: X10Device) -> None:
        out_dir = getattr(self._pipeline.config, "output_directory", "./notes_output") if self._pipeline else "./notes_output"
        self.sync_offline_pages(out_dir, device.address, delete_after_export=True)
        device.stored_pages.clear()
        device.page_count = 0


async def register_bluez_agent() -> None:
    pass
