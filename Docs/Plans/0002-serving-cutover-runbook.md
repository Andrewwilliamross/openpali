# Runbook 0002 — Serving Cutover (tiles out of git → object storage + CDN)

- **Status:** Ready to execute (gated on infra decisions — see Step 0)
- **Owner:** _assign before running_
- **Parent:** ADR 0001 (Decision 5)
- **Why:** the repo is 4.6 GB; **318 MB / 2,378 splat-tile files are committed to git** (`web/public/tiles/`).
  Serving must move to object storage + CDN before the repo is workable and before OpenPali can offer companies
  real endpoints. The web app is already decoupled (env-driven base URLs); this runbook flips the switch.

> ⚠️ **Order matters.** Do **not** untrack tiles (Step 4) until the CDN is serving them (Steps 1–3) and the app
> points at it (Step 3) — otherwise the live site 404s. The history rewrite (Step 5) rewrites SHAs and is a
> **separate, coordinated, all-hands** action — never bundle it into a routine PR.

## What's already done (code, behavior-preserving)
- `web/src/lib/config.ts` — `DATA_BASE` / `TILES_BASE` read `VITE_DATA_BASE` / `VITE_TILES_BASE`, defaulting to the
  current bundled paths. `App.tsx` and `MapView.tsx` consume them. **No behavior change until the env vars are set.**
- `make publish` — `rclone sync` of `web/public/tiles` + `web/public/data` to a bucket (guarded; needs `rclone` +
  `OPENPALI_TILES_REMOTE`).
- `make pmtiles` — builds `parcels.pmtiles` from the emitted GeoJSON (guarded; needs `tippecanoe`).
- `.gitignore` already lists `data/runs/`; tiles are added in Step 4.

---

## Step 0 — Decide the infra (gating)
- **Bucket / CDN.** Recommend **Cloudflare R2** (zero egress — material for a 318 MB public tileset) + a public
  bucket or R2 custom domain. Alternatives: S3 + CloudFront, GCS + Cloud CDN.
- **CORS.** The browser fetches `.splat` / `tileset.json` / `*.json` cross-origin → bucket must send
  `Access-Control-Allow-Origin` for the site origin.
- Install tooling locally: `brew install rclone tippecanoe git-filter-repo`.

## Step 1 — Provision + configure
- Create the bucket; enable public read + CORS.
- Configure an rclone remote (e.g. `r2`). Set `export OPENPALI_TILES_REMOTE=r2:openpali-tiles`.

## Step 2 — Publish current assets
```bash
make publish        # syncs web/public/tiles/palisades and web/public/data to the bucket
# (optional) make pmtiles && make publish   # also ship parcels.pmtiles
```
Verify a couple of objects resolve over HTTPS (e.g. `…/tiles/palisades/manifest.json`, `…/data/summary.json`)
with correct CORS headers.

## Step 3 — Point the app at the CDN, deploy, verify
Create `web/.env.production`:
```
VITE_TILES_BASE=https://<cdn-host>/tiles/palisades
VITE_DATA_BASE=https://<cdn-host>/data
```
```bash
make build          # tsc + vite build (dist/)
```
Deploy `dist/` and confirm in the browser: 2D parcels render, 3D splats stream, the parcel cards load — **all
from the CDN** (check the Network tab origin). Only proceed once this is green.

## Step 4 — Untrack tiles from git (reversible)
```bash
git rm -r --cached web/public/tiles            # stops tracking; leaves files on disk
echo 'web/public/tiles/' >> .gitignore
git commit -m "Serve splat tiles from CDN; stop tracking web/public/tiles"
```
This halts **future** bloat. Existing history still holds the binaries (Step 5).

## Step 5 — Reclaim history (coordinated, one-time, rewrites SHAs)
> Schedule with the whole team. Everyone re-clones afterward. Do this on a quiet branch state.
```bash
git filter-repo --path web/public/tiles --invert-paths     # purge tiles from all history
# re-add origin if filter-repo dropped it, then:
git push --force-with-lease --all
git push --force-with-lease --tags
```
Expect the repo to drop from ~4.6 GB toward a few hundred MB. Confirm with a fresh `git clone`.

## Rollback
- Steps 1–3 are additive — unset the `VITE_*_BASE` env and rebuild to revert to bundled paths.
- Step 4 is reversible until Step 5: `git revert` the untrack commit (files are still on disk).
- Step 5 is **not** easily reversible — keep a full mirror clone (`git clone --mirror`) as a backup before running.

---

## Deferred to Phase 2 (not in this runbook)
- Switching `MapView` from the whole-loaded `parcels.geojson` to the `parcels.pmtiles` vector source (a real
  rendering change — register the `pmtiles://` protocol, add a vector source + `source-layer`). `make pmtiles`
  produces the archive now; the frontend swap is verified separately so it can't silently break the map.
