#!/usr/bin/env python3
"""Huion Note X10 Background Auto-Sync & AI Transcription Daemon."""
import asyncio
import os
import sys
import logging
import subprocess

from huion.ble import BleDeviceConnection, load_config
from huion.sync_engine import OfflineSyncManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("huion.autosync")

async def daemon_loop():
    cfg = load_config()
    out_dir = os.path.expanduser("~/Documents/CYC-Caleb/00 Inbox/Raw PNGs")
    mac = cfg.get("mac_address")
    transcribe_script = os.path.expanduser("~/Documents/CYC-Caleb/process_huion_notes.py")

    log.info(f"Huion Note Autosync Daemon started. Watching for tablet {mac} -> {out_dir}")

    while True:
        try:
            sync_mgr = OfflineSyncManager(mac=mac, output_dir=out_dir, pin=cfg.get("pin") or None)
            pages = await sync_mgr.run_sync(delete_after_export=True, png_only=True)
            if pages:
                log.info(f"🎉 Autosynced {len(pages)} note(s) directly to {out_dir}")
                if os.path.exists(transcribe_script):
                    log.info("🤖 Triggering automated AI Studio transcription...")
                    subprocess.run([sys.executable, transcribe_script], check=False)
        except Exception as e:
            log.debug(f"Autosync poll note: {e}")

        await asyncio.sleep(4.0)

if __name__ == "__main__":
    asyncio.run(daemon_loop())
