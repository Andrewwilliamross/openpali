// Forecast-or-insufficiency (ML-003): the property card shows exactly what
// the learning system produced for THIS release — a submission-time estimate
// from a reviewed batch model, a typed insufficiency with the reason, or
// not-applicable. Never a live ETA, never silence.

import { useEffect, useState } from 'react'
import { fetchPostfireSources } from '../../lib/postfire'

interface ForecastApp {
  application_id: string
  status: string
  estimate?: number
  horizon_days?: number
  basis?: { origin_date?: string; note?: string; extrapolated_features?: string[] }
  note?: string
}

interface Forecast {
  status: 'available' | 'insufficient_evidence' | 'not_applicable'
  reason?: string
  note?: string
  prediction_set_id?: string
  disclaimer: string
  model?: { model_id: string; training_cutoff: string | null }
  applications?: ForecastApp[]
}

export default function ForecastPanel({ apn }: { apn: string }) {
  const [forecast, setForecast] = useState<Forecast | null>(null)

  useEffect(() => {
    let alive = true
    void (async () => {
      const sources = await fetchPostfireSources()
      if (!sources) return
      try {
        const resp = await fetch(
          `/v1/releases/${sources.releaseId}/properties/${apn}/forecast`,
        )
        if (resp.ok && alive) setForecast((await resp.json()) as Forecast)
      } catch {
        /* API unreachable: the panel simply doesn't render */
      }
    })()
    return () => {
      alive = false
    }
  }, [apn])

  if (!forecast || forecast.status === 'not_applicable') return null

  return (
    <section className="forecast-panel">
      <h3 className="spatial-h">Permit-timing model</h3>
      {forecast.status === 'insufficient_evidence' ? (
        <p className="forecast-insufficient">
          No forecast is shown: <code>{forecast.reason}</code>.{' '}
          {forecast.note ??
            'The evidence base cannot yet support a reviewed model for this estimate.'}
        </p>
      ) : (
        <>
          <ul className="forecast-apps">
            {(forecast.applications ?? []).map((a) => (
              <li key={a.application_id}>
                {a.status === 'predicted' && a.estimate !== undefined ? (
                  <>
                    <strong>{Math.round(a.estimate * 100)}%</strong> estimated
                    chance permit {a.application_id} issues within{' '}
                    {a.horizon_days} days of its {a.basis?.origin_date} submission
                    {a.basis?.extrapolated_features?.length ? (
                      <em> (outside the model's training range — extra caution)</em>
                    ) : null}
                  </>
                ) : (
                  <>
                    {a.application_id}: {a.note ?? a.status}
                  </>
                )}
              </li>
            ))}
          </ul>
          <p className="forecast-model-line">
            Reviewed model <code>{forecast.model?.model_id?.slice(0, 18)}</code>,
            trained through {forecast.model?.training_cutoff?.slice(0, 10)}.
          </p>
        </>
      )}
      <p className="forecast-disclaimer">{forecast.disclaimer}</p>
    </section>
  )
}
