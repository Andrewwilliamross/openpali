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
- [ ] Record references, what to borrow, and what to avoid.
- [ ] Confirm canonical repository URL and publication path.
- [ ] Separate shipped behavior, fixtures, legacy paths, and planned capabilities in copy.

### 2. Identity system

- [ ] Original transparent vector mark, light/dark variants, wordmark.
- [ ] GitHub README banner.
- [ ] Social preview at 1280 × 640 and social square at 1080 × 1080.
- [ ] Avatar and small favicon variants.
- [ ] ASCII/text mark for terminal and release notes.
- [ ] Brand guide covering colors, spacing, usage, accessibility, and voice.
- [ ] Reproducible asset source and export instructions.
- [ ] Inspect the assets at banner, avatar, and mobile sizes.

### 3. GitHub front door

- [ ] Rewrite the README around purpose, visuals, local start, architecture, and contribution.
- [ ] Give developers a low-friction frontend preview path.
- [ ] Preserve data honesty, source attribution, and license status.
- [ ] Add verified links and concise navigation.
- [ ] Add a useful contribution guide.
- [ ] Add bug, feature, and public data-correction issue forms.
- [ ] Add a pull request template and community conduct guidance.
- [ ] Replace stale frontend and pipeline READMEs.
- [ ] Verify private vulnerability reporting instructions against repository settings.

### 4. One-button website

- [ ] Implement a lightweight static page in `site/`, separate from the map application.
- [ ] Use the shared brand assets and one prominent link to the canonical repository.
- [ ] Work at small mobile, tablet, and desktop widths.
- [ ] Support keyboard focus, high contrast text, and reduced motion.
- [ ] Include favicon and accurate social metadata.
- [ ] Work without JavaScript; enhance only decorative behavior.
- [ ] Add a reproducible staging command and GitHub Pages workflow.
- [ ] Keep API services and real property data out of the marketing deploy.

### 5. Launch kit and verification

- [ ] Provide launch copy, social captions, and a release-note template.
- [ ] Provide the exact repository description, homepage, topics, and social-image settings.
- [ ] Check local links, asset dimensions, and staging output.
- [ ] Inspect the website in a real browser on desktop and mobile.
- [ ] Check keyboard navigation, reduced motion, and no-JavaScript rendering.
- [ ] Review the diff for unsupported product or license claims.
- [ ] Publish the GitHub presentation and website when authorized and available.
- [ ] Report any remaining owner decisions or settings accurately.

## Engineering scope

Use code-native SVG for the geometric identity and a dependency-free static page. Keep the existing React/MapLibre product intact. A small build script stages only the marketing page and its assets; GitHub Pages hosts the result. Community documentation should point to real scripts and current architecture. No analytics, signup flow, invented usage numbers, or third-party font requests are needed.

## Definition of done

A visitor recognizes OpenPali, understands its purpose and evidence standards, can start exploring the code, and sees a clear way to contribute. The same identity appears on GitHub, the website, and shareable images. Any unpublished pieces or undecided license are explicitly recorded.
