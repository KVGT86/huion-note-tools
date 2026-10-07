import asyncio
import datetime
import hashlib
import logging
import os
import struct
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Set

from .ble import BleDeviceConnection, HuionBleTransport, load_config
from .models import (
    HuionDevice,
    ConnectionState,
    NotePage,
    PageSyncStatus,
    SyncLedger,
    SyncedPageRecord,
    Stroke,
    PenPoint,
    PenType,
    ExportArtifacts
)
from .renderer import MultiFormatRenderer

log = logging.getLogger("huion.sync")


def next_sync_folder(output_dir: str, date: str) -> str:
    """Reserve a new sync set without replacing an earlier import."""
    day = os.path.join(output_dir, date)
    os.makedirs(day, exist_ok=True)
    index = 1
    while True:
        folder = os.path.join(day, f"set_{index:02d}")
        try:
            os.mkdir(folder)
            return folder
        except FileExistsError:
            index += 1

# Protocol Constants
START = 0xCD
END   = 0xED

OP_HEARTBEAT            = 0x80
OP_VERIFY_CONNECT       = 0x81
OP_VERIFY_RESULT        = 0x82
OP_VERIFY_PWD           = 0x83
OP_REQUEST_OFFLINE_DATA = 0x86
OP_RETURN_OFFLINE_DATA  = 0x87
OP_GET_PAGE_PACKAGE     = 0x88
OP_NEXT_PAGE            = 0x8A
OP_DELETE_PAGE          = 0x8B
OP_CLEAR_CACHE          = 0x8C
OP_MAX_DATA             = 0x95
OP_SET_DISTANCE         = 0x96


def build_frame(op: int, a: int = 0, b: int = 0, c: int = 0, d: int = 0) -> bytes:
    return bytes([START, op, 0x08, a & 0xFF, b & 0xFF, c & 0xFF, d & 0xFF, END])

def verify_response(a: int, b: int, c: int) -> Tuple[int, int, int]:
    r1 = ((a + b) << 2) % 255
    r2 = ((b + c) << 2) % 255
    r3 = ((c + 10) << 2) % 255
    return r1, r2, r3

def decode_point(rec: bytes) -> PenPoint:
    x = rec[0] | (rec[1] << 8)
    y = rec[2] | (rec[3] << 8)
    press = rec[4] | ((rec[5] & 0x1F) << 8)
    return PenPoint(x=x, y=y, pressure=press)

def decode_packet(pkt: bytes) -> List[PenPoint]:
    n = (len(pkt) - 5) // 6
    points = []
    for k in range(n):
        chunk = pkt[5 + k * 6 : 5 + k * 6 + 6]
        if len(chunk) == 6:
            points.append(decode_point(chunk))
    return points

def points_to_strokes(points: List[PenPoint]) -> List[Stroke]:
    strokes: List[Stroke] = []
    curr: List[PenPoint] = []
    for p in points:
        if p.pressure > 0:
            curr.append(p)
        else:
            if len(curr) > 1:
                strokes.append(Stroke(points=list(curr), pen_type=PenType.BALLPOINT))
            curr = []
    if len(curr) > 1:
        strokes.append(Stroke(points=list(curr), pen_type=PenType.BALLPOINT))
    return strokes


def verify_export_artifacts(artifacts: ExportArtifacts) -> bool:
    """Confirm every renderer-declared artifact exists and contains data."""
    names = [name for name in (artifacts.svg_filename, artifacts.png_filename, artifacts.json_filename) if name]
    return bool(names) and all(
        (Path(artifacts.folder_path) / name).is_file() and (Path(artifacts.folder_path) / name).stat().st_size > 0
        for name in names
    )


class SyncEngine:
    def __init__(self, base_output_dir: str = "./notes-out"):
        self.base_output_dir = base_output_dir
        self.renderer = MultiFormatRenderer()

    def discover_pages_to_sync(self, device: HuionDevice, ledger: SyncLedger, date_str: str) -> List[NotePage]:
        if device.connection_state != ConnectionState.CONNECTED:
            raise ValueError("Device must be connected to discover offline pages.")
        if device.stored_page_count <= 0:
            return []

        pages = []
        for i in range(1, device.stored_page_count + 1):
            page_num = ledger.total_synced_pages + i
            page = NotePage(
                device=device,
                date_str=date_str,
                page_number=page_num,
                stroke_count=0,
                status=PageSyncStatus.DISCOVERED,
                artifacts=None
            )
            pages.append(page)
        return pages

    def transfer_and_export_page(
        self,
        page: NotePage,
        ledger: SyncLedger,
        strokes: List[Stroke],
        set_number: int = 1,
        png_only: bool = False
    ) -> SyncedPageRecord:
        page.transition_status(PageSyncStatus.TRANSFERRING)
        page.stroke_count = len(strokes)

        folder = os.path.join(self.base_output_dir, page.date_str, f"set_{set_number:02d}")
        base_name = f"{page.date_str}_{page.page_number:02d}"

        artifacts = self.renderer.export_all(strokes, folder, base_name, png_only=png_only)
        
        target_file = artifacts.json_filename or artifacts.png_filename or artifacts.svg_filename
        check_path = os.path.join(folder, target_file) if target_file else ""
        if check_path and os.path.exists(check_path):
            with open(check_path, "rb") as f:
                checksum = hashlib.sha256(f.read()).hexdigest()
        else:
            checksum = ""

        page.artifacts = artifacts
        page.transition_status(PageSyncStatus.SAVED)

        record = SyncedPageRecord(
            date_str=page.date_str,
            page_number=page.page_number,
            checksum=checksum,
            artifacts=artifacts
        )
        ledger.add_record(record)
        return record

    def purge_device_storage(self, device: HuionDevice) -> None:
        if device.connection_state != ConnectionState.CONNECTED:
            raise ValueError("Device must be connected to purge storage.")
        device.stored_page_count = 0


class OfflineSyncManager:
    """Robust, self-healing offline note synchronizer for Huion Note X10."""

    def __init__(self, mac: str, output_dir: str, pin: Optional[str] = None):
        self.mac = mac
        self.output_dir = output_dir
        self.pin = pin
        self.renderer = MultiFormatRenderer()
        self.transport = HuionBleTransport(mac=mac)
        self.storage_page_count: Optional[int] = None

    async def run_sync(self, delete_after_export: bool = False, png_only: bool = False,
                       force_vectors: bool = False, progress=None) -> List[NotePage]:
        log.info(f"Connecting to Huion Note ({self.mac}) for offline sync...")
        self.storage_page_count = None
        self._storage_scan_complete = True
        await self.transport.connect()

        try:
            # 1. Challenge-Response Handshake with retry
            await self._authenticate()

            # 2. Query limits and distance
            await self.transport.send(build_frame(OP_MAX_DATA))
            await asyncio.sleep(0.05)
            await self.transport.send(build_frame(OP_SET_DISTANCE, 1, 3, 0, 0))
            await self.transport.send(build_frame(OP_SET_DISTANCE, 3, 2, 0, 0))

            # 3. Pull pages sequentially until device reports empty
            pages_saved: List[NotePage] = []
            today = datetime.date.today().isoformat()
            saved_names: Set[str] = set()
            vector_folder = None
            occupied_slots = 0

            for page_idx in range(64):
                count, raw_packets = await self._fetch_page(page_idx)
                if count > 0:
                    occupied_slots += 1
                if count == 0 or not raw_packets:
                    continue

                # Decode points and reconstruct vector strokes
                all_points: List[PenPoint] = []
                for pkt in raw_packets:
                    all_points.extend(decode_packet(pkt))

                strokes = points_to_strokes(all_points)
                if not strokes:
                    continue

                page_num = len(pages_saved) + 1

                is_raw_png = not force_vectors and (png_only or "Raw PNGs" in self.output_dir or self.output_dir.rstrip("/").endswith("Raw PNGs"))
                if is_raw_png:
                    folder = self.output_dir
                    os.makedirs(folder, exist_ok=True)
                    existing = set(os.listdir(folder)) if os.path.exists(folder) else set()
                    idx = 1
                    while f"{today}_{idx:02d}.png" in existing or f"{today}_{idx:02d}.png" in saved_names:
                        idx += 1
                    base_name = f"{today}_{idx:02d}"
                    saved_names.add(f"{base_name}.png")
                    artifacts = self.renderer.export_all(strokes, folder, base_name, png_only=True)
                else:
                    if vector_folder is None:
                        vector_folder = next_sync_folder(self.output_dir, today)
                    folder = vector_folder
                    base_name = f"{today}_{page_num:02d}"
                    artifacts = self.renderer.export_all(strokes, folder, base_name, png_only=png_only)

                page = NotePage(
                    device=HuionDevice(mac_address=self.mac, connection_state=ConnectionState.CONNECTED),
                    date_str=today,
                    page_number=page_num,
                    stroke_count=len(strokes),
                    status=PageSyncStatus.SAVED,
                    artifacts=artifacts
                )
                pages_saved.append(page)
                if progress:
                    progress(len(pages_saved), 0)
                saved_target = artifacts.png_filename if png_only else (artifacts.svg_filename or artifacts.png_filename)
                log.info(f"Saved Page {page_num} ({len(strokes)} strokes) -> {artifacts.folder_path}/{saved_target}")

                if delete_after_export:
                    if not verify_export_artifacts(artifacts):
                        raise RuntimeError("A transferred page could not be verified locally. It remains on the notebook.")
                    await self.transport.send(bytes([START, OP_DELETE_PAGE, 0x08, page_idx & 0xFF, (page_idx >> 8) & 0xFF, 0, 0, END]))
                    await asyncio.sleep(0.1)

            if delete_after_export and pages_saved:
                await self.transport.send(build_frame(OP_CLEAR_CACHE))
                log.info(f"Purged {len(pages_saved)} exported page(s) from device memory.")

            if self._storage_scan_complete and not delete_after_export:
                self.storage_page_count = occupied_slots
            return pages_saved

        finally:
            await self.transport.close()

    async def probe_stored_page_count(self) -> int:
        """Probe offline flash storage slots to count how many pages are stored in memory."""
        await self.transport.connect()
        try:
            await self._authenticate()
            await self.transport.send(build_frame(OP_MAX_DATA))
            await asyncio.sleep(0.05)

            stored_count = 0
            for page_idx in range(64):
                await self.transport.send(bytes([START, OP_REQUEST_OFFLINE_DATA, 0x08, page_idx & 0xFF, (page_idx >> 8) & 0xFF, 0, 0, END]))
                count = 0
                try:
                    while True:
                        data = await self.transport.recv(timeout=0.2)
                        if len(data) >= 5 and data[0] == START and data[1] == OP_REQUEST_OFFLINE_DATA and data[2] == 0x05:
                            count = data[3] | (data[4] << 8)
                            break
                except asyncio.TimeoutError:
                    count = 0

                if count > 0:
                    stored_count += 1

            return stored_count
        finally:
            await self.transport.close()

    async def _authenticate(self) -> None:
        """Pokes device with VERIFY_CONNECT and computes challenge response."""
        for attempt in range(5):
            await self.transport.send(build_frame(OP_VERIFY_CONNECT))
            try:
                while True:
                    data = await self.transport.recv(timeout=2.0)
                    if len(data) >= 6 and data[0] == START and data[1] == OP_VERIFY_CONNECT:
                        a, b, c = data[3], data[4], data[5]
                        r1, r2, r3 = verify_response(a, b, c)
                        await self.transport.send(build_frame(OP_VERIFY_RESULT, r1, r2, r3, 0))
                        
                        res = await self.transport.recv(timeout=2.0)
                        if len(res) >= 4 and res[0] == START and res[1] == OP_VERIFY_RESULT:
                            if res[3] == 1:
                                log.info("Authentication successful.")
                                return
                            elif res[3] == 2 and self.pin:
                                e = [ord(self.pin[i]) + (104, 117, 105, 111, 110, 35)[i] for i in range(6)]
                                await self.transport.send(build_frame(OP_VERIFY_PWD, 0x01, e[0], e[1], e[2]))
                                await self.transport.send(build_frame(OP_VERIFY_PWD, 0x02, e[3], e[4], e[5]))
                                return
            except asyncio.TimeoutError:
                log.debug(f"Auth attempt {attempt + 1} timed out, retrying poke...")
                await asyncio.sleep(0.3)

        raise RuntimeError("Device authentication timed out. Ensure the Huion Note is in Note Mode (folio closed).")

    async def _fetch_page(self, page_idx: int) -> Tuple[int, List[bytes]]:
        await self.transport.send(bytes([START, OP_REQUEST_OFFLINE_DATA, 0x08, page_idx & 0xFF, (page_idx >> 8) & 0xFF, 0, 0, END]))
        
        count = 0
        try:
            while True:
                data = await self.transport.recv(timeout=0.3)
                if len(data) >= 5 and data[0] == START and data[1] == OP_REQUEST_OFFLINE_DATA and data[2] == 0x05:
                    count = data[3] | (data[4] << 8)
                    break
        except asyncio.TimeoutError:
            self._storage_scan_complete = False
            return 0, []

        if count == 0:
            return 0, []

        log.info(f"Page slot {page_idx + 1}: Downloading {count} vector data packets...")
        received_packets: Dict[int, bytes] = {}
        retries = 0

        while len(received_packets) < count and retries < 5:
            try:
                data = await self.transport.recv(timeout=2.0)
                if len(data) >= 6 and data[0] == START and data[1] in (OP_RETURN_OFFLINE_DATA, OP_GET_PAGE_PACKAGE):
                    seq = data[3] | (data[4] << 8)
                    if 1 <= seq <= count:
                        received_packets[seq] = data
            except asyncio.TimeoutError:
                retries += 1
                missing = [s for s in range(1, count + 1) if s not in received_packets]
                if not missing:
                    break
                for idx in missing[:15]:
                    await self.transport.send(bytes([START, OP_GET_PAGE_PACKAGE, 0x08, page_idx & 0xFF, (page_idx >> 8) & 0xFF, idx & 0xFF, (idx >> 8) & 0xFF, END]))
                await asyncio.sleep(0.1)

        ordered = [received_packets[s] for s in sorted(received_packets)]
        if len(ordered) != count:
            self._storage_scan_complete = False
        return count, ordered
