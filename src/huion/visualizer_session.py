from typing import Optional
from .models import HuionDevice, DeviceMode, ConnectionState, LiveVisualizerSession, Stroke

class LiveVisualizerManager:
    def __init__(self, device: HuionDevice):
        self.device = device
        self.session: Optional[LiveVisualizerSession] = None

    def start_session(self, session_date: str) -> LiveVisualizerSession:
        if self.device.connection_state != ConnectionState.CONNECTED:
            raise ValueError("Device must be connected to start live visualizer.")
        if self.device.current_mode != DeviceMode.NOTE_OFFLINE:
            raise ValueError("Device must be in note_offline mode to start live visualizer.")

        self.device.transition_mode(DeviceMode.NOTE_LIVE)
        self.session = LiveVisualizerSession(
            device=self.device,
            session_date=session_date,
            current_page_number=1,
            active=True,
            total_strokes_drawn=0
        )
        return self.session

    def record_stroke(self, stroke: Stroke) -> None:
        if not self.session or not self.session.active:
            raise ValueError("No active visualizer session.")
        self.session.total_strokes_drawn += 1

    def handle_hardware_button_pressed(self) -> int:
        if not self.session or not self.session.active:
            raise ValueError("No active visualizer session.")
        self.session.current_page_number += 1
        self.session.total_strokes_drawn = 0
        return self.session.current_page_number

    def stop_session(self) -> None:
        if not self.session or not self.session.active:
            raise ValueError("No active visualizer session.")
        if self.device.current_mode != DeviceMode.NOTE_LIVE:
            raise ValueError("Device must be in note_live mode.")
        
        self.session.active = False
        self.device.transition_mode(DeviceMode.NOTE_OFFLINE)
