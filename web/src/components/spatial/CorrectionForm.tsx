// "Report an issue" — the public correction path (FRONTEND-001). Posts to the
// release-qualified API; a human moderates every submission and acceptance
// becomes an append-only revision. Hidden when the API is unreachable
// (static hosting) rather than failing.

import { useEffect, useState, type FormEvent } from 'react'
import { fetchPostfireSources } from '../../lib/postfire'

interface Props {
  apn: string
}

type SendState = 'idle' | 'sending' | 'sent' | 'rate_limited' | 'error'

export default function CorrectionForm({ apn }: Props) {
  const [releaseId, setReleaseId] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [contact, setContact] = useState('')
  const [state, setState] = useState<SendState>('idle')

  useEffect(() => {
    let alive = true
    void fetchPostfireSources().then((pf) => {
      if (alive && pf) setReleaseId(pf.releaseId)
    })
    return () => {
      alive = false
    }
  }, [])

  if (!releaseId) return null

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setState('sending')
    try {
      const resp = await fetch(
        `/v1/releases/${releaseId}/properties/${apn}/corrections`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            claim_ref: 'property-record',
            message,
            contact: contact || null,
          }),
        },
      )
      if (resp.status === 429) setState('rate_limited')
      else if (resp.ok) setState('sent')
      else setState('error')
    } catch {
      setState('error')
    }
  }

  return (
    <details className="correction">
      <summary>Report an issue with this record</summary>
      {state === 'sent' ? (
        <p role="status">
          Thank you — a person reviews every report. Accepted corrections
          become visible revisions with the original preserved.
        </p>
      ) : (
        <form onSubmit={(e) => void submit(e)}>
          <label>
            What looks wrong? <span aria-hidden>*</span>
            <textarea
              required
              minLength={10}
              maxLength={4000}
              rows={3}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </label>
          <label>
            Contact (optional; stored separately, never published)
            <input
              type="text"
              maxLength={200}
              value={contact}
              onChange={(e) => setContact(e.target.value)}
            />
          </label>
          <button type="submit" disabled={state === 'sending' || message.length < 10}>
            {state === 'sending' ? 'Sending…' : 'Send report'}
          </button>
          {state === 'rate_limited' && (
            <p role="alert">Rate limit reached — please try again later.</p>
          )}
          {state === 'error' && (
            <p role="alert">Could not send right now. Please try again.</p>
          )}
        </form>
      )}
    </details>
  )
}
