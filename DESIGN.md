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
  warm-paper: "#F2F1ED"
  hover-wash: "#EEECE6"
  hairline: "#D6D3CC"
  control-border: "#B8B3AA"
  control-hover: "#81796B"
  focus-ring: "#786995"
  selected-wash: "#E4DEF0"
  selected-text: "#51445F"
  quiet-hover: "#E4E1DA"
  pressed-wash: "#DEDAD2"
  menu-border: "#A6A198"
  destructive-ink: "#912D27"
  destructive-border: "#D6B6B1"
  destructive-wash: "#FAEDEB"
  focused-text: "#57466F"
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
    fontSize: "13px"
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
    padding: "8px 12px"
  navigation-active:
    backgroundColor: "{colors.graphite-ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
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
Graphite is the primary ink and action colour. White is paper; warm paper surrounds documents. Active navigation is graphite with white text. A muted lavender from the supplied logo marks document selection and keyboard focus. Operational messages use plain language; colour never carries meaning alone.

**The Paper Before Paint Rule.** Use the established neutral palette before adding a hue.

## Typography
Use the native system sans-serif family. Titles use 21px/600, brand 17px/600, body 14px and supporting copy 13px. Page rows use a 14px/600 title above 12px metadata. Placeholder text uses the fully opaque muted ink, not Qt's default half-opacity. Set native fonts through Qt rather than unsupported CSS font stacks.

## Layout
The default window is 1280×820 and the minimum is 860×580. A 196px sidebar anchors the shell. A resizable document-list/preview splitter adapts to available space. Content margins follow a 24px rhythm; document geometry maintains its aspect ratio at every zoom.

## Elevation & Depth
Flat surfaces. Tonal separation and one-pixel hairlines establish depth. No shadows.

## Shapes
Six-pixel control corners and rectangular paper. Qt Fusion supplies consistent native widget behaviour across Linux themes. Dialogs use the same control styling as the main workspace. Page rows remain compact documents, not decorative cards.

## Components
### Navigation
Notes is the opening workspace; Live notebook is the second destination. Icon-led Settings and Activity utilities stay near the sidebar foot. Version information belongs in Settings, not the navigation shell.

### Document workspace
Search, status filtering and multiselection sit above a document list. Selected handwriting renders as vectors. Transcript reading and editing use underlined active tabs. A cleared selection shows an explicit empty preview instead of the previous page. Batch export and transcription remain contextual.

### Live notebook
One toolbar groups page navigation and paper guides on the left, save/new-page icons and Present on the right. Plain, ruled or dotted paper; fit page, fit width, zoom and pan. Pressure changes locally along smooth stroke outlines. Completed geometry is cached. Single-point marks remain visible.

### Status footer
A full-width, hairline-separated Qt status bar anchors the shell. Bluetooth state and reconnect sit on the left; operation results occupy the flexible middle. Live draft state, fit and zoom controls sit on the right. Persistent instructions move into tooltips; draft state reports only what has actually happened. Saved-page browsing is distinguished from the active draft.

### Icons
One authored 24-unit outline family with 1.7-unit strokes, rendered at 18px for 1×–3× scaling. Tool buttons have at least 32px targets, named tooltips, accessible names and visible keyboard focus. Icon-only controls cover familiar view and document operations; Present, Activity and Settings keep their text labels.

### Presentation
F11 hides navigation, controls, activity and the entire status footer, including device identity. Escape restores the normal workspace. Connection changes never erase the page.

### Controls and feedback
One graphite primary button leads sync. Secondary actions have visible control boundaries; navigation utilities remain quiet. Dropdowns use authored vector chevrons and styled list popups with 40px rows, not platform-default menu delegates. Checkboxes, radio choices, menus and scrollbars share the palette. Keyboard focus remains visible. Long operations show progress and clear results; failures explain recovery.

### Interface language
Use pages for the saved objects, Notes for their library, and transcript for editable text. Prefer literal actions and outcomes: Sync notebook, Export, Transcribe, Edit transcript, Save changes. Status labels name transcription state rather than ambiguous readiness. Dialog confirmation buttons name the next action, including Choose folder and Erase notebook memory. Avoid taglines, implementation jargon and unsupported claims.

## Do's and Don'ts
- Do preserve the paper-and-graphite identity.
- Do render documents as vectors and keep raw samples unchanged.
- Do keep backend operations outside Qt widgets.
- Do protect edits, drafts and existing exported files.
- Don't expose implementation jargon in everyday workflows.
- Don't add decorative cards, gradients, glass or shadows.
- Don't put device identifiers or logs into presentation mode.
