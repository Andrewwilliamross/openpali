#!/usr/bin/env node
// Flies fixed camera paths over the running map and records frame times,
// transfer sizes, GPU memory and picking cost against the budgets below.
//
//   node web/scripts/perf-flight.mjs [--base http://127.0.0.1:5173] [--headed]
//
// Uses the Chrome already installed on this machine (no browser download).
// Writes data/out/checks/perf-<utc>.json and exits 1 if a budget is missed.
// Numbers are only comparable between runs on the same machine and display.
import { chromium } from 'playwright-core'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const args = process.argv.slice(2)
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`)
  return i < 0 ? fallback : args[i + 1]
}
const BASE = flag('base', 'http://127.0.0.1:5173')
const HEADED = args.includes('--headed')
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../../data/out/checks')

// Frame intervals are quantized to the display's refresh, so the frame budgets
// are stated against it: how often a frame is missed, and what the building
// layer adds to the p95 over the same flight with it switched off.
const BUDGETS = {
  dropped_frames_pct: 2, // intervals > 1.5× the refresh interval, worst flight, buildings on
  buildings_p95_cost_ms: 2, // p95(on) − p95(off), worst flight
  first_lots_ms: 2000, // navigation start → scored lots drawn, API warm
  own_transfer_mb: 5, // app + API + scene bytes to reach the first idle view
  pick_ms: 10, // main-thread time spent issuing a pick (the answer returns asynchronously)
}

// [name, start camera, motion]. Each is flown once to warm tiles, then measured.
const FLIGHTS = [
  ['alphabets-orbit', { center: [-118.5228, 34.0412], zoom: 17.6, pitch: 62, bearing: -20 },
    { bearing: 70, duration: 5000 }],
  ['bluffs-approach', { center: [-118.545, 34.0405], zoom: 15.2, pitch: 55, bearing: 10 },
    { center: [-118.5462, 34.0418], zoom: 17.4, pitch: 66, bearing: 40, duration: 5000 }],
  ['malibu-coast-pass', { center: [-118.628, 34.0375], zoom: 16.6, pitch: 68, bearing: -60 },
    { center: [-118.612, 34.0385], bearing: -40, duration: 5000 }],
]

const browser = await chromium.launch({
  channel: 'chrome',
  headless: !HEADED,
  args: ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
})
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
const page = await context.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(m.text())
})

// ---- transfer accounting, by who serves the bytes ----
// (context-level, so requests made by the scene worker are counted too)
const transfer = { app: 0, api: 0, scene_meshes: 0, scene_terrain: 0, scene_manifest: 0, third_party: 0 }
const sizing = []
context.on('requestfinished', (request) => {
  const url = request.url()
  const path = url.startsWith(BASE) ? url.slice(BASE.length) : null
  const bucket = path === null ? 'third_party'
    : path.startsWith('/v1/') ? 'api'
    : /^\/scene\/[^/]+\/terrain\//.test(path) ? 'scene_terrain'
    : /^\/scene\/(current\.json|[^/]+\/manifest)/.test(path) ? 'scene_manifest'
    : path.startsWith('/scene/') ? 'scene_meshes' : 'app'
  sizing.push(request.sizes().then((s) => {
    transfer[bucket] += s.responseBodySize + s.responseHeadersSize
  }).catch(() => {}))
})

// in-page helpers
await page.addInitScript(() => {
  window.__perf = { lots: null, buildings: null }
  const origin = performance.now()
  const watch = () => {
    const map = window.__map
    const perf = window.__perf
    if (map && perf.lots === null && map.getSource?.('parcels') && map.isSourceLoaded('parcels')
        && map.queryRenderedFeatures({ layers: ['parcel-fill'] }).length > 0) {
      perf.lots = performance.now() - origin
    }
    if (perf.buildings === null && (window.__buildings?.stats.batchesDrawn ?? 0) > 0) {
      perf.buildings = performance.now() - origin
    }
    if (perf.lots === null || perf.buildings === null) requestAnimationFrame(watch)
  }
  requestAnimationFrame(watch)
  window.__settle = (timeout = 25000) => new Promise((done) => {
    const started = performance.now()
    const check = () => {
      const map = window.__map
      const b = window.__buildings
      const quiet = map && map.loaded() && !map.isMoving() && map.areTilesLoaded()
      if (quiet && b) {
        const frames = b.stats.frames
        setTimeout(() => (b.stats.frames - frames <= 2 || performance.now() - started > timeout
          ? done(performance.now() - started) : check()), 500)
      } else if (performance.now() - started > timeout) done(-1)
      else setTimeout(check, 200)
    }
    check()
  })
  window.__fly = (motion) => new Promise((done) => {
    const map = window.__map
    const frames = []
    let last = performance.now()
    const end = last + motion.duration
    map.easeTo({ ...motion, easing: (t) => t, essential: true })
    const tick = () => {
      const now = performance.now()
      frames.push(now - last)
      last = now
      if (now < end) requestAnimationFrame(tick)
      else {
        frames.sort((a, b) => a - b)
        const q = (p) => +frames[Math.min(frames.length - 1, Math.floor(frames.length * p))].toFixed(2)
        const interval = q(0.5)
        const dropped = frames.filter((f) => f > interval * 1.5).length
        done({ frames: frames.length, p50: interval, p95: q(0.95), p99: q(0.99),
          max: +frames[frames.length - 1].toFixed(1), dropped_pct: +((dropped / frames.length) * 100).toFixed(2) })
      }
    }
    requestAnimationFrame(tick)
  })
})

const result = { base: BASE, at: new Date().toISOString(), budgets: BUDGETS, flights: {} }
try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => window.__perf.lots !== null && window.__perf.buildings !== null,
    null, { timeout: 60000 })
  await page.evaluate(() => window.__settle())
  result.first_view = await page.evaluate(() => ({
    first_lots_ms: Math.round(window.__perf.lots),
    first_buildings_ms: Math.round(window.__perf.buildings),
  }))
  await Promise.all(sizing)
  result.first_view.transfer_mb = Object.fromEntries(
    Object.entries(transfer).map(([k, v]) => [k, +(v / 1e6).toFixed(2)]))
  result.first_view.own_transfer_mb = +((Object.values(transfer).reduce((a, b) => a + b, 0) - transfer.third_party) / 1e6).toFixed(2)
  result.gpu = await page.evaluate(() => {
    const gl = document.createElement('canvas').getContext('webgl2')
    const info = gl?.getExtension('WEBGL_debug_renderer_info')
    return info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : 'unknown'
  })
  result.refresh_hz = await page.evaluate(() => new Promise((done) => {
    const t = []
    const tick = (now) => (t.push(now), t.length < 40 ? requestAnimationFrame(tick)
      : done(Math.round(1000 / ((t[t.length - 1] - t[5]) / (t.length - 6)))))
    requestAnimationFrame(tick)
  }))

  for (const [name, start, motion] of FLIGHTS) {
    const fly = async (buildings) => {
      await page.evaluate(([s, on]) => {
        window.__buildings.setEnabled(on)
        window.__map.jumpTo(s)
      }, [start, buildings])
      await page.evaluate(() => window.__settle())
      return page.evaluate((m) => window.__fly(m), motion)
    }
    await fly(true) // warm-up: loads the tiles and batches the path crosses
    const on = await fly(true)
    const off = await fly(false)
    await page.evaluate(() => window.__buildings.setEnabled(true))
    result.flights[name] = { buildings_on: on, buildings_off: off }
  }

  // picking over a grid at the first flight's start view
  result.picking = await page.evaluate(async (start) => {
    const map = window.__map
    const b = window.__buildings
    map.jumpTo(start)
    await window.__settle()
    const canvas = map.getCanvas()
    let hits = 0, n = 0, gpu = 0
    await b.pick({ x: 10, y: 10 }) // allocates the 1×1 target
    const started = performance.now()
    for (let y = 120; y < canvas.clientHeight; y += 110) {
      for (let x = 100; x < canvas.clientWidth; x += 150) {
        n++
        if (await b.pick({ x, y })) hits++
        gpu = Math.max(gpu, b.stats.lastPickMs)
      }
    }
    return { tested: n, hits, round_trip_avg_ms: +((performance.now() - started) / n).toFixed(1), gpu_max_ms: +gpu.toFixed(2) }
  }, FLIGHTS[0][1])

  result.memory = await page.evaluate(() => {
    const s = window.__buildings.stats
    return {
      geometry_mb: +(s.geometryBytes / 1e6).toFixed(1),
      roof_texture_mb: +(s.atlasBytes / 1e6).toFixed(1),
      js_heap_mb: performance.memory ? +(performance.memory.usedJSHeapSize / 1e6).toFixed(1) : null,
      batches_ready: s.batchesReady,
      ground_checks: s.groundSamples,
      ground_corrections: s.groundCorrections,
      layer_errors: s.errors,
    }
  })
} finally {
  await browser.close()
}

result.errors = errors.slice(0, 20)
const flights = Object.values(result.flights)
const dropped = Math.max(...flights.map((f) => f.buildings_on.dropped_pct))
const cost = +Math.max(...flights.map((f) => f.buildings_on.p95 - f.buildings_off.p95)).toFixed(2)
result.verdict = {
  dropped_frames_pct: { value: dropped, pass: dropped <= BUDGETS.dropped_frames_pct },
  buildings_p95_cost_ms: { value: cost, pass: cost <= BUDGETS.buildings_p95_cost_ms },
  first_lots_ms: { value: result.first_view?.first_lots_ms, pass: result.first_view?.first_lots_ms <= BUDGETS.first_lots_ms },
  own_transfer_mb: { value: result.first_view?.own_transfer_mb, pass: result.first_view?.own_transfer_mb <= BUDGETS.own_transfer_mb },
  pick_ms: { value: result.picking?.gpu_max_ms, pass: result.picking?.gpu_max_ms <= BUDGETS.pick_ms },
}
mkdirSync(OUT, { recursive: true })
const file = resolve(OUT, `perf-${result.at.replace(/[-:]|\..*/g, '')}.json`)
writeFileSync(file, JSON.stringify(result, null, 1) + '\n')
console.log(JSON.stringify(result, null, 1))
console.log(`\nwritten: ${file}`)
const failed = Object.entries(result.verdict).filter(([, v]) => !v.pass).map(([k]) => k)
if (failed.length) {
  console.error(`BUDGET MISSED: ${failed.join(', ')}`)
  process.exit(1)
}
console.log('all budgets met')
