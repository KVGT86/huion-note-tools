# HuionNote

A unified CLI, desktop application, real-time live digital canvas, and automated handwriting transcription pipeline for the **Huion Note X10** smart digital notebook on Linux (Zorin OS / Ubuntu / Debian).

![HuionNote](assets/huionnote.png)

---

## Features

* **Notes-first workspace**: Search titles and transcripts, filter page states, and click pages to build a selection for bulk export or transcription.
* **In-app reading and review**: Crisp vector handwriting preview, Markdown reading, and side-by-side transcript editing.
* **Batch export**: SVG, PDF, high-resolution PNG, original JSON pen samples, and Markdown with companion sketches. Existing files are preserved.
* **Live notebook sharing**: Smooth pressure-sensitive vector ink, zoom, pan, paper guides, saved pages and recoverable local drafts. F11 presents only the notebook; Escape restores controls.
* **Image annotation**: Add a photo, scan or diagram beneath live ink, then save or export the combined page without changing the original image.
* **Notebook management**: A dedicated Device workspace provides safe sync, verified sync-and-free-space, optional connection auto-sync, storage context and a separated erase action.
* **Organised library**: Rename, tag, favourite and collect pages; search includes those details and transcripts remain queued until reviewed.
* **Obsidian Inbox**: Publish selected pages as deterministic Markdown and mobile-friendly PNG previews, updating safely by stable Huion page ID.
* **Complete live toolkit**: Undo/redo, stroke eraser, highlighter, presentation pointer, paper templates and adjustable image backgrounds.
* **Local transcription**: Line-segmented Microsoft TrOCR runs on this computer and is tuned for handwriting. Tesseract remains available only through the legacy CLI.
* **Cloud transcription**: Explicitly selected Gemini transcription using a key configured in Settings. Only selected pages are sent. The REST integration needs no additional SDK.
* **Device controls**: Connection and battery state, reconnect, persistent folder/address/PIN settings, and confirmed device clearing.
* **Notion-inspired PySide6 interface**: Paper, graphite, native typography, quiet contextual actions, and an optional activity log. Native Wayland is preferred on supported desktops.

The Tkinter annotation editor and tray implementation remain in the repository as legacy tools; they are not features of the default Qt workspace.

## Desktop 1.7.3

Open **Notes**, sync the notebook, select a page, then use Handwriting, Transcript, or Edit transcript. Each click toggles a page in the selection; Select all/Clear selection handles the full filtered list. Export and Transcribe operate on that selection.

Enhanced local handwriting transcription uses Microsoft's TrOCR small handwritten model. The model downloads once on first use, then the selected pages remain on this computer. If the model dependencies are unavailable, the desktop app disables the local option instead of silently substituting Tesseract.

The trash icon deletes selected local pages after confirmation, moving their associated handwriting, pen data, transcript and preview files to the desktop Trash. Restore them through your file manager. Notebook originals and the active live draft are kept; syncing can import notebook originals again. GIO's system `gio` command is required; deletion refuses to run without recoverable Trash support.

The footer estimates free X10 pages from the last complete device sync, using [Huion's stated capacity of up to 50 pages](https://www.huion.com/products/huion-note). It is not a byte-level or real-time reading. Repeated imports, live pages and local deletion do not change device capacity. Hover for the observation time; sync again after writing offline or using another app. Incomplete scans leave the previous estimate unchanged, and estimates are tied to the notebook's Bluetooth address.

Dropdown menus, dialogs and selection states share a consistent Qt theme. The updated transparent logo appears in the app and desktop launcher.

The live toolbar groups page navigation, paper guides and icon-led save/new-page actions. Fit and zoom controls live in the status footer with connection and draft state. Hover or focus controls for their action names; shortcuts remain available.

UI icons are downloaded from [Lucide](https://lucide.dev/icons/), bundled locally with their license and pinned source revision. No icon service or extra runtime dependency is required.

Open **Live notebook** when sharing your writing. Save page adds the current page to Notes; New page saves it before starting a fresh page. The X10 page button uses the same save-and-advance action. Previous/Next browse this session; earlier saved sessions remain in Notes. A draft is saved every three seconds and restored on restart. Disconnects leave the page visible.

The X10 stays in its normal paired mode while Notes is open. HuionNote enables live pen streaming only when Live notebook is open, then returns the device to paired mode when you leave that workspace. Page changes reuse the active Bluetooth session, so the notebook does not need to be woken again between Notes, Live notebook and Device.

Linux requires the small BlueZ duplicate-MTU patch bundled at [`packaging/bluez/huion-x10-duplicate-mtu.patch`](packaging/bluez/huion-x10-duplicate-mtu.patch). Without it, X10 firmware can trigger a disconnect every 5–8 seconds. Build it against your distribution's BlueZ source, install the resulting package and hold that package so a stock update does not silently restore the fault. The patch comes from the [upstream X10 Linux driver](https://github.com/Reginleif86/huion-note-x10-ble).

The palette control selects ink for new strokes: Graphite, Blue, Burgundy, Green or a custom opaque colour. Existing handwriting keeps its original colour, including a stroke already in progress. Colours are retained in drafts, saved pages and exports; raw coordinates and pressure samples are unchanged. Older monochrome drafts open as Graphite. Paper guides remain view-only.

Use **Image → Choose image…** in Live notebook to annotate a JPEG, PNG, WebP, BMP or TIFF. HuionNote corrects its orientation, fits it on the page without distortion and keeps the original file unchanged. Replace or remove it from the same menu. Draft recovery retains the working image, while saved SVG, PNG and PDF pages embed the image beneath the vector ink.

Shortcuts: Ctrl+F search, Ctrl+S save the current page/transcript, Ctrl+E export, Ctrl+N new live page, F11 present, Escape leave presentation. Ctrl+wheel zooms; dragging pans the page.

Live tool shortcuts: Ctrl+Z undo, Ctrl+Shift+Z redo, Ctrl+Shift+E eraser, Ctrl+Shift+H highlighter and Ctrl+Shift+P presentation pointer. Use Device for notebook storage operations; automatic sync only copies and never erases pages.

Set an **Obsidian vault** once in Settings, then select pages in Notes and choose **Send to Obsidian Inbox**. HuionNote writes notes beneath `00 Inbox/Huion` and PNG previews beneath `00 Inbox/Huion Attachments`. Republishing updates the matching `huion_id`; it never creates numbered vault copies or exports raw pen data into the vault.

Versions follow Semantic Versioning, commits use Conventional Commits, and releases are recorded in [CHANGELOG.md](CHANGELOG.md). See [DESIGN.md](DESIGN.md) for the maintained style guide.

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
│       ├── htr.py               # Local TrOCR handwriting recognition & Gemini Vision
│       ├── models.py            # Data models (Note, Page, Stroke, etc.)
│       ├── pipeline.py          # State machine & offline sync coordinator
│       ├── store.py             # SVG, JSON, and Markdown storage managers
│       └── gui/
│           ├── qt_app.py        # PySide6 shell; default desktop interface
│           ├── app.py           # Legacy Tkinter shell during migration
│           ├── components.py    # Legacy Tkinter components
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

   Native Wayland is preferred when available. The X11 fallback needs its cursor runtime on Ubuntu/Debian:

   ```bash
   sudo apt install libxcb-cursor0
   ```
   Tesseract is needed only for the legacy CLI OCR command:

   ```bash
   sudo apt install tesseract-ocr tesseract-ocr-eng
   ```

   A platform override remains available for troubleshooting: run with `QT_QPA_PLATFORM=xcb`. Gemini defaults to `gemini-3.8-flash`; set `HUION_GEMINI_MODEL` to another supported model ID if needed. API format: [Google Gemini generateContent](https://ai.google.dev/api/generate-content).
   The installer will:

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

Local handwriting-recognition dependencies can be installed later with:

```bash
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -e '.[handwriting]'
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
* **Handwriting Recognition Models (HTR)**: This application integrates `Microsoft TrOCR` for offline handwriting transcription, alongside optional multimodal cloud transcription via Google's Gemini Vision API. Machine learning and vision transcription outputs are probabilistic approximations and may contain inaccuracies, misreadings, or hallucinations (particularly with cursive, mathematical notation, or low-contrast strokes). Users are advised to review transcribed Markdown files against their original vector SVG ink drawings.
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
