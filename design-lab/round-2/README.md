# OpenPali / design review 02

> Archived round-two review. Use the current [Signal brand kit](../../Docs/Brand/README.md) for published presentation work.

**The Field Office** was the recommendation from this review. The review also includes two working alternatives and a component board.

## Open the review

From the repository root:

```sh
python3 scripts/build-site.py
python3 -m http.server 4173 --bind 127.0.0.1
```

Open <http://127.0.0.1:4173/design-lab/round-2/>. The gallery supports desktop and phone viewports. Open each study directly to inspect its native-size layout.

| Study | Implementation | Direct route |
| --- | --- | --- |
| Field Office | HTML, CSS, native field notes, original ImageGen illustrations | `/design-lab/round-2/field-office/` |
| Living Atlas | Local Three.js, actual hinged paper/terrain geometry, SVG fallback | `/design-lab/round-2/atlas/` |
| Three Dates | HTML/CSS/JS mechanical date reader and source slip | `/design-lab/round-2/instrument/` |
| Component board | Four GitHub invitations, source disclosure, correction history | `/design-lab/round-2/components/` |

The illustrations and examples contain no property data. The primary site works without JavaScript. Alternatives document their own reduced-motion and fallback behavior.

## Review trail

- [Research](RESEARCH.md): Cua, Omarchy, and a critique of the first six studies.
- [Strategy](STRATEGY.md): purpose, audiences, story options, and acceptance criteria.
- [Engineering proposals](ENGINEERING-IDEAS.md): media, interaction, and delivery tradeoffs.
- [Field Office review](FIELD-OFFICE-REVIEW.md): independent review and implemented refinements.
- [Atlas critique](atlas/critique.md) and [instrument critique](instrument/critique.md): screenshot iterations and checks.
- [Brand guide](../../Docs/Brand/FIELD-OFFICE.md): how to extend the finished family.

The first round remains in `design-lab/concepts/` as exploration history. This round and the following pelican revision in `design-lab/round-3/` are archived. The selected direction is documented in [round four](../round-4/README.md); archived round-two assets remain in `assets/brand/field-office/`.

The presentation deck and review captures are generated artifacts in `output/design-round-2/`. The local `.build/` script uses the bundled Artifact Tool runtime. They are not part of the GitHub Pages artifact.
