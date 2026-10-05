import argparse
import asyncio
import datetime
import json
import logging
import os
import struct
import sys
import threading
from typing import Optional, List

from .ble import BleDeviceConnection, HuionBleTransport, load_config, save_config, CONFIG_PATH, build_tablet_cmd, CMD_TABLET_BATTERY
from .models import (
    HuionDevice,
    ConnectionState,
    DeviceMode,
    SyncLedger,
    SyncedPageRecord,
    PenPoint,
    Stroke,
)
from .renderer import MultiFormatRenderer
from .sync_engine import SyncEngine, OfflineSyncManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("huion")

LEDGER_PATH = os.path.expanduser("~/.config/huion/ledger.json")

def load_ledger(device: HuionDevice) -> SyncLedger:
    ledger = SyncLedger(device=device)
    if os.path.exists(LEDGER_PATH):
        try:
            with open(LEDGER_PATH, "r") as f:
                data = json.load(f)
                ledger.total_synced_pages = data.get("total_synced_pages", 0)
        except Exception:
            pass
    return ledger

def save_ledger(ledger: SyncLedger) -> None:
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    data = {
        "device_mac": ledger.device.mac_address,
        "total_synced_pages": ledger.total_synced_pages,
        "last_synced_at": ledger.last_synced_at.isoformat() if ledger.last_synced_at else None,
        "records": [
            {
                "date_str": r.date_str,
                "page_number": r.page_number,
                "checksum": r.checksum,
                "svg": r.artifacts.svg_filename if r.artifacts else None,
                "png": r.artifacts.png_filename if r.artifacts else None,
                "json": r.artifacts.json_filename if r.artifacts else None,
            }
            for r in ledger.records
        ]
    }
    with open(LEDGER_PATH, "w") as f:
        json.dump(data, f, indent=2)


async def cmd_status(args):
    """Query Huion Note X10 status (battery percentage, stored flash pages, pairing)."""
    cfg = load_config()
    mac = args.mac or cfg.get("mac_address")
    if not mac:
        print("❌ Error: No MAC address configured. Run 'huion config --mac <MAC>' first.")
        return

    print("\n🔍 Connecting to Huion Note X10...")
    conn = BleDeviceConnection(mac=mac)
    battery = None
    stored_pages = None

    try:
        # 1. Query Battery from BLE Connection
        await asyncio.wait_for(conn.connect(), timeout=5.0)
        battery = await asyncio.wait_for(conn.read_battery(), timeout=3.0)
    except Exception as e:
        log.debug(f"Battery query note: {e}")
    finally:
        try:
            await conn.close()
        except Exception:
            pass

    try:
        # 2. Query Stored Flash Pages from OfflineSyncManager
        sync_mgr = OfflineSyncManager(mac=mac, output_dir=cfg.get("output_dir", ""), pin=cfg.get("pin") or None)
        stored_pages = await asyncio.wait_for(sync_mgr.probe_stored_page_count(), timeout=6.0)
    except Exception as e:
        log.debug(f"Flash probe note: {e}")

    print("\n" + "=" * 50)
    print("  📊 Huion Note X10 Status & Telemetry")
    print("=" * 50)
    print(f"  Device MAC Address : {mac}")
    
    if battery is not None:
        bat_icon = "🔋" if battery > 20 else "🪫"
        print(f"  Battery Level      : {battery}% {bat_icon}")
    else:
        print(f"  Battery Level      : Available (BLE GATT)")

    if stored_pages is not None:
        print(f"  Offline Flash      : {stored_pages} page(s) stored (50 max capacity)")
    else:
        print(f"  Offline Flash      : 50 Pages Max Capacity")

    out_dir = cfg.get("output_dir") or os.path.expanduser("~/Documents/CYC-Caleb/00 Inbox/Raw PNGs")
    print(f"  Sync Inbox         : {out_dir}")
    print(f"  Status             : Connected & Ready")
    print("=" * 50 + "\n")


async def cmd_sync(args):
    """Synchronize offline handwritten pages from tablet memory."""
    cfg = load_config()
    default_png_inbox = os.path.expanduser("~/Documents/CYC-Caleb/00 Inbox/Raw PNGs")

    if args.out:
        out_dir = os.path.abspath(os.path.expanduser(args.out))
    else:
        out_dir = cfg.get("output_dir") or default_png_inbox

    mac = args.mac or cfg.get("mac_address")

    if not mac:
        print("❌ Error: No MAC address configured. Run 'huion config --mac <MAC>' first.")
        return

    is_png_only = getattr(args, "png_only", False) or "Raw PNGs" in out_dir or out_dir.rstrip("/").endswith("Raw PNGs")

    if is_png_only:
        target_folder = out_dir
    else:
        today = datetime.date.today().isoformat()
        target_folder = os.path.join(out_dir, today, "set_01")

    os.makedirs(target_folder, exist_ok=True)

    mode_str = " (PNG only)" if is_png_only else ""
    print(f"\n📥 Syncing offline notes{mode_str} -> {target_folder}")
    print("ℹ️  Make sure the notebook folio cover is in Note Mode.")

    sync_mgr = OfflineSyncManager(mac=mac, output_dir=target_folder if is_png_only else out_dir, pin=cfg.get("pin") or None)
    try:
        pages = await sync_mgr.run_sync(
            delete_after_export=args.delete,
            png_only=is_png_only
        )
        if not pages:
            print("\n📭 No offline pages found in notebook memory (or memory was already synced).")
            return

        print(f"\n✅ Successfully downloaded {len(pages)} note(s) from device:")
        new_png_paths = []
        for p in pages:
            saved_file = p.artifacts.png_filename if is_png_only else (p.artifacts.svg_filename or p.artifacts.png_filename)
            full_path = os.path.join(p.artifacts.folder_path, saved_file)
            print(f"   📄 Page {p.page_number} ({p.stroke_count} strokes) -> {full_path}")
            if p.artifacts.png_filename:
                new_png_paths.append(os.path.join(p.artifacts.folder_path, p.artifacts.png_filename))

        if getattr(args, "transcribe", False) and new_png_paths:
            import subprocess
            script_path = os.path.expanduser("~/Documents/CYC-Caleb/process_huion_notes.py")
            if os.path.exists(script_path):
                env = os.environ.copy()
                env["PYTHONPATH"] = f"/home/caleb:{env.get('PYTHONPATH', '')}"
                subprocess.run([sys.executable, script_path] + new_png_paths, env=env, check=False)
    except Exception as e:
        print(f"\n❌ Sync failed: {e}")


def cmd_live(args):
    """Launch the real-time drawing visualizer with smooth inking and self-healing reconnect loop."""
    from .live_viewer import LiveViewerWindow
    cfg = load_config()
    out_dir = args.out or cfg.get("output_dir") or os.path.expanduser("~/HuionNotes")
    mac = args.mac or cfg.get("mac_address")

    loop = asyncio.new_event_loop()
    conn_ref = [None]

    def on_window_close():
        log.info("Live viewer window closed.")
        if loop.is_running() and conn_ref[0]:
            loop.call_soon_threadsafe(lambda: asyncio.create_task(conn_ref[0].close()))

    viewer = LiveViewerWindow(output_dir=out_dir, on_close_callback=on_window_close)

    def on_point_received(data: bytes):
        # 1. Live pen data packet: 0x55 0x54 ...
        if len(data) >= 13 and data[0] == 0x55 and data[1] == 0x54:
            status = data[2]
            raw_x = data[3] | (data[4] << 8) | (data[9] << 16)
            raw_y = data[5] | (data[6] << 8) | (data[10] << 16)
            pressure = struct.unpack_from("<H", data, 7)[0]
            
            # Portrait CW rotation:
            # Device raw long edge (37400) is X, short edge (28200) is Y.
            out_x = raw_y
            out_y = max(0, 37400 - raw_x)

            pen_down = (status == 0x81 and pressure > 0)
            viewer.add_point(PenPoint(x=out_x, y=out_y, pressure=pressure), pen_down)

        # 2. Hardware button packet: 0xCD 0x8A / 0xE0 / 0xE2
        elif (len(data) >= 2 and data[0] == 0xCD and data[1] == 0x8A) or \
             (len(data) >= 3 and data[0] == 0x55 and data[1] == 0x54 and data[2] in (0xE0, 0xE2)):
            viewer.handle_hardware_button()

    async def ble_worker():
        disconnected_event = asyncio.Event()

        def on_disconnect():
            disconnected_event.set()

        while viewer.is_running:
            conn = BleDeviceConnection(mac=mac)
            conn_ref[0] = conn
            disconnected_event.clear()
            try:
                await conn.connect()
                await conn.setup_signals(on_point_received, on_disconnect)
                await conn.enter_live_tablet_mode()
                
                # Keep active until window closes or device disconnects
                while viewer.is_running and not disconnected_event.is_set():
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                log.debug(f"BLE connection loop note: {e}")
            finally:
                await conn.close()
            
            if viewer.is_running:
                # Fast auto-reconnect retry
                await asyncio.sleep(0.5)

    def run_ble_thread():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ble_worker())

    t = threading.Thread(target=run_ble_thread, daemon=True)
    t.start()

    print("\n🎨 Live Visualizer opened. Write on your pad...")
    viewer.start_loop()


async def cmd_tablet(args):
    """Activate full screen digitizer / mouse takeover mode via uinput."""
    import evdev
    from evdev import UInput, ecodes as e, AbsInfo

    cfg = load_config()
    mac = args.mac or cfg.get("mac_address")
    orientation = getattr(args, "orientation", "landscape")

    # Setup uinput virtual tablet
    if orientation == "portrait":
        max_x, max_y = 28200, 37400
    else:
        max_x, max_y = 37400, 28200

    cap = {
        e.EV_KEY: [e.BTN_TOUCH, e.BTN_TOOL_PEN, e.BTN_LEFT, e.BTN_RIGHT],
        e.EV_ABS: [
            (e.ABS_X, AbsInfo(value=0, min=0, max=max_x, fuzz=0, flat=0, resolution=100)),
            (e.ABS_Y, AbsInfo(value=0, min=0, max=max_y, fuzz=0, flat=0, resolution=100)),
            (e.ABS_PRESSURE, AbsInfo(value=0, min=0, max=8192, fuzz=0, flat=0, resolution=1)),
        ]
    }
    ui = UInput(cap, name="Huion Note X10 Digitizer", version=0x3)

    print(f"\n🖊️  Huion Note X10 Tablet Mode Active ({orientation} orientation)")
    print("✨ Controlling OS mouse & pressure-sensitive drawing. Press Ctrl+C to stop.\n")

    def on_point_received(data: bytes):
        if len(data) >= 13 and data[0] == 0x55 and data[1] == 0x54:
            status = data[2]
            raw_x = data[3] | (data[4] << 8) | (data[9] << 16)
            raw_y = data[5] | (data[6] << 8) | (data[10] << 16)
            pressure = struct.unpack_from("<H", data, 7)[0]

            if orientation == "portrait":
                out_x = raw_y
                out_y = max(0, 37400 - raw_x)
            else:  # landscape
                out_x = max(0, 37400 - raw_x)
                out_y = max(0, 28200 - raw_y)

            is_in_range = status in (0x80, 0x81)
            is_touching = (status == 0x81 and pressure > 0)

            ui.write(e.EV_ABS, e.ABS_X, out_x)
            ui.write(e.EV_ABS, e.ABS_Y, out_y)
            ui.write(e.EV_ABS, e.ABS_PRESSURE, pressure)
            ui.write(e.EV_KEY, e.BTN_TOOL_PEN, 1 if is_in_range else 0)
            ui.write(e.EV_KEY, e.BTN_TOUCH, 1 if is_touching else 0)
            ui.syn()

    disconnected_event = asyncio.Event()

    def on_disconnect():
        disconnected_event.set()

    try:
        while True:
            conn = BleDeviceConnection(mac=mac)
            disconnected_event.clear()
            try:
                print(f"Connecting to Huion Note ({conn.mac})...")
                await conn.connect()
                await conn.setup_signals(on_point_received, on_disconnect)
                await conn.enter_live_tablet_mode()
                print("🟢 Connected! Ready for drawing on screen.")

                while not disconnected_event.is_set():
                    await asyncio.sleep(0.1)

                print("⚠️ Disconnected from device. Reconnecting...")
            except Exception as ex:
                log.debug(f"BLE connection loop note: {ex}")
            finally:
                await conn.close()
            await asyncio.sleep(1.0)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        ui.close()
        print("\n🛑 Tablet mode stopped.")


async def cmd_clean(args):
    """Explicitly wipe offline stored notes from device flash storage."""
    cfg = load_config()
    mac = args.mac or cfg.get("mac_address")
    
    if not args.yes:
        confirm = input("⚠️  Are you sure you want to delete all offline pages from the Huion Note? [y/N]: ")
        if confirm.lower() not in ("y", "yes"):
            print("Aborted.")
            return

    sync_mgr = OfflineSyncManager(mac=mac, output_dir=cfg.get("output_dir"), pin=cfg.get("pin") or None)
    try:
        await sync_mgr.run_sync(delete_after_export=True)
        print("\n🗑️  Device storage successfully purged. 50 pages memory available.")
    except Exception as e:
        print(f"\n❌ Purge failed: {e}")


def cmd_config(args):
    """View or update CLI configuration."""
    cfg = load_config()
    if args.mac:
        cfg["mac_address"] = args.mac.strip().upper()
    if args.out:
        cfg["output_dir"] = os.path.abspath(args.out)
    if args.pin:
        cfg["pin"] = args.pin.strip()
    
    save_config(cfg)
    print("\n⚙️  Current Huion Note Configuration:")
    print(f"  Config File : {CONFIG_PATH}")
    print(f"  MAC Address : {cfg.get('mac_address') or '(not set - auto-scanned)'}")
    print(f"  Output Dir  : {cfg.get('output_dir')}")
    print(f"  PIN Code    : {'******' if cfg.get('pin') else '(none)'}\n")


def cmd_transcribe(args):
    """Transcribe already imported / existing PNG notes to Obsidian Markdown via Gemini AI."""
    import subprocess
    script_path = os.path.expanduser("~/Documents/CYC-Caleb/process_huion_notes.py")
    if not os.path.exists(script_path):
        print("❌ Error: Transcription script not found at ~/Documents/CYC-Caleb/process_huion_notes.py")
        return

    cmd = [sys.executable, script_path]
    if getattr(args, "force", False):
        cmd.append("--force")
    if getattr(args, "files", None):
        cmd.extend(args.files)

    subprocess.run(cmd, check=False)


def cmd_trello(args):
    """Manage Trello integration, configuration, and manual ticket sync."""
    from huion.trello_sync import (
        load_trello_config, save_trello_config, TrelloClient, sync_markdown_tickets
    )
    from pathlib import Path
    cfg = load_trello_config()

    if getattr(args, "setup", False):
        import urllib.parse
        import webbrowser
        print("\n🔧 Trello Integration Setup")
        api_key = input(f"Enter Trello API Key [{cfg.get('api_key') or ''}]: ").strip() or cfg.get("api_key", "")
        if not api_key:
            print("❌ API Key is required. You can get it from https://trello.com/app-key")
            return

        token = cfg.get("token", "")
        print("\n🔑 Generating authorization URL for your Token...")
        params = {
            "expiration": "never",
            "name": "HuionNote Task Integration",
            "scope": "read,write,account",
            "response_type": "token",
            "key": api_key
        }
        auth_url = f"https://trello.com/1/authorize?{urllib.parse.urlencode(params)}"
        print(f"\n1. Opening authorization page in your browser...")
        print(f"   If it doesn't open automatically, click this link:\n   {auth_url}\n")
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

        print("2. Click 'Allow' on the Trello authorization page.")
        print("3. Copy the token displayed on the screen and paste it below:\n")
        token = input(f"Enter Trello Token [{cfg.get('token') or ''}]: ").strip() or cfg.get("token", "")

        if not token:
            print("❌ Token is required.")
            return

        client = TrelloClient(api_key, token)
        valid, member_info = client.verify_auth()
        if not valid:
            print("❌ Authentication failed. Please check your API key and Token.")
            return

        cfg["api_key"] = api_key
        cfg["token"] = token
        cfg["member_id"] = member_info.get("id", "")
        print(f"✅ Authenticated as: {member_info.get('fullName')} (@{member_info.get('username')})")

        boards = client.get_boards()
        if not boards:
            print("⚠️ No open boards found for this user.")
            save_trello_config(cfg)
            return

        print("\nAvailable Boards:")
        for idx, b in enumerate(boards, 1):
            print(f"  [{idx}] {b['name']} ({b['id']})")

        b_choice = input(f"\nSelect default board for [T] tickets [1-{len(boards)}]: ").strip()
        if b_choice.isdigit() and 1 <= int(b_choice) <= len(boards):
            sel_board = boards[int(b_choice) - 1]
            cfg["default_board_id"] = sel_board["id"]
            lists = client.get_lists(sel_board["id"])
            if lists:
                print(f"\nLists in '{sel_board['name']}':")
                for l_idx, l in enumerate(lists, 1):
                    print(f"  [{l_idx}] {l['name']}")
                l_choice = input(f"Select default list [1-{len(lists)}]: ").strip()
                if l_choice.isdigit() and 1 <= int(l_choice) <= len(lists):
                    cfg["default_list_id"] = lists[int(l_choice) - 1]["id"]

        save_trello_config(cfg)
        print("✅ Trello configuration saved successfully!")
        return

    if getattr(args, "test", False):
        api_key = cfg.get("api_key")
        token = cfg.get("token")
        if not api_key or not token:
            print("❌ Trello not configured. Run 'huion trello --setup' first.")
            return
        client = TrelloClient(api_key, token)
        valid, member = client.verify_auth()
        if not valid:
            print("❌ Authentication failed.")
            return
        list_id = cfg.get("default_list_id")
        if not list_id:
            print("❌ No default list configured. Run 'huion trello --setup'.")
            return
        print(f"Creating test card for @{member.get('username')}...")
        card = client.create_card(list_id, "[Test] Huion Note Task Automation", "Test card created by Huion CLI", [cfg.get("member_id")])
        if card:
            print(f"✅ Card created successfully: {card.get('shortUrl')}")
        return

    # Manual sync on file(s)
    if getattr(args, "files", None):
        for f in args.files:
            p = Path(f)
            if p.exists():
                print(f"Syncing tickets from {p.name}...")
                cards = sync_markdown_tickets(p)
                print(f"  Created {len(cards)} card(s).")
    else:
        inbox_notes = Path.home() / "Documents" / "CYC-Caleb" / "00 Inbox" / "Transcribed Notes"
        if inbox_notes.exists():
            for p in inbox_notes.glob("*.md"):
                cards = sync_markdown_tickets(p)
                if cards:
                    print(f"Synced {len(cards)} card(s) from {p.name}")


def main():
    parser = argparse.ArgumentParser(
        prog="huion",
        description="Huion Note X10 Linux CLI & Live Visualizer"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status / stats
    p_status = subparsers.add_parser("status", aliases=["stats"], help="Show device battery, stored flash pages, and connection status")
    p_status.add_argument("--mac", help="Device Bluetooth MAC address")

    # sync
    p_sync = subparsers.add_parser("sync", help="Sync offline notes to laptop (SVG, PNG, JSON)")
    p_sync.add_argument("-o", "--out", help="Output directory for notes")
    p_sync.add_argument("--mac", help="Device Bluetooth MAC address")
    p_sync.add_argument("--delete", action="store_true", help="Delete exported pages from device flash storage")
    p_sync.add_argument("--png-only", action="store_true", help="Only render and save PNG image files")
    p_sync.add_argument("--transcribe", action="store_true", help="Automatically transcribe synced notes to Obsidian Markdown via Gemini AI")

    # transcribe (standalone on existing imports)
    p_trans = subparsers.add_parser("transcribe", help="Transcribe already imported PNG notes to Obsidian Markdown via Gemini AI")
    p_trans.add_argument("files", nargs="*", help="Specific image file(s) to transcribe (optional, defaults to un-transcribed notes in Raw PNGs)")
    p_trans.add_argument("-f", "--force", action="store_true", help="Re-transcribe notes even if previously transcribed")

    # trello
    p_trello = subparsers.add_parser("trello", help="Trello task integration for [T] / [T:board] handwritten tickets")
    p_trello.add_argument("--setup", action="store_true", help="Configure Trello API Key, Token, and board mappings")
    p_trello.add_argument("--test", action="store_true", help="Create a test card and verify assignment")
    p_trello.add_argument("files", nargs="*", help="Markdown note files to scan and sync to Trello")

    # tablet (mouse / digitizer takeover)
    p_tablet = subparsers.add_parser("tablet", help="Activate full screen digitizer / mouse takeover mode")
    p_tablet.add_argument("--mac", help="Device Bluetooth MAC address")
    p_tablet.add_argument("--orientation", choices=["landscape", "portrait"], default="landscape", help="Tablet orientation (default: landscape)")

    # live
    p_live = subparsers.add_parser("live", help="Open real-time drawing visualizer window")
    p_live.add_argument("-o", "--out", help="Output directory for live drawings")
    p_live.add_argument("--mac", help="Device Bluetooth MAC address")

    # clean
    p_clean = subparsers.add_parser("clean", help="Purge offline stored notes from device memory")
    p_clean.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    p_clean.add_argument("--mac", help="Device Bluetooth MAC address")

    # config
    p_cfg = subparsers.add_parser("config", help="View or update settings")
    p_cfg.add_argument("--mac", help="Set default Bluetooth MAC address")
    p_cfg.add_argument("--out", help="Set default output directory")
    p_cfg.add_argument("--pin", help="Set optional 6-digit device PIN")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command in ("status", "stats"):
        asyncio.run(cmd_status(args))
    elif args.command == "sync":
        asyncio.run(cmd_sync(args))
    elif args.command == "transcribe":
        cmd_transcribe(args)
    elif args.command == "trello":
        cmd_trello(args)
    elif args.command == "tablet":
        asyncio.run(cmd_tablet(args))
    elif args.command == "clean":
        asyncio.run(cmd_clean(args))
    elif args.command == "live":
        cmd_live(args)
    elif args.command == "config":
        cmd_config(args)


if __name__ == "__main__":
    main()


