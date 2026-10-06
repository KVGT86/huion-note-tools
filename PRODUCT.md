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
- Device clearing requires explicit confirmation; normal sync retains device originals.
- Local page deletion uses recoverable desktop Trash and keeps device originals and live drafts.
- Remaining X10 pages are an estimate from the last complete device sync, not local import totals or a live storage reading.
- Cloud transcription is an explicit action and sends selected handwriting to Gemini.
- Physical pen fidelity must be checked with actual handwriting; synthetic rendering tests cannot establish hardware quality.

## Brand Commitments
Preserve the Notion-inspired paper-and-graphite theme and the user's supplied notebook-and-pen icon.

## Product Principles
- Keep the document central and controls contextual.
- Finish normal note workflows inside the app.
- Preserve originals and make failure recovery understandable.
- Keep device and storage logic outside UI widgets.
