# HuionNote
<!-- impeccable:product-schema 1 -->

## Platform
Native Linux desktop using PySide6 / Qt Widgets. An iPhone client is a future objective, not part of this release.

## Users
The owner of a Huion Note X10 who writes on paper, saves and exports notes, and shares their notebook during calls.

## Product Purpose
Save, inspect, optionally transcribe, and export handwritten notes without requiring terminal commands. The live notebook is primarily a screen-sharing surface.

## Operating Context
Huion Note X10 over Bluetooth on this Linux PC. Local notes must remain usable when the notebook is disconnected.

## Capabilities and Constraints
- Notes and export lead the desktop experience.
- Handwriting and transcripts can be reviewed together.
- Raw pen samples remain available separately from rendered geometry.
- CLI operations and Qt rendering use shared UI-independent backend code.
- Live drafts are stored locally and restored after restart.
- Notes keeps a normal paired X10 connection; only the Live notebook workspace may enable pen streaming.
- Live ink colours belong to individual strokes and survive drafts, saved-page browsing and exports.
- A live page may contain one imported image beneath the ink; it is recoverable, removable, adjustable through HuionNote's working copy and embedded into visual exports without changing the source file.
- Device clearing requires explicit confirmation; normal sync retains device originals.
- Local page deletion uses recoverable desktop Trash and keeps device originals and live drafts.
- Remaining X10 pages are an estimate from the last complete device sync, not local import totals or a live storage reading.
- Saved pages support explicit click-to-toggle multi-selection for batch export, transcription and a combined PDF in library order.
- Saved pages support user titles, tags, collections, favourites and explicit transcript review state.
- Selected pages can be published to a configured Obsidian Inbox as frontmatter-rich Markdown plus a mobile PNG, updating only by stable Huion page ID.
- Raw SVG, JSON, drafts, ledgers and recovery files never enter the Obsidian vault.
- Device management has a dedicated workspace; sync-and-free-space removes only pages the transport has saved locally, and automatic sync never deletes.
- Live work supports undo/redo, stroke erasing, highlighting, a temporary pointer, grid guides and non-destructive working-copy image adjustment.
- Transcription is an explicit action that sends only selected handwriting to Gemini and requires a user-provided API key.
- Physical pen fidelity must be checked with actual handwriting; synthetic rendering tests cannot establish hardware quality.

## Brand Commitments
Preserve the cream paper-and-graphite theme, using steel blue only for accents and the cartoon X10 identity.

## Product Principles
- Keep the document central and controls contextual.
- Finish normal note workflows inside the app.
- Preserve originals and make failure recovery understandable.
- Keep device and storage logic outside UI widgets.
