from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set
import datetime

# --- Enumerations ---

class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CONNECTION_FAILED = "connection_failed"

class DeviceMode(str, Enum):
    NOTE_OFFLINE = "note_offline"
    NOTE_LIVE = "note_live"
    DIGITIZER_TABLET = "digitizer_tablet"

class PenType(str, Enum):
    BALLPOINT = "ballpoint"
    STYLUS = "stylus"

class PageSyncStatus(str, Enum):
    DISCOVERED = "discovered"
    TRANSFERRING = "transferring"
    SAVED = "saved"
    FAILED = "failed"


# --- Value Types ---

@dataclass(frozen=True)
class PenPoint:
    x: int
    y: int
    pressure: int
    tilt_x: int = 0
    tilt_y: int = 0

@dataclass(frozen=True)
class Stroke:
    points: List[PenPoint]
    pen_type: PenType = PenType.BALLPOINT

@dataclass(frozen=True)
class ExportArtifacts:
    folder_path: str
    svg_filename: Optional[str] = None
    png_filename: Optional[str] = None
    json_filename: Optional[str] = None


# --- Entities ---

@dataclass
class LaptopUser:
    username: str
    is_active: bool = True

@dataclass
class HuionDevice:
    mac_address: str
    is_paired: bool = False
    battery_level: int = 100
    stored_page_count: int = 0
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    current_mode: DeviceMode = DeviceMode.NOTE_OFFLINE

    @property
    def has_low_battery(self) -> bool:
        return self.battery_level < 15

    @property
    def has_stored_notes(self) -> bool:
        return self.stored_page_count > 0

    @property
    def is_ready_to_sync(self) -> bool:
        return self.connection_state == ConnectionState.CONNECTED and self.stored_page_count > 0

    def transition_connection(self, target: ConnectionState) -> None:
        valid_transitions = {
            ConnectionState.DISCONNECTED: {ConnectionState.SCANNING},
            ConnectionState.SCANNING: {ConnectionState.CONNECTING},
            ConnectionState.CONNECTING: {ConnectionState.CONNECTED, ConnectionState.CONNECTION_FAILED},
            ConnectionState.CONNECTED: {ConnectionState.DISCONNECTED},
            ConnectionState.CONNECTION_FAILED: {ConnectionState.DISCONNECTED},
        }
        if target not in valid_transitions.get(self.connection_state, set()):
            raise ValueError(f"Invalid connection transition from {self.connection_state} to {target}")
        self.connection_state = target

    def transition_mode(self, target: DeviceMode) -> None:
        valid_transitions = {
            DeviceMode.NOTE_OFFLINE: {DeviceMode.NOTE_LIVE, DeviceMode.DIGITIZER_TABLET},
            DeviceMode.NOTE_LIVE: {DeviceMode.NOTE_OFFLINE},
            DeviceMode.DIGITIZER_TABLET: {DeviceMode.NOTE_OFFLINE},
        }
        if target not in valid_transitions.get(self.current_mode, set()):
            raise ValueError(f"Invalid mode transition from {self.current_mode} to {target}")
        self.current_mode = target

    def check_invariants(self, max_pages: int = 50) -> None:
        if not (0 <= self.battery_level <= 100):
            raise AssertionError(f"BatteryLevelWithinBounds violated: {self.battery_level}")
        if not (0 <= self.stored_page_count <= max_pages):
            raise AssertionError(f"PageStorageWithinCapacity violated: {self.stored_page_count}")


@dataclass
class SyncedPageRecord:
    date_str: str
    page_number: int
    checksum: str
    artifacts: ExportArtifacts
    synced_at: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class SyncLedger:
    device: HuionDevice
    total_synced_pages: int = 0
    last_synced_at: Optional[datetime.datetime] = None
    records: List[SyncedPageRecord] = field(default_factory=list)

    def add_record(self, record: SyncedPageRecord) -> None:
        # Invariant: UniquePageNumbersPerDate
        for existing in self.records:
            if existing.date_str == record.date_str and existing.page_number == record.page_number:
                raise AssertionError(f"UniquePageNumbersPerDate violated for {record.date_str}_{record.page_number}")
        self.records.append(record)
        self.total_synced_pages += 1
        self.last_synced_at = record.synced_at


@dataclass
class NotePage:
    device: HuionDevice
    date_str: str
    page_number: int
    stroke_count: int = 0
    status: PageSyncStatus = PageSyncStatus.DISCOVERED
    artifacts: Optional[ExportArtifacts] = None

    def transition_status(self, target: PageSyncStatus) -> None:
        valid_transitions = {
            PageSyncStatus.DISCOVERED: {PageSyncStatus.TRANSFERRING},
            PageSyncStatus.TRANSFERRING: {PageSyncStatus.SAVED, PageSyncStatus.FAILED},
            PageSyncStatus.FAILED: {PageSyncStatus.TRANSFERRING},
            PageSyncStatus.SAVED: set(),  # Terminal
        }
        if target not in valid_transitions.get(self.status, set()):
            raise ValueError(f"Invalid status transition from {self.status} to {target}")
        self.status = target


@dataclass
class LiveVisualizerSession:
    device: HuionDevice
    session_date: str
    current_page_number: int = 1
    active: bool = True
    total_strokes_drawn: int = 0
