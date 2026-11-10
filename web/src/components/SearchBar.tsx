import { useMemo, useState } from 'react'
import type { ParcelCollection } from '../lib/types'
import { titleCase } from '../lib/format'
import { NEIGHBORHOODS } from '../lib/neighborhoods'

interface Props {
  parcels: ParcelCollection | null
  /** the parcel request failed: say so rather than "loading" forever */
  unavailable: boolean
  onPick: (apn: string) => void
  onNeighborhood: (name: string) => void
}

const MAX_HITS = 8

/** "1263 MONACO DR LOS ANGELES CA 90272" → "1263 Monaco Dr" */
function streetAddress(address: string): string {
  return titleCase(address.replace(/\s+(LOS ANGELES|PACIFIC PALISADES|MALIBU|TOPANGA|SANTA MONICA)\s+CA\b.*$/i, ''))
}

export default function SearchBar({ parcels, unavailable, onPick, onNeighborhood }: Props) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)

  const index = useMemo(
    () =>
      (parcels?.features ?? [])
        .filter((f) => f.properties.address)
        .map((f) => ({
          apn: f.properties.apn,
          label: streetAddress(f.properties.address),
          lc: f.properties.address.toLowerCase(),
        })),
    [parcels],
  )

  const hits = useMemo(() => {
    const needle = q.trim().toLowerCase().replace(/\s+/g, ' ')
    if (needle.length < 2) return []
    // addresses match by text; APNs (how county records cite parcels) by digits
    const digits = needle.replace(/[^0-9]/g, '')
    const apnNeedle = digits.length >= 4 ? digits : null
    const matchStart = (r: { lc: string; apn: string }) =>
      r.lc.startsWith(needle) || (apnNeedle !== null && r.apn.startsWith(apnNeedle))
    const starts = index.filter(matchStart)
    const contains =
      starts.length >= MAX_HITS
        ? []
        : index.filter((r) => !matchStart(r) && r.lc.includes(needle))
    return [...starts, ...contains].slice(0, MAX_HITS)
  }, [q, index])

  const pick = (hit: { apn: string; label: string }): void => {
    onPick(hit.apn)
    setQ(hit.label)
    setOpen(false)
  }
  const showList = open && hits.length > 0
  const noMatch = open && q.trim().length >= 2 && hits.length === 0 && index.length > 0

  return (
    <div className="searchbar">
      <div className="search-box">
        <input
          type="search"
          role="combobox"
          aria-expanded={showList}
          aria-controls="address-results"
          aria-activedescendant={showList ? `address-result-${active}` : undefined}
          aria-label="Search address or parcel number"
          placeholder={parcels ? 'Search an address or APN…' : unavailable ? 'Addresses unavailable' : 'Loading addresses…'}
          disabled={!parcels}
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setActive(0)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setOpen(false)
            if (!showList) return
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((i) => (i + 1) % hits.length)
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((i) => (i - 1 + hits.length) % hits.length)
            } else if (e.key === 'Enter') {
              e.preventDefault()
              pick(hits[Math.min(active, hits.length - 1)])
            }
          }}
        />
        {showList && (
          <ul className="search-results" id="address-results" role="listbox">
            {hits.map((h, i) => (
              <li
                key={h.apn}
                id={`address-result-${i}`}
                role="option"
                aria-selected={i === active}
                className={i === active ? 'active' : undefined}
                // mousedown, not click: fires before the input's blur closes the list
                onMouseDown={(e) => {
                  e.preventDefault()
                  pick(h)
                }}
                onMouseEnter={() => setActive(i)}
              >
                {h.label}
                <small>{h.apn}</small>
              </li>
            ))}
          </ul>
        )}
        {noMatch && (
          <p className="search-results search-empty" role="status">
            No matching address. Try a street name or a ten-digit APN.
          </p>
        )}
      </div>
      <select
        className="hood-select"
        defaultValue=""
        onChange={(e) => onNeighborhood(e.target.value)}
        aria-label="Jump to neighborhood"
      >
        <option value="" disabled>
          Neighborhood…
        </option>
        {NEIGHBORHOODS.map((n) => (
          <option key={n.name} value={n.name}>
            {n.name}
          </option>
        ))}
      </select>
    </div>
  )
}
