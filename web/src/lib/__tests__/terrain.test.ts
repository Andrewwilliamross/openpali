import { describe, expect, it } from 'vitest'
import {
  AWS_TERRARIUM,
  POSTFIRE_DTM_BOUNDS,
  isPostfireTerrainEnabled,
  postfireTerrainConfig,
  resolveTerrainConfig,
  toDemSource,
  type TerrainEnv,
} from '../terrain'

const POSTFIRE_URL = 'https://cdn.example.com/palisades/dtm/{z}/{x}/{y}.png'

describe('terrain feature flag', () => {
  it('is off by default (no env)', () => {
    expect(isPostfireTerrainEnabled({})).toBe(false)
  })

  it('stays off if enabled but no tiles URL is configured', () => {
    expect(isPostfireTerrainEnabled({ VITE_POSTFIRE_TERRAIN: 'true' })).toBe(false)
  })

  it('stays off if a URL is set but the flag is not "true"', () => {
    expect(
      isPostfireTerrainEnabled({ VITE_POSTFIRE_TERRAIN_URL: POSTFIRE_URL }),
    ).toBe(false)
  })

  it('is on only when both the flag and URL are set', () => {
    const env: TerrainEnv = { VITE_POSTFIRE_TERRAIN: 'true', VITE_POSTFIRE_TERRAIN_URL: POSTFIRE_URL }
    expect(isPostfireTerrainEnabled(env)).toBe(true)
  })
})

describe('resolveTerrainConfig', () => {
  it('falls back to AWS terrarium when disabled', () => {
    expect(resolveTerrainConfig({})).toBe(AWS_TERRARIUM)
    expect(AWS_TERRARIUM.encoding).toBe('terrarium')
    expect(AWS_TERRARIUM.maxzoom).toBe(15) // z16 does not exist upstream
    expect(AWS_TERRARIUM.bounds).toBeUndefined() // global coverage
  })

  it('uses the post-fire DTM (bounded, finer zoom) when enabled', () => {
    const env: TerrainEnv = { VITE_POSTFIRE_TERRAIN: 'true', VITE_POSTFIRE_TERRAIN_URL: POSTFIRE_URL }
    const cfg = resolveTerrainConfig(env)
    expect(cfg.tiles).toBe(POSTFIRE_URL)
    expect(cfg.encoding).toBe('terrarium')
    expect(cfg.maxzoom).toBeGreaterThan(AWS_TERRARIUM.maxzoom) // sub-metre detail
    expect(cfg.bounds).toEqual(POSTFIRE_DTM_BOUNDS) // clipped to the burn footprint
    expect(cfg.vdatum).toContain('ellipsoidal') // baked to the splat store's frame
  })

  it('honors an explicit encoding + maxzoom override', () => {
    const cfg = postfireTerrainConfig({
      VITE_POSTFIRE_TERRAIN: 'true',
      VITE_POSTFIRE_TERRAIN_URL: POSTFIRE_URL,
      VITE_POSTFIRE_TERRAIN_ENCODING: 'mapbox',
      VITE_POSTFIRE_TERRAIN_MAXZOOM: '18',
    })
    expect(cfg.encoding).toBe('mapbox')
    expect(cfg.maxzoom).toBe(18)
  })
})

describe('toDemSource', () => {
  it('emits a raster-dem spec and omits bounds when global', () => {
    const src = toDemSource(AWS_TERRARIUM)
    expect(src.type).toBe('raster-dem')
    expect(src.tiles).toEqual([AWS_TERRARIUM.tiles])
    expect('bounds' in src).toBe(false)
  })

  it('carries bounds through for the bounded post-fire source', () => {
    const env: TerrainEnv = { VITE_POSTFIRE_TERRAIN: 'true', VITE_POSTFIRE_TERRAIN_URL: POSTFIRE_URL }
    const src = toDemSource(resolveTerrainConfig(env))
    expect(src.bounds).toEqual(POSTFIRE_DTM_BOUNDS)
  })
})
