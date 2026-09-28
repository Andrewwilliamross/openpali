# 02 — Ledger

**Thesis:** Turn traceability into a tactile interface: unfold translucent evidence sheets and bring a source, observation, or release into focus.

## Strongest

- The material metaphor belongs to this project. Depth represents the relationship between evidence layers rather than a decorative floating card collection.
- Three working tabs change the active sheet; a continuous depth control changes the stack's spacing and Z distance.
- White sheets, blue edge lines, muted rear content, and restrained shadows create transparency without photographic or generated illustration.
- The active record remains readable on mobile, and every layer is explicitly marked illustrative.

## Weakest

- This is the most visually technical of these two directions. Some visitors will explore the component before noticing the contribution invitation.
- Sheet details are necessarily small on mobile. Actual property records would need an expanded reading view, not just this introduction-sized stack.
- The perspective is best understood on a desktop display; mobile preserves the mechanism but reduces its spatial drama.

## Self-critique → revision

The first pass wrapped the middle tab, gave the rear sheets too much visual weight, and placed the first two evidence layers in the wrong visual order. The revision keeps tab labels on one line, dims inactive sheet contents, orders source → observation → release in the initial stack, and tightens mobile geometry to fit the target viewport. Mobile headings retain intentional line breaks. Active panels also receive keyboard focus. Peer review then prompted qualitative spacing labels, larger mobile table text, a gentler mobile reading angle, and a fully flat state at zero spacing.

## Engineering cost

**Moderate.** Self-contained HTML/CSS/JS with no package dependencies. CSS perspective and transformed sheets need a local stacking context; one explicit active index sets depth and stacking order. ResizeObserver recalculates offsets, and the range control changes them without reloading. Backdrop blur has an opaque-white fallback. A production version should be checked across Safari/Firefox and lower-power devices.

## Checked

- Desktop: 1440 × 900; mobile: 390 × 844; no horizontal overflow.
- Tabs: click, Left/Right arrows, Home/End, roving tabindex, selected state, and one exposed active panel.
- Range: Home = 0, End = 100; visible and accessible values describe qualitative sheet spacing (Stacked, Close, Open, Spread), not an evidence metric.
- Reduced motion removes transitions (`0s` verified).
- One actual GitHub link. Card contents are labeled illustrations with no live data.

**Files:** `index.html`, `desktop.png`, `mobile.png`. Initial screenshots retain the first pass for comparison.
