// /methods: what every number and color means, with the claim boundaries the
// platform enforces (observational evidence, never resident judgment).

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

interface ReleaseInfo {
  release_id: string
  policy_versions: Record<string, string>
  schema_versions: Record<string, string>
}

export default function MethodsPage() {
  const [release, setRelease] = useState<ReleaseInfo | null>(null)
  useEffect(() => {
    let alive = true
    fetch('/v1/releases/current')
      .then((r) => r.json())
      .then((rel) => alive && setRelease(rel))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  return (
    <main className="page">
      <nav className="page-nav">
        <Link to="/map">← Map</Link>
        <Link to="/status">Status</Link>
      </nav>
      <h1>Methods and definitions</h1>

      <section>
        <h2>What the map shows</h2>
        <p>
          Every parcel is colored by its <strong>most advanced evidenced
          milestone</strong> in public agency records: debris cleanup,
          design review, permitting, construction inspection, and
          certificate of occupancy run as <strong>parallel lanes</strong> —
          no forced single ladder, no 0–100 score, no predicted finish date
          on the map.
        </p>
        <p>
          "No public evidence" always means absence from the covered public
          sources, <strong>never</strong> a judgment that an owner is
          inactive. Missing dates stay unknown; they are never replaced by
          the fire date or today's date.
        </p>
      </section>

      <section>
        <h2>Event semantics</h2>
        <ul>
          <li><strong>Scheduled</strong> inspections are not outcomes: the public
            LADBS feed documents only scheduling, so inspections never advance
            a construction lane by themselves.</li>
          <li><strong>Qualifying rebuild</strong> means a new-building permit the
            city itself flags as a Palisades rebuild; ancillary permits stay
            visible in the timeline but do not advance rebuild lanes.</li>
          <li><strong>Conflicting sources</strong> are shown as conflicts (with both
            assertions), not silently resolved.</li>
          <li>Corrections and retractions are append-only: history is preserved,
            never rewritten.</li>
        </ul>
      </section>

      <section>
        <h2>Statistics</h2>
        <p>
          Time-to-permit estimates use censoring-aware survival methods
          (Kaplan–Meier): parcels still waiting count as "still waiting,"
          not as missing. Community metrics carry their denominator, sample
          size, and computation version. Cross-checks against independent
          portals run with predeclared tolerances, and failures are
          disclosed rather than hidden.
        </p>
        <p>
          Any forecast shown is an estimate made <strong>at application
          submission time</strong> from a versioned, reviewed batch model —
          never a live ETA, never a causal claim, and never a judgment of
          resident effort. When the evidence base cannot support a model,
          the product says so with a typed reason instead of guessing.
        </p>
      </section>

      <section>
        <h2>3D and imagery</h2>
        <p>
          The post-fire ground surface comes from the USGS emergency lidar
          flight of <strong>2025-01-21</strong> (public domain, preliminary):
          it is a <em>post-fire observation</em>, never evidence of current
          construction. Pre-fire structure models are historical context
          from county data and are labeled as such; assets whose
          redistribution rights are unresolved are excluded from published
          releases and listed with the reason.
        </p>
      </section>

      {release && (
        <section>
          <h2>Versions pinned by the current release</h2>
          <dl className="status-dl">
            <dt>Release</dt>
            <dd><code>{release.release_id}</code></dd>
            {Object.entries(release.policy_versions ?? {}).map(([k, v]) => (
              // div is the only wrapper the dl content model permits
              <div key={k} style={{ display: 'contents' }}>
                <dt>{k}</dt>
                <dd><code>{v}</code></dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </main>
  )
}
