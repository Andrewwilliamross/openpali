# Round three / Field Notes

The current candidate in [PR #12](https://github.com/Andrewwilliamross/openpali/pull/12): a flat pelican with a field notebook, actual Palisades parcel lines, and one small task played over 26 seconds. This remains a review candidate until the relevant main-branch release is deployed.

## Review locally

From the repository root:

```sh
python3 scripts/compose-field-notes.py
python3 scripts/build-site.py
python3 -m http.server 4173 --bind 127.0.0.1
```

Open <http://127.0.0.1:4173/dist/site/> for the candidate or <http://127.0.0.1:4173/design-lab/> for the gallery. The previous paper-atlas page is archived in [`../round-2/field-office/`](../round-2/field-office/).

The scene is composed into an inline SVG. It uses local fonts and committed geometry; viewing it needs no map API, external font service, or rendering package. Only the public landing-page allowlist enters the Pages artifact; this design lab stays outside it.

## What to inspect

Watch a full cycle: the feet plant during the waddle, the bird stops to inspect, the pencil meets the margin underline, and the actor returns. The map remains stationary. Check the complete route on desktop and phones, then try:

- Pause and resume at different phases.
- Reduced motion: a complete still, **Play once**, then a return to still mode.
- Leaving the scene or hiding the tab: the animation clock suspends.
- Keyboard access, expanded field notes, and the source disclosure.
- JavaScript disabled: the static drawing, text, notes, and GitHub link remain available.

The 61-parcel drawing is source geometry. The pelican, architectural inset, and annotation gesture are illustration. No animation encodes a property’s condition or recovery status.

## Sources and decisions

| Document | Purpose |
| --- | --- |
| [Art direction](ART-DIRECTION.md) | Creative brief and proposed choreography; the shipped implementation is in the scene composer and website script. |
| [QA and review](QA.md) | Browser checks, corrected issues, and review limits. |
| [Character guide](CHARACTER.md) | Original SVG rig, parts, and drawing decisions. |
| [Geography](GEOGRAPHY.md) | Official sources, exact crop, attribution, terms, and reproducible exports. |
| [Implementation summary](../../Docs/Brand/ROUND-3.md) | Current delivery and pending release status. |
| [Brand kit](../../Docs/Brand/README.md) | Current assets and rules for extending the family. |
| [Website guide](../../site/README.md) | Build, deployment scope, and interaction behavior. |

Source artwork is in [`assets/brand/field-notes-2d/`](../../assets/brand/field-notes-2d/). [`compose-field-notes.py`](../../scripts/compose-field-notes.py) builds the scene; [`site/field-office.js`](../../site/field-office.js) controls its shared timeline. The earlier artwork is retained as an archive.
