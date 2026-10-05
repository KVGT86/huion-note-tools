"""
Trello Integration Module for Huion Note & Obsidian Workflow.
Automatically parses handwritten ticket symbols [T], [T:board], ★, ▲,
creates Trello cards, assigns the user, and injects links back into Obsidian.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import requests

log = logging.getLogger("huion.trello")

CONFIG_PATH = Path.home() / ".config" / "huion" / "trello_config.json"
LEDGER_PATH = Path.home() / "Documents" / "CYC-Caleb" / "00 Inbox" / "Raw PNGs" / ".trello_ledger.json"

DEFAULT_CONFIG = {
    "api_key": "",
    "token": "",
    "member_id": "",
    "default_board_id": "",
    "default_list_id": "",
    "boards": {},
    "symbol_aliases": {
        "★": "eng",
        "▲": "ops",
        "T": "default"
    }
}


def load_trello_config() -> Dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {**DEFAULT_CONFIG, **cfg}
        except Exception as e:
            log.warning(f"Failed to load trello config: {e}")
    return DEFAULT_CONFIG.copy()


def save_trello_config(cfg: Dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_trello_ledger() -> Dict[str, Any]:
    if LEDGER_PATH.exists():
        try:
            with open(LEDGER_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_trello_ledger(ledger: Dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to save trello ledger: {e}")


class TrelloClient:
    def __init__(self, api_key: str, token: str):
        self.api_key = api_key
        self.token = token
        self.base_url = "https://api.trello.com/1"
        self.auth_params = {"key": self.api_key, "token": self.token}

    def verify_auth(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if not self.api_key or not self.token:
            return False, None
        try:
            res = requests.get(f"{self.base_url}/members/me", params=self.auth_params, timeout=10)
            if res.status_code == 200:
                return True, res.json()
        except Exception as e:
            log.error(f"Trello auth verification error: {e}")
        return False, None

    def get_boards(self) -> List[Dict[str, Any]]:
        res = requests.get(f"{self.base_url}/members/me/boards", params=self.auth_params, timeout=10)
        if res.status_code == 200:
            return [{"id": b["id"], "name": b["name"]} for b in res.json() if not b.get("closed")]
        return []

    def get_lists(self, board_id: str) -> List[Dict[str, Any]]:
        res = requests.get(f"{self.base_url}/boards/{board_id}/lists", params=self.auth_params, timeout=10)
        if res.status_code == 200:
            return [{"id": l["id"], "name": l["name"]} for l in res.json() if not l.get("closed")]
        return []

    def create_card(self, list_id: str, name: str, desc: str = "", member_ids: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        payload = {
            **self.auth_params,
            "idList": list_id,
            "name": name,
            "desc": desc,
            "idMembers": member_ids or []
        }
        res = requests.post(f"{self.base_url}/cards", json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()
        log.error(f"Failed to create card '{name}': {res.status_code} {res.text}")
        return None


def sync_markdown_tickets(file_path: Path) -> List[Dict[str, Any]]:
    """Scan an Obsidian markdown file for [T] / [T:board] / ★ / ▲ tags, create Trello cards, and update note."""
    cfg = load_trello_config()
    api_key = cfg.get("api_key") or os.environ.get("TRELLO_API_KEY", "")
    token = cfg.get("token") or os.environ.get("TRELLO_TOKEN", "")

    if not api_key or not token:
        log.info("Trello sync skipped: No Trello API credentials configured.")
        return []

    client = TrelloClient(api_key, token)
    valid, member_info = client.verify_auth()
    if not valid or not member_info:
        log.warning("Trello sync skipped: Invalid credentials.")
        return []

    member_id = cfg.get("member_id") or member_info.get("id")
    member_ids = [member_id] if member_id else []

    if not file_path.exists():
        return []

    content = file_path.read_text(encoding="utf-8")
    ledger = load_trello_ledger()

    # Regex patterns for ticket triggers:
    # 1. - [ ] [T] Task description
    # 2. - [ ] [T:board] Task description
    # 3. - [ ] ★ Task description
    # 4. - [ ] ▲ Task description
    pattern = re.compile(
        r"^(\s*-\s*\[[ xX]?\]\s*)(?:\[T(?::([a-zA-Z0-9_-]+))?\]|([★▲]))\s+(.+)$",
        re.MULTILINE
    )

    created_cards = []
    lines = content.splitlines()
    modified = False

    for i, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue

        prefix, board_tag, symbol_glyph, task_text = match.groups()
        board_key = (board_tag or "").lower()

        if symbol_glyph:
            board_key = cfg.get("symbol_aliases", {}).get(symbol_glyph, "default")
        elif not board_key:
            board_key = "default"

        # Clean task text for Trello card title (remove hashtags and markdown asterisks)
        task_clean = task_text.strip()
        card_title = re.sub(r"#[\w\/-]+", "", task_text)
        card_title = re.sub(r"\*\*([^*]+)\*\*", r"\1", card_title)
        card_title = re.sub(r"\*([^*]+)\*", r"\1", card_title)
        card_title = re.sub(r"\s+", " ", card_title).strip()

        task_key = f"{file_path.stem}::{task_clean}"
        if task_key in ledger:
            continue

        # Resolve target list
        target_list_id = None
        if board_key in cfg.get("boards", {}):
            target_list_id = cfg["boards"][board_key].get("list_id")
        elif cfg.get("default_list_id"):
            target_list_id = cfg["default_list_id"]

        if not target_list_id:
            log.warning(f"No Trello list configured for board '{board_key}'")
            continue

        desc = f"Transcribed from Obsidian note: [[{file_path.stem}]]\nRaw Task: {task_clean}\nSource: CYC-Caleb Vault"
        card = client.create_card(
            list_id=target_list_id,
            name=card_title,
            desc=desc,
            member_ids=member_ids
        )

        if card and "shortUrl" in card:
            card_url = card["shortUrl"]
            ledger[task_key] = {
                "card_id": card["id"],
                "url": card_url,
                "created_at": card.get("dateLastActivity", "")
            }
            # Append markdown link to task line
            lines[i] = f"{prefix}{task_clean} [Trello]({card_url})"
            modified = True
            created_cards.append({
                "task": card_title,
                "url": card_url,
                "board": board_key
            })
            log.info(f"Created Trello card: '{card_title}' -> {card_url}")

    if modified:
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        save_trello_ledger(ledger)

    return created_cards
