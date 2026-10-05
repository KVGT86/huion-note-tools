# HuionNote

A unified CLI, desktop application, real-time live digital canvas, and automated handwriting transcription pipeline for the **Huion Note X10** smart digital notebook on Linux (Zorin OS / Ubuntu / Debian).

![HuionNote](assets/huionnote.png)

---

## Features

* **Real-Time Live Canvas**: Stream pen strokes directly from the Huion Note X10 over BLE with pressure sensitivity and A5 paper aspect ratio rendering.
* **Offline Deep Learning Handwriting Transcription (HTR)**: Uses local neural networks (`EasyOCR` + `Microsoft TrOCR`) to transcribe cursive and print notes directly into structured Markdown without an internet connection.
* **Cloud AI Transcription**: Optional one-click **"AI Convert (Gemini)"** button for multimodal handwriting recognition.
* **In-App Annotation & Editor**: Annotate existing synced notes or draw new vector strokes directly onto pages.
* **Markdown Reader**: Preview transcribed Markdown directly inside the app with Obsidian-compatible YAML frontmatter and one-click "Open in Default Editor".
* **Persistent Document Library**: Scans and indexes all existing notes across `~/HuionNotes` and offline storage locations.
* **System Tray Indicator**: Minimalist system tray pen icon with live connection dot (blue = connected, yellow = connecting, red = disconnected) and battery percentage.
* **Customizable Interface**: Clean Notion / Apple-inspired light mode UI with togglable activity log console in the Settings menu.

---

## Repository Structure

```
huion-notes/
├── src/
│   └── huion_note_pipeline/     # Core pipeline package
│       ├── ble_bridge.py        # BlueZ / D-Bus BLE transport & pen streaming
│       ├── config.py            # Pipeline configuration
│       ├── converter.py         # Coordinate conversion & SVG generator
│       ├── editor.py            # Vector in-app note annotator & canvas
│       ├── enums.py             # NoteStatus, NoteCategory enums
│       ├── frontmatter.py       # YAML metadata parser & generator
│       ├── htr.py               # Local neural HTR (EasyOCR/TrOCR) & Gemini Vision
│       ├── models.py            # Data models (Note, Page, Stroke, etc.)
│       ├── pipeline.py          # State machine & offline sync coordinator
│       ├── store.py             # SVG, JSON, and Markdown storage managers
│       └── gui/
│           ├── app.py           # Main application window & UI lifecycle
│           ├── components.py    # UI components, modals, and settings dialog
│           └── tray.py          # System tray indicator & background menu
├── assets/
│   ├── huionnote.png            # Application & system tray icon art
│   └── huionnote.desktop        # Desktop launcher entry
├── tests/                       # Unit & invariant test suite (pytest + hypothesis)
├── install.sh                   # One-click installation script
├── start_app.py                 # Application launcher
├── pyproject.toml               # Package build configuration
└── requirements.txt             # Python dependencies
```

---

## Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd huion-notes
   ```

2. **Run the install script**:
   ```bash
   ./install.sh
   ```
   This will:
   * Create and configure the `.venv` virtual environment.
   * Install all required dependencies.
   * Install the desktop launcher and icon into `~/.local/share/applications/` and `~/.local/share/icons/`.
   * Create the default user notes storage directory at `~/HuionNotes`.

3. **Launch the application**:
   * Open **HuionNote** from your system Application Menu / Dock, or
   * Run directly via terminal:
     ```bash
     ./start_app.py
     ```

## Command Line

The GUI and CLI use the same `huion` BLE and sync package. After installation:

```bash
huion config --mac AA:BB:CC:DD:EE:FF
huion status
huion sync
huion live
huion tablet
huionnote
```

---

## Changing the Application Icon

If you wish to change the application and tray icon art:
1. Replace the file at `assets/huionnote.png` with your desired PNG image (recommended: 512x512 with transparent background).
2. Re-run `./install.sh` to update your desktop environment and system caches.

---

## Note Storage

User documents (`.svg`, `.json`, `.md`) are stored outside the git repository by default at:
```
~/HuionNotes/
```
You can customize this path by exporting `HUION_NOTES_DIR`:
```bash
export HUION_NOTES_DIR="/path/to/your/notes"
```

---

## Running Tests

Run the full automated test suite (220+ tests):
```bash
.venv/bin/pytest tests
```

---

## Disclaimers & Legal Notices

### 1. Unaffiliation & Trademarks Notice
* **Independent Community Project**: This software is an independent, open-source community companion utility developed to provide Linux desktop compatibility and offline document synchronization for the Huion Note X10 digital smart notebook.
* **No Official Affiliation**: This project is **not** created, endorsed, sponsored, affiliated with, or supported by **Shenzhen Huion Animation Technology Co., Ltd.** or any of its subsidiaries.
* **Trademarks**: "Huion", "Huion Note", and related names, logos, or marks are registered trademarks of Shenzhen Huion Animation Technology Co., Ltd. All other company names, brand names, and product names mentioned in this project are trademarks or registered trademarks of their respective owners.

### 2. AI & Machine Learning Usage Notice
* **Handwriting Recognition Models (HTR)**: This application integrates open-source neural network models (such as `EasyOCR` and `Microsoft TrOCR`) for offline optical character and handwriting transcription, alongside optional multimodal cloud transcription via Google's Gemini Vision API. Machine learning and vision transcription outputs are probabilistic approximations and may contain inaccuracies, misreadings, or hallucinations (particularly with cursive, mathematical notation, or low-contrast strokes). Users are advised to review transcribed Markdown files against their original vector SVG ink drawings.
* **AI-Assisted Development**: Portions of this codebase, architecture specifications, and documentation were authored and refined with the assistance of artificial intelligence coding systems under human developer oversight.

### 3. Software Usage & Hardware Interoperability
* **Provided "As-Is"**: This software is distributed under the MIT License on an "AS IS" basis, without warranties or conditions of any kind, either express or implied.
* **Hardware Interoperability**: Bluetooth Low Energy (BLE) protocol communications are implemented via non-invasive observation of standard GATT characteristics to enable Linux desktop interoperability. The authors and maintainers assume no liability for any data loss, hardware malfunction, unexpected device behavior, or damages arising from the use of this software.

---

## Credits & Acknowledgments

Special thanks and credit to:
* **[Reginleif88](https://github.com/Reginleif88)** for the pioneering reverse-engineering of the Huion Note X10 BLE protocol in the [**`huion-note-x10-ble`**](https://github.com/Reginleif88/huion-note-x10-ble) repository, which provided the foundational Linux Bluetooth Low Energy driver implementation, GATT service specifications, and pen packet decoders.
* The open-source Linux digital inking community, including the **OpenTabletDriver** and **libwacom** contributors.

---

## License

Distributed under the [MIT License](LICENSE). See `LICENSE` for more information.
