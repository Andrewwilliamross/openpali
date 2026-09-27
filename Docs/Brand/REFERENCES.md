# OpenPali — reference study and creative brief

Research date: September 26, 2026. These are observations of the linked public
pages at the time of review, followed by original proposals for OpenPali.
Reference projects retain their names, marks, artwork, and copy. None should be
reused as OpenPali assets.

Implementation decisions and completion status live in [PLAN.md](PLAN.md). The
[brand guide](README.md) contains the selected mark, palette, and final assets;
proposals below record the exploration rather than superseding that guide.

## The direction

Give OpenPali the care and energy of a project people want to help build:
a recognizable mark, a useful README, a small and memorable website, and a
welcoming path to a first contribution. The organizing idea is **an open square**:
a small unit of evidence that becomes more useful when connected to others.

The white-and-blue palette and square grid can connect developer culture to
OpenPali's map and records without turning the recovery of a community into a
game. Transparency has two jobs: restrained visual layers, and language that
makes the source and limits of a claim clear.

## What the references teach us

| Reference | Observed presentation | Useful lesson for OpenPali |
| --- | --- | --- |
| [Omarchy website](https://omarchy.org/) | A short promise, obvious entry points, demonstrations, themes, community work, and a consistent voice across the page. The site itself can wear the product's themes. | Make the identity something a visitor experiences. Use a small square interaction and a memorable invitation to build. The first screen must explain the project and lead to its GitHub repository. |
| [Omarchy repository](https://github.com/omacom/omarchy) | A compact introduction gives way to a structured manual. SVG, PNG, and text identity files live alongside the code. | Give the README a clear route to deeper documentation. Ship a real kit, including a text mark, instead of making the banner the only branded surface. |
| [Omarchy brand page](https://omarchy.org/brand/) | Separate logo and wordmark downloads are available in vector and raster formats. Brand rights are stated explicitly. | Supply reusable source assets, useful export sizes, and short usage instructions. Keep branding rights distinct from code and data licensing. |
| [Omarchy branding manual](https://github.com/omacom/omarchy/blob/quattro/manual/41-branding.md) | Identity reaches boot, screensaver, and about surfaces. The manual exposes text art as something users can edit. | An ASCII mark and small contributor-facing details can make the project feel owned and lived in. They must remain optional and legible. |
| [Omarchy doctrine](https://omarchy.org/doctrine/) | An explicit set of principles connects project taste, craftsmanship, participation, and fun. | Publish a few OpenPali-specific commitments: trace claims, preserve unknowns, make corrections easy, and welcome careful work. Write our own inclusive community expectations. |
| [Prime Agent README](https://github.com/PrimeIntellect-ai/prime-agent) | A centered identity, light/dark image sources, compact navigation and status badges precede a clear explanation and installation path. Contribution and security routes are visible. | Put the visual introduction, purpose, and first useful developer action close together. Use a few truthful badges and make every link earn its place. |
| [Prime Agent brand assets](https://github.com/PrimeIntellect-ai/prime-agent/tree/main/assets/brand) | The repository includes SVG variants of its butterfly mark. | Keep our mark editable, portable, and usable on light or dark backgrounds. |
| [GeoLibre README](https://github.com/opengeos/GeoLibre) | Specific capabilities are followed by screenshots, animations, live project links, guides, and contribution routes. Technical components are named. | Show what the software does with a verified product image or clearly labeled schematic. Give developers enough architecture and setup detail to decide where they can help. |

### Synthesis

The shared strength is a complete path: recognize the project, understand it,
see evidence that it works, and find a way in. For this release, OpenPali's
website should remain the requested one-button invitation. The GitHub README
can carry the fuller technical story. Future demos and community showcases can
grow from actual releases and contributions.

## Original identity proposal

### Mark and visual vocabulary

- **Mark:** a geometric open square built from a small grid, with one clear
  opening. It should read at favicon size and work in one color. Explore a
  subtle lowercase `p` through the negative space only if small-size legibility
  survives.
- **Wordmark:** lowercase `openpali` for the designed lockup; `OpenPali` in prose.
  Give it generous spacing and a simple, durable silhouette.
- **Grid:** square cells at a steady interval, inspired by contribution graphs.
  Use them as a decorative field or abstract map, with a few blue cells giving
  rhythm. A decorative grid must never imply a count of homes or a recovery
  percentage.
- **Transparency:** pale blue overlays and visible grid lines can suggest
  connected records. Keep text on solid, high-contrast surfaces. Avoid visual
  effects that obscure the content.
- **Shapes:** precise squares, thin rules, open corners, and generous white
  space. A tiny offset square or cursor supplies personality.
- **Typography:** one clear sans-serif for prose and display; a monospace face
  for code, small labels, and the ASCII companion. Use licensed local fonts or
  system fallbacks; do not make a network font request necessary to render.
- **Motion:** one brief square assembly on the landing page, with a static
  reduced-motion version. Keep the GitHub hero static and instantly readable.

Suggested starting palette; implementation should verify contrast in context:

| Role | Color | Use |
| --- | --- | --- |
| Paper | `#FFFFFF` | Main canvas |
| Ink | `#102A43` | Body and display text |
| Pali blue | `#155EEF` | Primary action and mark |
| Deep blue | `#123CA6` | Hover state and emphatic text |
| Pale blue | `#EAF2FF` | Supporting panels and grid cells |
| Grid | `#D6E5F7` | Decorative rules and open cells |

These colors establish the brand; they do not redefine the product's evidence
lane colors or introduce a new status scale.

### Three candidate taglines

1. **Build a clearer picture.** Recommended for the hero: an invitation to
   contribute, with a plain subtitle explaining the product.
2. **Every record. A clearer picture.** A more evidence-led option for social
   cards and a documentation cover. Use it as an aspiration, never as a claim
   of complete source coverage.
3. **Open records. Shared understanding.** The calmest option for civic and
   research audiences.

Recommended descriptive line: **Public evidence for the Palisades rebuild.**
Follow it with a concrete sentence about cleanup, design review, permitting,
construction, and occupancy evidence. The tagline must not carry that whole
explanation by itself.

## Tone: human, precise, and inviting

Fun belongs in the act of building and understanding software. The people and
properties represented by the platform deserve calm, respectful language.

| Surface | Suitable tone and content | Keep out |
| --- | --- | --- |
| README introduction | Direct purpose, a little optimism, specific developer invitation | Claims that software will solve recovery by itself |
| Contributor guide | “Small fixes count.” Clear setup, examples, credit, and review expectations | Insider jokes that make first-time contributors feel unwelcome |
| Brand/site details | A square that snaps into place, an ASCII mark, a friendly footer | Flashing effects, automatic sound, unreadable text art |
| Property and evidence views | Dates, sources, uncertainty, correction routes | Jokes about loss, owner behavior, blame, or recovery speed |
| Release notes and social cards | Celebrate a shipped capability and thank contributors | Unverified adoption numbers, invented testimonials, dramatic disaster imagery |

Use short, ordinary sentences. Prefer “the record documents” to “we know.”
Celebrate better evidence and easier contribution. Treat “unknown” as useful
information, never as a failure or an empty progress bar.

## Product claims audit

The current [root README](../../README.md) describes the intended evidence
model. Copy should remain consistent with it, and deployed behavior must be
verified before it is used as proof in launch materials.

| Claim or implication to avoid | Safe direction / evidence needed |
| --- | --- |
| “Open source” or an MIT/Apache badge before a license exists | The repository currently states that licensing is undecided and grants no license. Use “public project” and make licensing status visible until the owner decides. |
| “Live,” “real-time,” “complete,” or “every property covered” | Name the published snapshot, source coverage, and observation dates that support the statement. |
| A rebuild score, percentage complete, ranking, or countdown for a property | Show the separate evidence lanes and the source events supporting them. |
| Missing public evidence means nothing happened | Say “no public evidence” and preserve the distinction between observation and reality. |
| An event is current because it was fetched recently | Keep event time, observation time, and publication time distinct. |
| Guaranteed permit timing or recovery predictions | Describe only the reviewed batch estimate behavior, including suppression when evidence is insufficient. |
| A decorative parcel/grid graphic is a real map or current dataset | Label it as an illustration or schematic; avoid actual addresses in invented records. |
| “Production ready,” “fully secure,” or “all checks passing” | Link a dated, relevant verification result with its actual scope. |
| Government endorsement, official status, or data ownership | Describe the project as independent and preserve source attribution and usage terms. |
| Every image or government-hosted asset is freely reusable | Keep rights review and data licenses separate from the software license. |

### Documentation inconsistency found during research

At the initial audit, [pipeline/README.md](../../pipeline/README.md) described the retired
0–100 rebuild score and score-tinted exports. That conflicted with the root
README's evidence model. It has been rewritten during this launch to describe
the current platform and explicitly identify retained legacy code. The preserved files in `Docs/initialbuild_docs/` should
continue to be presented as history.

## Implementation plan and acceptance criteria

This is a planning checklist. Completion should be recorded by the
implementation owner after verification; an unchecked item is not a statement
that a particular feature is absent.

### 1. Establish the facts

- [ ] Verify the canonical public repository owner, name, default branch, and
  links against the configured remote.
- [ ] Confirm the license status without selecting new legal terms implicitly.
- [ ] Identify the current developer setup commands and supported versions.
- [ ] Separate runnable behavior, architectural intent, and future work in copy.
- [ ] Audit public documentation links for retired scoring language.

### 2. Build the identity kit

- [ ] Original SVG mark, wordmark/lockup, light variant, and dark variant.
- [ ] Transparent PNG mark for avatars and social tools.
- [ ] Wide README banner with meaningful alternative text.
- [ ] Social sharing card with enough margin for platform cropping.
- [ ] Square card/avatar and a favicon that remain recognizable at small sizes.
- [ ] ASCII text mark using ordinary monospaced characters.
- [ ] Brief brand guide: palette, spacing, backgrounds, accessibility, and
  honest uses of decorative grids.
- [ ] Record source files and a repeatable export process.

### 3. Make GitHub welcoming and useful

- [ ] README: identity, purpose, current status, useful first action, evidence
  principles, architecture, contribution paths, and license status.
- [ ] Contribution guide with small entry points across code, docs, accessibility,
  source adapters, and data quality.
- [ ] Behavior expectations that fit a civic project and a practical moderation
  route supported by the maintainers.
- [ ] Security reporting instructions that use a real supported channel.
- [ ] Bug report, feature request, and data-correction routing with a reminder
  to omit private contact details from public issues.
- [ ] Pull request template with relevant verification and evidence checks.
- [ ] Repository description, website link, topics, and social preview image.
  Treat these as GitHub settings work, not something committed files alone finish.
- [ ] Only use badges tied to actual workflows, supported versions, or a license
  the repository really grants.

### 4. Ship the one-button site

- [ ] One clear screen with the mark, tagline, descriptive sentence, square
  composition, and one primary “View on GitHub” button.
- [ ] Correct repository URL in the button, canonical URL, and sharing metadata.
- [ ] Small-screen layout, keyboard focus, readable contrast, and reduced-motion
  behavior.
- [ ] No visitor tracking, signup wall, or invented product telemetry.
- [ ] Static assets and straightforward hosting with a documented deployment path.
- [ ] Preview and verify the published destination before declaring it live.

### 5. Review the launch as a whole

- [ ] Inspect the README in GitHub light and dark themes.
- [ ] Inspect the website at mobile and desktop widths.
- [ ] Check links, image loading, heading order, alternative text, and tab order.
- [ ] Ensure all public surfaces use the same name, description, and marks.
- [ ] Verify screenshots represent actual software; identify fixtures or
  illustrations clearly.
- [ ] Produce short launch copy and a reusable social card; publishing to social
  accounts remains a separate action.
- [ ] Record completed work, verification evidence, and any remaining owner
  decision or platform setting accurately.

## Ideas for later releases

These can add the ongoing life visible in the reference projects once the
underlying work exists:

- **One contribution, explained:** a small card showing a real improvement,
  its contributor, and the user benefit.
- **Follow one record:** a short verified demonstration from a public source
  through the ledger to a visible evidence lane.
- **The missing square:** a friendly invitation to a specific tractable issue,
  using the mark's opening as the recurring graphic.
- **Release postcards:** a consistent square-grid image for each release,
  with one shipped capability and a link to the full notes.
- **A tiny brand playground:** choose a blue shade or rearrange a decorative
  grid, while leaving the page readable and the GitHub action obvious.

The launch earns enthusiasm by making the work understandable and participation
possible. Repeated care across those details will give OpenPali its own identity.
