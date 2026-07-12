// /status: the release the product is pinned to, per-source freshness, and
// last-known-good — the operational honesty page.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

interface ReleaseInfo {
  release_id: string
  snapshot_id: string
  kind: string
  status: string
  published_at: string | null
  coverage: Record<string, number>
  limitations: string[]
  lkg_release_id: string | null
}

interface SourceHealth {
  source_id: string
  title: string | null
  ok: boolean
  records: number | null
  retrieved_at: string | null
  upstream_edited_at: string | null
}

export default function StatusPage() {
  const [release, setRelease] = useState<ReleaseInfo | null>(null)
  const [sources, setSources] = useState<SourceHealth[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const rel = (await (await fetch('/v1/releases/current')).json()) as ReleaseInfo
        if (!alive) return
        setRelease(rel)
        const src = await (await fetch(`/v1/releases/${rel.release_id}/sources`)).json()
        if (alive) setSources(src.sources ?? [])
      } catch {
        if (alive) setError('The release API is unreachable. The map may be serving cached data.')
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  return (
    <main className="page">
      <nav className="page-nav">
        <Link to="/map">← Map</Link>
        <Link to="/methods">Methods</Link>
      </nav>
      <h1>Platform status</h1>
      {error && <p role="alert">{error}</p>}
      {release && (
        <>
          <section>
            <h2>Current release</h2>
            <dl className="status-dl">
              <dt>Release</dt>
              <dd><code>{release.release_id}</code> ({release.kind}, {release.status})</dd>
              <dt>Published</dt>
              <dd>{release.published_at ?? 'unknown'}</dd>
              <dt>Snapshot</dt>
              <dd><code>{release.snapshot_id}</code></dd>
              <dt>Last known good</dt>
              <dd>{release.lkg_release_id ? <code>{release.lkg_release_id}</code> : 'none recorded'}</dd>
              <dt>Properties covered</dt>
              <dd>{release.coverage?.properties?.toLocaleString() ?? '—'}</dd>
            </dl>
            {release.limitations?.length > 0 && (
              <>
                <h3>Known limitations</h3>
                <ul>{release.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              </>
            )}
          </section>
          <section>
            <h2>Sources frozen into this release</h2>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr><th>Source</th><th>Status</th><th>Records</th><th>Retrieved</th><th>Upstream edited</th></tr>
                </thead>
                <tbody>
                  {(sources ?? []).map((s) => (
                    <tr key={s.source_id}>
                      <td>{s.title ?? s.source_id}</td>
                      <td>{s.ok ? 'ok' : 'FAILED'}</td>
                      <td>{s.records?.toLocaleString() ?? '—'}</td>
                      <td>{s.retrieved_at?.slice(0, 16) ?? '—'}</td>
                      <td>{s.upstream_edited_at?.slice(0, 16) ?? 'not published'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="page-note">
              Retrieval time is when this platform fetched the data; upstream
              edited is the agency's own last-edit stamp when published.
              Absence of evidence in these sources is never evidence that
              nothing happened on the ground.
            </p>
          </section>
        </>
      )}
    </main>
  )
}
