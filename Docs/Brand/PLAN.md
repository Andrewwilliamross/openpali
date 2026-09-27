# OpenPali public launch design

## Brief

Make OpenPali recognizable and welcoming to developers across its GitHub repository, a one-button website, and social sharing. Use white, blue, transparent surfaces, and the visual rhythm of GitHub contribution squares. Make the invitation to build feel enjoyable while treating recovery records and affected residents with care.

## Creative direction: Build in the open

- **Identity:** a square-built P, called the Parcel P. It suggests a shared map and many small contributions. It is an abstract mark, never a map or measure of recovery.
- **Public headline:** “Recovery, in the open.”
- **Developer invitation:** “Build in the open.”
- **Plain description:** “A public evidence platform for the Palisades rebuild.”
- **Visual system:** vivid blue `#1557FF`, ink `#10234A`, white, pale blue, precise square geometry, generous space, and readable typography.
- **Signature detail:** a contribution-like field of blue squares, with an open area around the mark. On the website it responds gently to a pointer; motion is decorative and respects reduced-motion preferences.
- **Tone:** curious, direct, neighborly. Have fun with code, marks, and building together. Do not gamify recovery or turn missing evidence into a judgment.
- **Ownership:** OpenPali is the project name; RE\\SPRING is credited as its originator. No inferred endorsements or government affiliation.

## Reference translation

See [REFERENCES.md](REFERENCES.md) for source-linked research. Borrow the discipline of repeating an identity, showing real capabilities, and making contribution approachable. Develop original artwork and language.

## Deliverables and acceptance checklist

### 1. Research and truth

- [x] Inspect the requested reference websites and repositories.
- [x] Read the existing project, setup scripts, CI, and deployment instructions.
- [x] Identify stale descriptions and the outstanding license decision.
- [x] Record references, what to borrow, and what to avoid.
- [x] Confirm canonical repository URL and publication path.
- [x] Separate shipped behavior, fixtures, legacy paths, and planned capabilities in copy.

### 2. Identity system

- [x] Original transparent vector mark, light/dark variants, wordmark.
- [x] GitHub README banner.
- [x] Social preview at 1280 × 640 and social square at 1080 × 1080.
- [x] Avatar and small favicon variants.
- [x] ASCII/text mark for terminal and release notes.
- [x] Brand guide covering colors, spacing, usage, accessibility, and voice.
- [x] Reproducible asset source and export instructions.
- [x] Inspect the assets at banner, avatar, and mobile sizes.

### 3. GitHub front door

- [x] Rewrite the README around purpose, visuals, local start, architecture, and contribution.
- [x] Give developers a low-friction frontend preview path.
- [x] Preserve data honesty, source attribution, and license status.
- [x] Add verified links and concise navigation.
- [x] Add a useful contribution guide.
- [x] Add bug, feature, and public data-correction issue forms.
- [x] Add a pull request template and community conduct guidance.
- [x] Replace stale frontend and pipeline READMEs.
- [x] Verify private vulnerability reporting instructions against repository settings.

### 4. One-button website

- [x] Implement a lightweight static page in `site/`, separate from the map application.
- [x] Use the shared brand assets and one prominent link to the canonical repository.
- [x] Work at small mobile, tablet, and desktop widths.
- [x] Support keyboard focus, high contrast text, and reduced motion.
- [x] Include favicon and accurate social metadata.
- [x] Work without JavaScript; enhance only decorative behavior.
- [x] Add a reproducible staging command and GitHub Pages workflow.
- [x] Keep API services and real property data out of the marketing deploy.

### 5. Launch kit and verification

- [x] Provide launch copy, social captions, and a release-note template.
- [x] Provide the exact repository description, homepage, topics, and social-image settings.
- [x] Check local links, asset dimensions, and staging output.
- [x] Inspect the website in a real browser on desktop and mobile.
- [x] Verify keyboard navigation in-browser and review reduced-motion/no-JavaScript behavior in source.
- [ ] Finish browser emulation of reduced motion, JavaScript disabled, and 200% zoom.
- [x] Review the diff for unsupported product or license claims.
- [ ] Publish the GitHub presentation and website when authorized and available.
- [ ] Report any remaining owner decisions or settings accurately.

## Engineering scope

Use code-native SVG for the geometric identity and a dependency-free static page. Keep the existing React/MapLibre product intact. A small build script stages only the marketing page and its assets; GitHub Pages hosts the result. Community documentation should point to real scripts and current architecture. No analytics, signup flow, invented usage numbers, or third-party font requests are needed.

## Definition of done

A visitor recognizes OpenPali, understands its purpose and evidence standards, can start exploring the code, and sees a clear way to contribute. The same identity appears on GitHub, the website, and shareable images. Any unpublished pieces or undecided license are explicitly recorded.


## Verification and publication record

- Original SVGs parse, generation is deterministic, and PNG dimensions match their intended uses. Banner and both social-card compositions were visually inspected.
- The static build stages only the landing page, CSS, decorative JavaScript, mark, favicon, social PNG, and `.nojekyll`.
- Real-browser checks passed at desktop, 390 px, and 320 px: assets loaded, one GitHub action, no horizontal overflow, and a visible keyboard-focus outline.
- Reduced motion and no-JavaScript behavior were reviewed in source: the full grid and link are static HTML, while pointer highlighting is optional and checks `prefers-reduced-motion`. Browser emulation of these settings and 200% zoom were not completed after browser access became unavailable.
- Local documentation links, SVG XML, PNG dimensions, Python compilation, JavaScript syntax, and whitespace checks passed. Independent review found and corrected a stale security-scanning claim.
- Canonical repository confirmed as `Andrewwilliamross/openpali`. GitHub Pages was enabled for Actions; private vulnerability reporting was enabled.
- Publication is tracked in [pull request #11](https://github.com/Andrewwilliamross/openpali/pull/11).
- Source-code licensing remains pending owner selection. Public copy does not claim an open-source license.
- GitHub's social-preview image still needs uploading in Settings. The browser extension denied local file access; the ready-to-upload asset is `assets/brand/social-card.png`. Social posts are drafted, not sent.
