import { useEffect, useState } from 'react'
import { EVIDENCE_CATEGORIES } from '../lib/colors'
import {
  fetchPostfireSources,
  postfireSourceLabel,
  type PostfireSources,
} from '../lib/postfire'

interface Props {
  mode?: '2d' | '3d'
}

export default function Legend({ mode = '2d' }: Props) {
  const [postfire, setPostfire] = useState<PostfireSources | null>(null)
  useEffect(() => {
    let alive = true
    void fetchPostfireSources().then((pf) => {
      if (alive) setPostfire(pf)
    })
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="legend" aria-label="Map legend: most advanced evidenced milestone">
      <div className="legend-title">Evidenced milestone</div>
      <ul className="legend-cats">
        {EVIDENCE_CATEGORIES.map((c) => (
          <li key={c.key}>
            <span className="legend-swatch" style={{ background: c.color }} aria-hidden />
            <span>{c.label}</span>
          </li>
        ))}
      </ul>
      {postfire?.terrain && (
        <div className="legend-sources">
          <div className="legend-title">Spatial sources</div>
          <ul className="legend-cats">
            <li>
              <span className="legend-swatch legend-swatch-hillshade" aria-hidden />
              <span>{postfireSourceLabel(postfire.terrain)}</span>
            </li>
            {mode === '3d' && (
              <li>
                <span className="legend-swatch legend-swatch-prefire" aria-hidden />
                <span>Pre-fire structures (LARIAC county model — not current conditions)</span>
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
