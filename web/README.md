# OpenPali evidence workspace

React + TypeScript + Vite + Tailwind 4 + official coss components + MapLibre.

From the repository root:

```sh
npm --prefix web ci --cache .npm-cache
make evidence-build
make evidence-api  # terminal 1, localhost:8000
make evidence-web  # terminal 2, localhost:5173
```

The source acquisition cache must exist before `evidence-build`; build errors
identify missing or altered inputs. It never silently substitutes fixtures.
The UI pins a portable evidence release for its lifetime. Reload to adopt a
new release. Production civic releases are a separate publication authority.

- Explore: search all records, filter the map, inspect a property.
- Evidence: public cleanup packets, agency status, assessment and permit tables.
- Market: sourced listing samples, recorded transfers and neighborhood exposure.
- Site: dated point-cloud QA, measurements, downloads and sampled sewer records.
- People: local project-role drafts, explicitly unverified; no performance ranking.
- Collect: queue missing evidence against alternate sources.
- Coverage: source counts, limitations and a full versioned JSON export.

Draft writes require `OPENPALI_LOCAL_WORKSPACE=1`. Bind this mode to loopback;
public authentication, owner verification and abuse controls are not shipped.
Without that setting, the API is read-only. Operational drafts are stored in
`data/out/workspace.sqlite` and never mutate an evidence release.

Component provenance and license scope: [COSS-SOURCE.md](COSS-SOURCE.md).
Basemap: OpenStreetMap; parcel polygons are the acquired County geometry.
The basemap is contextual and is never used as dated construction evidence.
