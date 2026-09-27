# 01 — Fieldnotes

**Thesis:** Make OpenPali feel like a carefully edited civic journal: confident type, generous margins, and a quiet invitation to contribute.

## Strongest

- The enormous broken wordmark is the composition, so the identity survives without a hero illustration.
- Fine rules, small folios, and the serif closing phrase give the same blue-and-white palette an editorial character.
- The GitHub action is a single ruled row with a vivid arrow tile. It is easy to find without turning the whole page into a button advertisement.
- “Read the margin” opens a genuine annotated state, with an explicit accessible expanded/collapsed control.

## Weakest

- This is a brand introduction, not an explanation of the actual map product. A future product demonstration needs a second surface.
- The large lowercase wordmark depends on disciplined type spacing. It will need another visual check if a custom typeface replaces the system font.
- The tiny folio is atmospheric; no essential instruction should ever be placed there.

## Self-critique → revision

The first desktop pass had overly tight wordmark kerning; the mobile heading also joined words when line breaks disappeared. The revision loosens the mark, preserves spaces across responsive breaks, and tightens the mobile bottom margin. The serif phrase now has more breathing room below the mark on desktop.

## Engineering cost

**Low.** One self-contained HTML file, inline CSS, a small local toggle, no assets or dependencies. Natural document flow handles mobile and enlarged text. The margin note adds ordinary page height when open. System fonts, visible focus, a named heading, and reduced-motion handling are built in.

## Checked

- Desktop: 1440 × 900; mobile: 390 × 844.
- One real anchor, pointing to the canonical project repository.
- Margin toggle opens and closes through a native button.
- No horizontal overflow at the target sizes.
- No data values, fabricated records, or adoption claims.

**Files:** `index.html`, `desktop.png`, `mobile.png`. Initial screenshots retain the first pass for comparison.
