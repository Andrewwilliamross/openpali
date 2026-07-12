import { useMemo, useState } from 'react'
import type { ParcelCollection, Summary } from '../lib/types'
import { titleCase } from '../lib/format'

interface Props {
  parcels: ParcelCollection | null
  neighborhoods: Summary['neighborhoods']
  onPick: (apn: string) => void
  onGoto: (center: [number, number], zoom: number) => void
}

export default function SearchBar({ parcels, neighborhoods, onPick, onGoto }: Props) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)

  const index = useMemo(
    () =>
      (parcels?.features ?? []).map((f) => ({
        apn: f.properties.apn,
        address: f.properties.address,
        lc: f.properties.address.toLowerCase(),
      })),
    [parcels],
  )

  const hits = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (needle.length < 2) return []
    // addresses match by text; APNs (how county records cite parcels) by digits
    const digits = needle.replace(/[^0-9]/g, '')
    const apnNeedle = digits.length >= 4 ? digits : null
    const matchStart = (r: { lc: string; apn: string }) =>
      r.lc.startsWith(needle) || (apnNeedle !== null && r.apn.startsWith(apnNeedle))
    const starts = index.filter(matchStart)
    const contains =
      starts.length >= 8
        ? []
        : index.filter((r) => !matchStart(r) && r.lc.includes(needle))
    return [...starts, ...contains].slice(0, 8)
  }, [q, index])

  return (
    <div className="searchbar">
      <div className="search-box">
        <input
          type="search"
          placeholder="Search an address or APN…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          aria-label="Search address"
        />
        {open && hits.length > 0 && (
          <ul className="search-results">
            {hits.map((h) => (
              <li key={h.apn}>
                <button
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onPick(h.apn)
                    setQ('')
                    setOpen(false)
                  }}
                >
                  {titleCase(h.address)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <select
        className="hood-select"
        defaultValue=""
        onChange={(e) => {
          const n = neighborhoods.find((x) => x.name === e.target.value)
          if (n) onGoto(n.center, n.zoom)
        }}
        aria-label="Jump to neighborhood"
      >
        <option value="" disabled>
          Neighborhood…
        </option>
        {neighborhoods.map((n) => (
          <option key={n.name} value={n.name}>
            {n.name}
          </option>
        ))}
      </select>
    </div>
  )
}
