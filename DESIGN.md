---
name: HuionNote
description: A warm paper-and-graphite desktop workspace for live Huion ink and note conversion.
colors:
  graphite-ink: "#25231F"
  graphite-muted: "#625F59"
  graphite-faint: "#706D67"
  paper: "#FFFFFF"
  warm-paper: "#F7F6F3"
  hover-wash: "#EEEDE8"
  hairline: "#E3E1DC"
  focus-ring: "#9C9A94"
  selected-wash: "#E8E6E1"
  state-success: "#23683A"
  state-warning: "#7D480C"
  state-danger: "#B43D35"
  success-wash: "#E8F3EB"
  warning-wash: "#FFF3DF"
  danger-wash: "#FBE9E7"
typography:
  title:
    fontFamily: "Aptos, Noto Sans, sans-serif"
    fontSize: "20px"
    fontWeight: 650
  brand:
    fontFamily: "Aptos, Noto Sans, sans-serif"
    fontSize: "16px"
    fontWeight: 650
  body:
    fontFamily: "Aptos, Noto Sans, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  status:
    fontFamily: "Aptos, Noto Sans, sans-serif"
    fontSize: "11px"
    fontWeight: 650
  section-label:
    fontFamily: "Aptos, Noto Sans, sans-serif"
    fontSize: "10px"
    fontWeight: 650
    letterSpacing: "1px"
rounded:
  scrollbar: "4px"
  list-item: "6px"
  control: "7px"
  panel: "10px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  canvas-margin: "28px"
components:
  button-primary:
    backgroundColor: "{colors.graphite-ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.graphite-muted}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  navigation-active:
    backgroundColor: "{colors.selected-wash}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  status-connected:
    backgroundColor: "{colors.success-wash}"
    textColor: "{colors.state-success}"
    rounded: "{rounded.panel}"
    padding: "4px 9px"
  status-connecting:
    backgroundColor: "{colors.warning-wash}"
    textColor: "{colors.state-warning}"
    rounded: "{rounded.panel}"
    padding: "4px 9px"
  status-failed:
    backgroundColor: "{colors.danger-wash}"
    textColor: "{colors.state-danger}"
    rounded: "{rounded.panel}"
    padding: "4px 9px"
---

# Design System: HuionNote

## Overview

**Creative North Star: "Notion for Huion"**

HuionNote is a quiet, native Operate surface built from warm paper, graphite ink, and precise hairlines. It should feel like opening a dependable notebook workspace: familiar enough to disappear during use, but unmistakably tied to handwriting through its A5 page, dot grid, and pressure-sensitive ink.

The live A5 canvas is the visual and functional centre of gravity. Navigation and controls recede into a fixed, quiet sidebar and a slim top bar; document management remains a dense list rather than becoming a card dashboard. Colour communicates device state, note state, or destructive risk only.

The PySide6 layer renders state and forwards user intent. `HuionApplication` remains the owner of hardware, sync, settings, note discovery, storage, and conversion workflows; visual extensions must preserve this boundary.

**Key Characteristics:**

- Warm off-white workspace with crisp white paper surfaces.
- Graphite-first type, controls, and live ink.
- A5 canvas as the largest and most visually important object.
- Fixed 224px sidebar with compact, left-aligned native controls.
- Hairline separators and tonal washes instead of card chrome or decorative elevation.
- Semantic green, amber, and red reserved for operational state and risk.

## Colors

The palette is nearly monochrome: warm paper and graphite establish the environment, while semantic colour appears only when the system has something operational to say.

### Primary

- **Graphite Ink** (`#25231F`): primary text, active controls, live pen strokes, and the single filled action button.

### Secondary

- **Connected Green** (`#23683A`): connected and converted states only, paired with Success Wash.
- **Working Amber** (`#7D480C`): connecting and converting states only, paired with Warning Wash.
- **Failure Red** (`#B43D35`): failed and destructive states only, paired with Danger Wash when a status background is needed.

### Neutral

- **Graphite Muted** (`#625F59`): metadata, quiet controls, and neutral device or note state.
- **Graphite Faint** (`#706D67`): compact section labels that organize the sidebar without competing with navigation.
- **Paper** (`#FFFFFF`): the A5 sheet, top bar, fields, note rows, and primary-button text.
- **Warm Paper** (`#F7F6F3`): sidebar, page wells, and the space surrounding the canvas.
- **Hover Wash** (`#EEEDE8`): hover feedback for unfilled controls.
- **Hairline** (`#E3E1DC`): top-bar and note-row separation.
- **Selected Wash** (`#E8E6E1`): checked navigation and selected list items.

### Named Rules

**The Semantic Colour Rule.** Green, amber, and red communicate device state, note state, or destructive risk; they are never decorative accents.

**The Paper Before Paint Rule.** Extend the neutral paper-and-graphite scale before introducing any new hue.

## Typography

**Display Font:** Aptos (with Noto Sans and system sans-serif fallbacks)

**Body Font:** Aptos (with Noto Sans and system sans-serif fallbacks)

**Character:** One practical sans-serif family keeps the native tool legible and restrained. Hierarchy comes from size, weight, spacing, and placement rather than expressive font pairing.

### Hierarchy

- **Title** (650, 20px): current workspace name in the top bar.
- **Brand** (650, 16px): product name at the top of the sidebar.
- **Empty-state title** (650, 17px): the single lead line in a quiet empty state.
- **Body** (400, 13px): buttons, note names, fields, and general interface copy.
- **Status** (650, 11px): compact device and note-state labels.
- **Section label** (650, 10px, 1px tracking, uppercase): sidebar grouping labels only.

### Named Rules

**The Native Clarity Rule.** Use type to establish scan order, never to simulate editorial drama inside the operating surface.

## Layout

The window opens at 1180×760px and supports a minimum of 900×600px. A fixed 224px sidebar anchors the left edge; the remaining width belongs to a top bar and one active workspace. The shell uses zero outer gaps so separation comes from surface tone and hairlines.

The live page uses 24px horizontal margins, with 16px above and 24px below. Its A5 canvas preserves a 148:210 aspect ratio inside a flexible well, maintaining a 28px minimum surrounding margin and a 420×520px minimum drawing area. The library uses the same 24px horizontal rhythm and renders notes as full-width rows separated by 1px rules.

**The Canvas Priority Rule.** When space tightens, controls stay compact and the canvas keeps the largest available region; never reduce it to a dashboard tile.

## Elevation & Depth

The system is flat by default and uses no shadows. Depth comes from warm-versus-white surface contrast, 1px borders, hover washes, and the physical metaphor of a white page resting in a warm work area.

**The Hairline, Not Shadow Rule.** Separate stable regions with a tonal change or a 1px line; reserve overlays for native dialogs instead of lifting routine content into cards.

## Shapes

Controls use gently rounded corners (7px), list items use a slightly tighter radius (6px), and bordered panels or lists use 10px. Status labels use the same 10px value to read as compact pills. The A5 page remains a sharp rectangle, preserving the feel of real paper; rounding it would weaken the product metaphor.

## Components

### A5 Live Canvas

- **Structure:** white A5 paper centred inside a warm flexible well, inset by at least 28px.
- **Grid:** restrained warm-grey dot grid at 24px intervals.
- **Ink:** graphite paths with round caps and joins; stroke width responds to Huion pressure.
- **Ownership:** the widget maps and renders device-space points only. Hardware streaming and lifecycle remain in `HuionApplication`.

### Navigation

- **Structure:** fixed 224px sidebar with 12px horizontal insets and 4px vertical rhythm.
- **Default:** transparent, graphite text, left aligned, with 8px × 10px padding.
- **Hover / Focus:** warm neutral hover wash; a 1px focus ring remains visible for keyboard use.
- **Active:** selected neutral wash and semibold text, without a coloured rail or icon badge.

### Buttons

- **Primary:** graphite fill, white text, 7px corners, and 8px × 14px padding; use for the main immediate action such as Sync now.
- **Quiet:** transparent or muted text with the shared 8px × 10px control padding.
- **Destructive:** red text stays visually quiet until the user reaches a destructive context; native confirmation remains mandatory.
- **States:** hover uses a darker graphite fill for primary actions and Hover Wash for unfilled controls; focus uses the established 1px ring.

### Status Labels

- **Shape:** compact pill with 10px corners and 4px × 9px padding.
- **Connected / converted:** green text on the pale green wash.
- **Connecting / converting:** amber text on the pale amber wash.
- **Failed:** red text on the pale red wash.
- **Disconnected / synced:** muted graphite on a neutral wash.

### Note Rows

- **Structure:** full-width rows with 16px × 12px internal padding and a bottom hairline.
- **Content:** note title and timestamp lead; status and actions align to the trailing edge.
- **Behavior:** hover changes only the row surface. Available actions reflect note state and forward intent to the application boundary.

### Inputs / Fields

- **Style:** white fill, 1px warm-grey border, 7px corners, and 8px padding.
- **Focus:** preserve a visible native keyboard-focus indication.
- **Usage:** settings and markdown editing remain native dialogs, not custom card flows.

## Do's and Don'ts

### Do:

- **Do** keep the A5 page as the focal point of the live workspace.
- **Do** use warm neutrals, 1px separators, and compact native controls to establish hierarchy.
- **Do** reserve green, amber, and red for real state or risk.
- **Do** keep PySide6 responsible for rendering and intent forwarding while `HuionApplication` owns operational workflows.
- **Do** show destructive device clearing only in the relevant library context and retain native confirmation.

### Don't:

- **Don't** turn the product into a card dashboard, analytics grid, or collection of floating panels.
- **Don't** use semantic colours as branding, navigation accents, or decoration.
- **Don't** add decorative shadows, gradients, oversized radii, or glass effects.
- **Don't** move Bluetooth, sync, settings, note discovery, storage, or conversion logic into GUI widgets.
- **Don't** introduce a second typeface or icon system unless a concrete workflow cannot be expressed with the native control vocabulary.
