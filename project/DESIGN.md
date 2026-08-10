# Design System: Local LLM Conversation Gateway

## Direction Contract

The client behaves like a modern language-model instrument bench. The transcript is the central working surface; a narrow thread rail and a compact telemetry rail expose persistence, provider, context, and stream state. Light neutral work surfaces support long classroom sessions under normal room lighting. Ink, signal green, cobalt, and amber carry distinct functional roles. Controls use familiar icons and direct labels. Motion is limited to the live token cursor and state transitions. Responsive layouts preserve the transcript first, then collapse diagnostic rails into inspectable bands.

## Mode

Operate. Students use this page repeatedly to send, stop, inspect, and compare requests.

## Palette

- `paper`: `#f5f7f8`
- `surface`: `#ffffff`
- `ink`: `#182022`
- `muted`: `#59666a`
- `line`: `#cbd4d6`
- `signal`: `#147d64` for ready and completed states
- `cobalt`: `#2457c5` for primary actions and live data
- `amber`: `#a65b00` for warnings and compaction
- `danger`: `#b42318` for errors and destructive actions

Color never carries state alone; every state includes text or an icon.

## Typography

Use the native system UI stack for controls and prose. Use the native monospace stack only for IDs, durations, token counts, and protocol events. Letter spacing is always `0`.

## Composition

- Desktop: fixed thread rail, flexible transcript, fixed diagnostic rail.
- Tablet: thread rail plus transcript; diagnostics become a horizontal strip.
- Mobile: transcript leads; threads and diagnostics open as full-width sections.
- Messages are unframed transcript rows, not nested cards.
- Individual metric readouts may use compact bordered cells with stable dimensions.

## Controls and State

- Primary command: send message.
- During streaming, send becomes stop and the composer is disabled.
- Thread creation, deletion, and refresh use familiar icons with tooltips.
- Empty, loading, disconnected, ready, streaming, cancelled, and error states have explicit copy.
- All interactive elements have visible keyboard focus and minimum 40px touch targets.

## Motion

The only continuous motion is a low-key live cursor during streaming. Panel transitions use short ease-out changes and are removed under `prefers-reduced-motion`.

## Content Rules

Interface copy names the state and next action. Technical detail is shown because inspection is the teaching purpose, but explanatory marketing copy is excluded from the app.
