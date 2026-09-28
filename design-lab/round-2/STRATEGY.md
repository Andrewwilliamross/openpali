# OpenPali · a place with footnotes

Round 2 strategy, September 26, 2026. This is an internal creative judgment grounded in the repository and the first exploration. It is not resident research or an endorsement from the Palisades community.

## The thesis

**Make OpenPali feel like an independent Palisades field office: recognizably local, exact about sources, and welcoming to people who improve the record.**

The strongest signature is a folding public-record atlas. Its coastline and ridges establish a place; its notes establish a way of working. The pleasure comes from opening, following, annotating, and contributing. A small observing character can inhabit this world, but the world needs to work without the character.

Recommended first screen:

> **A place with footnotes.**
>
> Public evidence for the Palisades rebuild.
>
> **Explore on GitHub ↗**

The headline supplies personality. The sentence supplies meaning. The link supplies the next step. Artwork should do the remaining work.

## What we are actually communicating

| Reader | Real value | Design implication |
| --- | --- | --- |
| A resident or someone following the rebuild | Search a property, see what covered agency records document, and inspect the source and dates. | Show a relationship between a place and a record. Avoid a generic dashboard or a claim to know current conditions everywhere. |
| Someone who spots a discrepancy | A service-backed report path allows a person to review a correction; accepted corrections preserve the original history. | Make careful annotation feel welcome. An illustration must never pretend it has submitted or accepted a real correction. |
| A developer | Work on a map, source adapter, evidence model, release process, or accessible interface. Retained source bytes and versioned releases make traceability an engineering concern. | Let the identity include the actual tools of the project: source notes, separate lanes, citations, release editions, and useful small contributions. |

The product's unusual strength is **the distance it keeps between an observation and a claim**. Scheduled is not completed. Missing evidence is not inactivity. Conflicting sources remain visible. Five evidence lanes are not a progress ladder. This is more distinctive than describing the project as transparent.

The repository sources behind these claims are linked in the source notes below.

## Why the first round fell short

- **It changed the material more than the idea.** A P assembled from cubes, displayed on blue, rendered in acrylic, or implied by glass remained the same weak premise: a logo is the story.
- **It confused technical range with creative range.** CSS depth, Three.js, Blender, and generated imagery demonstrate production methods. They do not explain why this project needs to exist.
- **“Bring your square” was arbitrary.** The square came from GitHub aesthetics rather than a meaningful action in OpenPali. It could welcome contributors to almost any repository.
- **Optical transparency was an easy metaphor.** The product's meaningful transparency is a source, a date, an uncertainty, and a preserved revision. Glass expressed little of that.
- **The place was largely absent.** Removing “Palisades” from most compositions left a plausible generic developer startup. Locality cannot be recovered by adding more blue.
- **The best part was the editorial discipline.** Fieldnotes made the purpose legible. Retain that clarity, not necessarily its giant wordmark. Ledger began to explain the source relationship, but miniature floating cards weakened readability and risked looking like a production screenshot.
- **We optimized too many specimens before choosing a story.** Eight button treatments are useful after the concept is sound. They cannot supply individuality by themselves.

The next round must survive the unbranded test: cover the name and ask what remains specific to a local public-evidence project.

## Three distinct art and interaction directions

### 1. The living paper atlas — recommended

**Premise:** a place becomes easier to understand when its public record opens alongside it.

**Art direction.** An original, asymmetric folding atlas occupies the hero. White paper catches a soft, ordinary daylight shadow. Cobalt linework describes a coastal edge and branching canyon contours. A narrow citation tab projects from one fold. The atlas has an identifiable silhouette at poster scale; it is not a miniature application floating in space. Use a small set of measured lines rather than decorative topographic wallpaper.

If the drawing depicts actual geography, derive it from a checked source, record the extent and attribution, and review the simplification. The existing nearest-center neighborhood assignments are explicitly informal; they cannot become authoritative borders. Concept art may instead use an explicitly illustrative coastal terrain drawing. Neither version should depict rebuilding status, damage, individual homes, or invented parcel facts.

**Interaction.** A native “Unfold the atlas” control opens the same object into three connected panels: **place / observation / source**. A continuous blue leader connects the panels. These are conceptual labels, not three stages of recovery. Close returns to the compact composition. Keyboard and reduced-motion versions reveal the same content without dragging or animation. The GitHub link remains visible and unchanged.

**Minimal copy:** “A place with footnotes.” / “Public evidence for the Palisades rebuild.” / “Explore on GitHub.”

**Strength:** the geography and the evidence model become one memorable artifact. The fold, citation tab, linework, and paper edge all travel to other formats.

**Weakness:** a beautiful map alone could advertise a travel journal. The visible source relationship is essential. “Living” is the concept name, not a promise that a decorative hero is a live feed.

**Engineering cost:** moderate asset authoring; low runtime if a still or SVG supplies the first frame and a small local interaction controls the fold. Full WebGL is optional, not the concept. Actual geographic geometry adds a rights and derivation task.

### 2. The field notebook — an illustrated welcome

**Premise:** careful public work is done by people who notice, check, and leave useful notes.

**Art direction.** A purposeful blue-ink illustration shows a notebook opened beside a folded map, a pencil, and a citation slip. Use authored line weight, paper cut shapes, and a few deliberate imperfections. Let the notebook extend beyond its frame; do not arrange generic stationery into a centered icon pile. A small original coastal bird can recur as an observer turning a page or carrying a blank note. It must have a role in the composition, not become a cute proxy for displaced residents.

**Interaction.** “Turn the page” switches among three real kinds of contribution: **follow a source / improve the software / question a record**. Each page has a distinct small illustration and one plain sentence. All content remains available in the document without the interaction. Nothing suggests the visitor has made a contribution merely by clicking.

**Minimal copy:** “Leave a better record.” / “Maps, sources, and room to help.” / “Explore on GitHub.” The plain Palisades-purpose sentence must remain nearby.

**Strength:** naturally extends to contributor guides, release notes, stickers, and welcoming empty states. It offers character without making the data whimsical.

**Weakness:** a pelican, notebook, and blue palette can still be generic coastal merchandise. The artist needs a consistent drawing vocabulary and the source-checking actions. A large bird alone fails the brief as surely as the large P did.

**Engineering cost:** low browser cost; substantial illustration work. Multiple poses need a common model sheet and repeatable proportions. A small set of finished poses is better than many inconsistent generated variants.

### 3. The public-record press — participation as an edition

**Premise:** the shared record becomes more useful through careful, visible revisions.

**Art direction.** A flat, graphic print workshop: a cobalt impression, white paper, restrained ink misregistration, crop marks, a footnote block, and oversized readable type. The main composition is a sheet emerging from a simple printing frame. The distinctive object is a printed record with room in its margin. This direction uses bold two-dimensional print design, not another 3D hero.

**Interaction.** “Add the note” changes a clearly labeled illustrative sheet from an original statement to an annotated edition. The original remains visible; a leader and margin note show the addition. “Show original” reverses the local view. There is no score, confetti, fictitious submission, or fabricated recovery event. Use a harmless editorial example, such as explaining that an observation date and publication date differ.

**Minimal copy:** “Make the next edition clearer.” / “Public evidence. Visible sources.” / “Explore on GitHub.”

**Strength:** gives releases, source adapters, documentation changes, and contributor credits a strong shared visual language. Especially good for social cards and physical print.

**Weakness:** heavy distress or faux official stamps would make the project feel antiquated or governmental. It must retain contemporary type and an explicit independent identity. Edition language must not imply a published release that does not exist.

**Engineering cost:** low runtime with HTML/SVG and a local state toggle. The effort is in art direction, responsive typography, and producing a convincing print texture that compresses well and never obscures text.

## The selected family: field office + atlas

The current working direction combines the atlas's central artifact with the notebook's human welcome. **The atlas leads; the bird participates.** The print workshop remains a distinct alternative, rather than a third visual style to mix into every screen. This is a creative decision for the next implementation, pending the project owner's judgment of the actual artwork.

“Field office” names the creative world, not a government body, staffed public office, or physical service. Avoid official seals, civic uniforms, invented postal addresses, and badges of authority.

Use one disciplined system:

- White paper, cobalt ink, dark readable text, and a restrained pale-blue wash.
- The same coastal drawing and fold geometry in every atlas depiction.
- One citation-tab shape, one leader-line style, and a consistent bracketed footnote vocabulary.
- A readable wordmark; small mark studies can follow once the principal art works.
- A small bird with a limited set of actions: observe, carry a source note, and help at the notebook. No rescue costume, construction victory, or emotion assigned to a property.
- Short human language. Keep the public evidence explanation close to the poetic headline.

### How the identity travels

| Surface | Expression | Useful content |
| --- | --- | --- |
| One-button website | Folded atlas hero; quiet bird within the scene; one actual outbound GitHub CTA. Optional local art control. | Headline and exact Palisades-purpose sentence. Avoid fake map search or other controls that resemble an available product. |
| GitHub README | Wide atlas masthead, restrained type, three small illustrated role panels. | What it does, the source/uncertainty principles, first developer command, then deeper documentation. Useful text stays Markdown. |
| Social | Crop the same atlas or one role illustration; blue field or white paper, one short headline. | A real shipped change, source-method note, or contributor credit. No invented adoption statistics or recovery percentages. |
| ASCII | A compact folded sheet/coastal-bird outline with a bracketed note marker. | `openpali` and a short purpose line in ordinary monospaced characters. Keep it optional. |
| Stickers | Atlas silhouette, citation tab, small bird action, or “A place with footnotes.” | One-color versions that remain legible without tiny annotations. Do not require a QR code to understand them. |
| Contribution guide and release notes | The same note markers, rules, and small role artwork. | Concrete work and real acknowledgments. Keep humor away from property evidence and resident circumstances. |

## Copy decisions

**Use:** “A place with footnotes.” / “Follow the source.” / “Small fixes count.” / “Help make the record clearer.” / “Public evidence for the Palisades rebuild.”

**Use carefully:** “Know what's taking shape” is appealing but may imply current physical visibility the records cannot guarantee. “Good neighbors. Open records.” introduces a moral tone that the product deliberately avoids when interpreting residents' actions. Neither should lead this round.

**Retire:** “Bring your square,” recovery-as-progress slogans, “nothing to hide,” “every record,” unqualified “live,” and “open source” while the source-code license remains undecided.

## Acceptance criteria for the actual design

1. **Specificity:** the hero contains a recognizable relationship between place and public record. A monogram or generic premium object cannot carry the concept.
2. **Immediate purpose:** at 390 × 844 and 1440 × 900, the initial view includes OpenPali, the Palisades-purpose sentence, and a clear GitHub action. The scene must not push meaning below the fold.
3. **One coherent world:** the website, README banner, three role panels, square social card, and one-color sticker look like the same project before adding the name. Character proportions and atlas linework agree.
4. **Honest art:** any geographic drawing is sourced or visibly illustrative. No fake addresses, milestones, dates, boundaries, badges, usage figures, or official endorsement. No disaster spectacle.
5. **Useful play:** the interaction reveals a relationship or changes a local illustration. It does not award recovery points, imply public submission, or require a puzzle before the GitHub link works.
6. **Accessible reading:** essential copy is actual text; controls have keyboard equivalents and visible focus; reduced motion has the same information. Contrast, narrow layouts, enlarged text, and decorative overlap receive visual checks.
7. **Resilient delivery:** the first frame is a complete composition with JavaScript disabled. Animation stops when idle. Optimize measured assets before adding a 3D runtime; record the final download cost rather than guessing it.
8. **Practical portability:** export a static README banner, social crops, transparent role assets, a simple monochrome mark, and an ASCII version from the chosen system. Preserve editable source files and provenance.
9. **Real critique:** review full-size desktop, mobile, and small social crops. Ask whether the art feels like a place people work together, whether its source relationship is clear, and whether the bird adds meaning. If it merely makes the page cute, remove it.

## Reference and source notes

[Cua's official brand page](https://cua.ai/branding) distinguishes a small koala mark, full lockup, larger illustrated character, and display/body/technical typography. Its useful lesson here is a character and visual language with multiple jobs. OpenPali needs its own world and actions; copying the animal-led formula is not sufficient. The [Cua homepage](https://cua.ai/) also grounds the identity in concrete computer-use surfaces. These observations were checked September 26, 2026.

The earlier [Omarchy, Prime Agent, and GeoLibre research](../../Docs/Brand/REFERENCES.md) remains useful for continuity across GitHub, web, and community surfaces. It does not justify borrowing their art.

Repository sources: [README](../../README.md), [frontend guide](../../web/README.md), [methods](../../web/src/pages/MethodsPage.tsx), [property detail](../../web/src/components/spatial/ParcelDetailCard.tsx), [correction form](../../web/src/components/spatial/CorrectionForm.tsx), [status](../../web/src/pages/StatusPage.tsx), [observation model](../../pipeline/openpali/domain/observations.py), [identity model](../../pipeline/openpali/identity/ids.py), [terrain rendering](../../web/src/components/MapView.tsx), and [informal neighborhood assignments](../../pipeline/palisades/neighborhoods.py).
