# Changelog

Versions follow Semantic Versioning. Commit messages follow Conventional Commits.

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
