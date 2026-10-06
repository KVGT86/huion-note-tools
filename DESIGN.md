---
name: HuionNote
description: A quiet paper-and-graphite workspace for saved notes and live notebook sharing.
colors:
  graphite-ink: "#25231F"
  graphite-muted: "#625F59"
  graphite-hover: "#11100E"
  graphite-disabled: "#817E78"
  paper-guide: "#D4D1CA"
  paper: "#FFFFFF"
  warm-paper: "#F7F6F3"
  hover-wash: "#EEEDE8"
  hairline: "#E3E1DC"
  focus-ring: "#9C9A94"
  selected-wash: "#E8E6E1"
typography:
  title:
    fontFamily: "system sans-serif"
    fontSize: "21px"
    fontWeight: 600
  brand:
    fontFamily: "system sans-serif"
    fontSize: "17px"
    fontWeight: 600
  body:
    fontFamily: "system sans-serif"
    fontSize: "14px"
    fontWeight: 400
  metadata:
    fontFamily: "system sans-serif"
    fontSize: "12px"
    fontWeight: 400
rounded:
  control: "6px"
spacing:
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.graphite-ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.control}"
    padding: "7px 10px"
  navigation-active:
    backgroundColor: "{colors.selected-wash}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.control}"
    padding: "7px 10px"
---

# Design System: HuionNote

## Overview
**Creative North Star: "Notion for Huion"**

A restrained native workspace in warm paper and graphite. Saved documents lead; the live notebook becomes the focal object when sharing. Familiar controls, readable typography and contextual actions carry the product's richness.

**Key Characteristics:**
- Warm neutral surfaces, precise hairlines and no decorative shadows.
- Searchable document list beside a large vector preview.
- Native font family with a compact, legible hierarchy.
- Minimal page-only presentation mode.

## Colors
Graphite is the primary ink and action colour. White is paper; warm paper surrounds documents. Selection and hover use tonal washes. Operational messages use plain language; colour never carries meaning alone.

**The Paper Before Paint Rule.** Use the established neutral palette before adding a hue.

## Typography
Use the native system sans-serif family. Titles use 21px/600, brand 17px/600, body 14px and metadata 12px. Set native fonts through Qt rather than unsupported CSS font stacks.

## Layout
The default window is 1280×820 and the minimum is 860×580. A 196px sidebar anchors the shell. A resizable document-list/preview splitter adapts to available space. Content margins follow a 24px rhythm; document geometry maintains its aspect ratio at every zoom.

## Elevation & Depth
Flat surfaces. Tonal separation and one-pixel hairlines establish depth. No shadows.

## Shapes
Six-pixel control corners and rectangular paper. Native dialogs remain conventional; lists are compact document rows rather than cards.

## Components
### Navigation
Notes is the opening workspace; Live notebook is the second destination. Settings and Activity stay near the sidebar foot.

### Document workspace
Search, status filtering and multiselection sit above a document list. Selected handwriting renders as vectors. Transcript reading and side-by-side editing use tabs. Batch export and transcription remain contextual.

### Live notebook
Plain, ruled or dotted paper; fit page, fit width, zoom and pan. Pressure changes locally along smooth stroke outlines. Completed geometry is cached. Single-point marks remain visible.

### Presentation
F11 hides navigation, controls, activity and device identity. Escape restores the normal workspace. Connection changes never erase the page.

### Controls and feedback
One graphite primary button leads sync. Quiet secondary actions share six-pixel corners. Keyboard focus remains visible. Long operations show progress and clear results; failures explain recovery.

## Do's and Don'ts
- Do preserve the paper-and-graphite identity.
- Do render documents as vectors and keep raw samples unchanged.
- Do keep backend operations outside Qt widgets.
- Do protect edits, drafts and existing exported files.
- Don't expose implementation jargon in everyday workflows.
- Don't add decorative cards, gradients, glass or shadows.
- Don't put device identifiers or logs into presentation mode.
