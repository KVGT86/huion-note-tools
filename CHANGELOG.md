# Changelog

Versions follow Semantic Versioning. Commit messages follow Conventional Commits.

## [1.7.2] — 2026-10-08

### Fixed
- Notes mode now completes the X10 challenge-response before its heartbeat and ignores duplicate challenge notifications.
- Active sync reuses the same authenticated connection instead of re-entering notebook mode afterward.
- Documented and bundled the upstream BlueZ duplicate-MTU patch required for stable X10 sessions on Linux.

## [1.7.1] — 2026-10-08

### Fixed
- Notes and Device now keep the X10 paired with the notebook-mode heartbeat; live pen streaming remains exclusive to Live notebook.

## [1.7.0] — 2026-10-08

### Added
- Separate Send to Obsidian Inbox workflow with one configured vault root and bulk support for selected pages.
- Deterministic `00 Inbox/Huion/YYYY-MM-DD-title.md` notes and `00 Inbox/Huion Attachments/<huion-id>.png` previews.
- Stable page IDs, safe update-in-place publishing and collision refusal when an unrelated note occupies the target filename.
- Obsidian frontmatter for Huion titles, tags, collections, favourite and reviewed state.

### Changed
- Obsidian receives only Markdown and a 1410×1870 mobile-friendly PNG; raw SVG, JSON, drafts and recovery material remain in HuionNote's private library.
- General Export remains unchanged and continues to preserve conventional numbered copies.

## [1.6.0] — 2026-10-07

### Added
- Dedicated Device workspace with connection, battery, storage estimate, safe sync, verified sync-and-free-space, optional connection auto-sync, session history and an isolated erase action.
- Live undo/redo, stroke eraser, highlighter, presentation pointer and grid template, with keyboard shortcuts and compact icon controls.
- Saved-page titles, tags, collections, favourites and transcript review state, all searchable from Notes.
- Combined multi-page PDF export for selected notes.
- Imported-image rotation, positioned page cropping and opacity adjustment while preserving the source image.

### Changed
- Notes, Live notebook and Device now own the X10 mode explicitly; only Live notebook enables tablet streaming.
- Transcribed pages remain in a Needs review queue until explicitly reviewed.
- Official pinned Lucide icons cover every new tool and device action.

## [1.5.0] — 2026-10-07

### Added
- Image backgrounds for the Live notebook, with JPEG, PNG, WebP, BMP and TIFF import through a compact Image menu.
- Image replacement/removal, draft recovery and in-session saved-page browsing without modifying the original file.
- Self-contained saved SVGs that embed the normalized image beneath vector ink; PNG and PDF exports retain the annotation background.

### Changed
- Live toolbar labels collapse to accessible icon-only controls at compact window widths.
- Imported images are orientation-corrected, contained without distortion and normalized to a practical local JPEG size.

## [1.4.1] — 2026-10-07

### Fixed
- Notes keeps the X10 in its normal paired state; the live-tablet handshake now runs only while Live notebook is open.
- Sync and reconnect return to the mode requested by the active workspace instead of forcing live streaming.
- Connection status distinguishes paired and live states.

## [1.4.0] — 2026-10-07

### Added
- Click-to-toggle multi-selection with a visible Select all/Clear selection action for batch export and transcription.
- Line-segmented Microsoft TrOCR handwriting recognition as the enhanced local transcription engine.
- CPU-only handwriting dependencies in the Linux installer; the configured model is cached for offline use after its first download.

### Fixed
- Saved-note selection backgrounds and row content are inset from the list boundary and scrollbar.
- Local transcription no longer silently falls back to Tesseract when the handwriting model is unavailable.

## [1.3.0] — 2026-10-06

### Added
- Compact live ink-colour menu with Graphite, Blue, Burgundy, Green and a custom Qt colour picker.
- Per-stroke colours survive draft recovery, saved-page browsing and SVG/PNG/PDF/JSON exports without changing raw pen samples.
- Downloaded Lucide palette icon, named colour choices and a visible current-colour label.

### Fixed
- Crossing and retracing a stroke no longer produces white gaps: active and cached ink use winding fill, matching SVG's explicit nonzero fill rule.
- Changing ink applies to new strokes without recolouring existing ink or a stroke already in progress.

## [1.2.0] — 2026-10-06

### Added
- Confirmed local page deletion through the desktop Trash, including associated files and a downloaded Lucide trash icon.
- Device-specific, persisted last-sync storage estimate based on Huion's stated 50-page maximum; uncertain scans do not replace an earlier estimate.
- Deletion protects transcript edits, retains the live draft and removes deleted pages from session history.

### Fixed
- Export and Transcribe actions have 16px clearance above the footer.
- Notebook storage estimates count device slots, not cumulative local imports; timeouts are not treated as empty storage.

## [1.1.3] — 2026-10-06

### Changed
- Footer has a 56px minimum height, wider outer padding and spacing between status groups.
- Toolbar, utilities, dropdown and checkbox icons use downloaded Lucide SVG assets.
- Upstream icon revision, ISC/MIT license notices and a colour-only checkbox variant are bundled with the package.
- Qt renders SVG icons directly; removed custom icon geometry and raster generation.

## [1.1.2] — 2026-10-06

### Changed
- Unified live toolbar with outlined icons for page navigation, saving, new pages and presentation.
- Fit and zoom controls moved into a full-width status footer alongside connection and draft state.
- Compact icon-led Activity and Settings utilities; version information moved into Settings.
- Keyboard-accessible icons with named tooltips and high-DPI rendering.

### Fixed
- Footer draft state reflects unsaved changes, successful saves, failures and saved-page browsing.
- Unavailable page navigation is disabled; presentation hides the whole footer.

## [1.1.1] — 2026-10-06

### Changed
- Consistent Qt Fusion controls, styled dropdown menus, checkboxes, radio buttons and scrollbars.
- Stronger page selection, navigation, focus, control boundaries and readable placeholder text.
- Separate title and metadata typography in the page list.
- Direct, consistent interface wording; explicit export, transcription and erase actions.
- Empty-selection preview and save-button states that match the current workflow.
- Updated transparent logo in the desktop launcher, window and sidebar.

## [1.1.0] — 2026-10-06

### Added
- Notes-first workspace with title/transcript search, status filters and multiselection.
- In-app vector handwriting preview, Markdown reader and side-by-side transcript editing.
- Batch SVG, PDF, high-resolution PNG, raw JSON and Markdown export.
- Local or explicitly selected cloud transcription with progress and recoverable errors.
- Live page saving, local draft recovery, previous/next session pages and new-page preservation.
- Fit-page/fit-width controls, zoom, pan, optional paper guides and F11 presentation mode.
- Persistent device, output-folder and transcription settings.

### Changed
- Shared pressure-sensitive ink outlines for Qt, SVG and PNG, retaining original samples.
- Native Wayland preferred with X11 fallback and explicit platform override support.
- Supplied high-resolution application icon installed and loaded by the Qt window.
- Gemini REST integration uses the existing requests dependency; the model can be selected with HUION_GEMINI_MODEL.

### Fixed
- Single-point ink marks and pressure variation along individual strokes.
- Restoring existing Markdown paths when loading saved notes.
- Preventing earlier live pages from overwriting the active draft.
- Preventing export collisions and preserving Markdown sketch companions.
- Reserving fresh sync folders and showing separate imports with matching page names.
- Retaining vector imports in the GUI even when the shared CLI folder is named Raw PNGs.
- Surfacing local OCR and device-clearing failures instead of reporting false success.

### Validation
- Automated ink, recovery, export and Qt workflow checks.
- Native Wayland launch check and rendered screen inspection at 1× and 2× scaling.
- Bluetooth pen feel and cloud account access require real hardware/account testing.

## [1.0.0]
- Unified Huion CLI, pipeline and desktop source, followed by the initial PySide6 translation.
