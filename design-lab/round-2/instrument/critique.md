# Three Dates / the record room

## The idea

Make a defining OpenPali distinction into something a visitor can operate. One fictional event occurs on May 3, becomes observable on May 14, and appears in a May 16 release. Advancing the reader keeps the earlier dates in view. The source slip emerges as the record becomes available.

The scene is an archival instrument: an inset viewfinder, a three-position selector, a cobalt dial, countersunk screws, and a paper output slot. Its pleasure comes from discovering what the object does. This is an original HTML/CSS composition with CSS perspective and JavaScript state; it uses no Three.js, Blender render, generated image, or borrowed character art. It shares the local DM Sans font with the primary direction.

## Why this belongs to OpenPali

The interaction explains evidence history and avoids turning a delayed observation into the date an event occurred. That is a concrete civic-data concern. The original event date remains stable; unobserved and unpublished dates remain unknown until their corresponding stages. Every visible record is explicitly fictional. The illustration names no property, person, permit, or actual disaster milestone.

The source slip is a recurring visual device: it could carry citation, correction, and release-note illustrations across documentation. A single GitHub link remains the destination. The other controls operate the example.

## Visual review, pass 1

Inspected the rendered desktop page at 1440 × 1000, then the phone page at 390 pixels wide.

Found:

- An incorrect gradient color created an intense yellow reflection across the viewfinder.
- The first paper-layer implementation let the hidden slip cross the explanation inside the reader.
- The fictional-record label was too small on mobile.

Changed:

- Replaced the reflection with a faint transparent white band.
- Added a clipped paper-output area below the enclosure. The slip now emerges from a real visual slot and stays clear of the controls.
- Gave the fictional-record label its own full-width row on mobile and increased it to 8 pixels.

## Visual review, pass 2

Inspected the settled published state on desktop, mobile at 390 pixels, and a narrow 320-pixel viewport. Reviewed the actual date and control states in the browser.

Changed:

- Replaced the default round range thumb with a small ridged metal selector carrying a cobalt index line.
- Enlarged the essential mobile date labels, notes, explanation, and stage controls.
- Reserved room beside the mobile invitation for the paper slip, with the GitHub button below it.
- Compressed desktop spacing on viewports under 950 pixels high so the GitHub button fits a 1440 × 900 viewport.
- Kept the small stage number on one line at 320 pixels.

Verified:

- Event: `03 / unknown / unknown`.
- Observed: `03 / 14 / unknown`.
- Published: `03 / 14 / 16`.
- Arrow keys advance the native range control; buttons expose their selected state with `aria-pressed`.
- The changing explanation uses a polite live region; the range has a meaningful spoken value.
- Exactly one link points to the canonical GitHub repository.
- No horizontal overflow at 320, 390, or 1440 pixels.
- Local DM Sans loads successfully.
- Reduced-motion CSS removes transition and date-roll animation.
- JavaScript syntax and whitespace checks pass.

Final screenshots: `desktop.png` (1440 × 937 full page, captured with a 1440 × 900 viewport), `mobile.png` (390 × 1077 full page), and `mobile-320.png` (narrow keyboard-focus check). Earlier pass images are retained as review evidence and are not the final gallery previews.

## Candid tradeoffs

This is the most precise of the three proposed stories, and the least emotionally generous. It communicates disciplined record handling quickly. It does less to communicate a neighborhood, a community, or a contribution culture. The primary field-office scene should lead if the goal is a recognizable public world; this instrument can support documentation and technical explainers.

The physical detailing creates a particular point of view, but miniaturized labels still function as texture. Essential facts also appear in the heading, three named windows, and plain-language explanation. A full public product should not use tiny instrument labels as its only instruction.

The displayed dates form a deliberately simple example. Real source history can include corrections, repeated observations, multiple event dates, and missing dates. This illustration does not model that entire data system.

The paper slip represents source retention; it is not a citation preview and should never be mistaken for proof. Its fictional-record label and example-only marking remain part of the design.
