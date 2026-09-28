# Field Office / component board

A live design study with four GitHub links and two fictional evidence examples. The page is written in HTML, CSS, and a small JavaScript enhancement. It uses the local Fraunces and DM Sans fonts. It is separate from the production application.

## Four invitations

| Variant | Behavior | Best use | Tradeoff |
| --- | --- | --- | --- |
| Folded corner | Lifts on hover, compresses on press, keeps a small paper fold. | Primary project CTA. Matches the selected website direction. | The strongest contrast; use sparingly. |
| Source tab | A slightly rotated document straightens and lifts. | A repository or document invitation within the Field Office world. | “Source” needs its GitHub repository label to distinguish code from evidence. |
| Print stamp | Straightens on hover and fills with cobalt under pressure. | Small marketing and printed moments. | A stamp can imply official endorsement. Keep it out of evidence-verification status. |
| Editorial line | The underline gains weight; the arrow moves and footnote turns. | A quieter invitation within editorial content. | Less prominent than a filled button. |

All four are real anchors to the canonical repository and use `target="_top"` so they work when the board is embedded in the review gallery. The state radio group previews Live, Hover, Focus, and Pressed. Previews do not disable the links. Actual pointer and keyboard styles also work independently.

## Two useful details

**Source disclosure.** A native `details` control reveals a fictional source, quoted example text, and a citation-copy button. The copied text begins with an explicit illustrative-example label. A status message reports successful copying or a manual-copy fallback.

**Accepted correction and history.** The current date is shown beside the earlier value. A native disclosure reveals both version 2 and the original version 1, with separate publication and acceptance labels. This is an illustrative accepted state; it does not submit a correction or imply a production approval workflow.

## Review and revisions

### Pass 1: desktop

Inspected the actual page at 1440 pixels wide. The first folded-corner sample was too small relative to the other variants. Restored the production CTA dimensions. The evidence examples also had slightly different header and fact-row heights; aligned those rows so the source and correction read as related components. Increased the fictional-record disclosure and card captions.

### Pass 2: mobile and interactions

Inspected the 390-pixel page with details closed and open, plus a 320-pixel layout. The optional introductory aside touched the large heading on the first phone capture. Hid that repeated introductory copy on phones; the four card names convey the same information. Reduced the editorial link size slightly at 320 pixels to retain side clearance.

Verified in Chrome:

- Arrow keys change the native preview radio group and update the selected visual state.
- Tab moves from that group to the primary GitHub link with visible keyboard focus.
- Enter on the GitHub anchor opens the canonical repository.
- Enter on each native summary opens its source or history details.
- Both disclosures can stay open together for comparison.
- Citation copying returns “Example copied.”
- All four preview states update correctly.
- Reduced motion sets all link transition durations to zero.
- Both local fonts load.
- All four repository anchors use `_top`.
- No horizontal overflow at 320 or 390 pixels; the 1440-pixel board fits its fixed content width.
- JavaScript syntax and whitespace checks pass.

The first keyboard test targeted the text span within a summary, leaving focus on the repository link. That test correctly navigated to GitHub. The disclosure checks were then rerun against the actual native `summary` elements and passed.

## Artifacts

- `desktop.png`: 1440 × 1000, complete board.
- `mobile.png`: 390 × 1726, phone board.
- `desktop-expanded-focus.png`: both details open, focus preview.
- `mobile-expanded.png`: both details open on a phone.
- `mobile-320.png`: narrow-phone inspection.
- `buttons.png`: 1160 × 272, actual button-section crop for the deck.
- `evidence.png`: 1160 × 482, actual expanded evidence-section crop.
- `buttons-hover.png` and `buttons-pressed.png`: state crops.

## Remaining design judgment

Use the folded corner as the default invitation. Source tab and editorial underline give the system quieter ways to link without inventing another primary button. The stamp is a deliberately narrow accent. Putting all four into one production screen would weaken hierarchy.

The illustrative evidence examples demonstrate provenance and visible history. Before adapting them to the application, map the labels and available dates to the actual contract, including unknown values and rejected or pending corrections. The sample is intentionally small and makes no claim to implement those states.
