// SPATIAL-002 deterministic renderer benchmark: fixed scenes, fixed cameras,
// measured frame times / draw volume / memory / requests. Report-only — the
// numbers drive the profiling-selected improvement and its before/after
// artifact. Headless runs record the GL renderer string; SwiftShader results
// support correctness and RELATIVE regression checks, never GPU claims.

import { test, type Page } from '@playwright/test'

interface SplatStats {
  frames: number
  drawnNodes: number
  drawnSplats: number
  residentBytes: number
}

declare global {
  interface Window {
    __mapReady?: boolean
    __map?: {
      jumpTo: (o: { center: [number, number]; zoom: number; pitch: number; bearing?: number }) => void
      repaint: boolean
    }
    __splats?: { stats: SplatStats }
    __usgsSplats?: { stats: SplatStats }
    __frameSamples?: number[]
  }
}

// Fixed reference scenes: LARIAC corpus core, USGS AOI, wide oblique, far out.
const SCENES = [
  { name: 'lariac-core', center: [-118.5525, 34.049] as [number, number], zoom: 16.5, pitch: 60, bearing: 20 },
  { name: 'usgs-aoi', center: [-118.5248, 34.0432] as [number, number], zoom: 16.5, pitch: 60, bearing: 0 },
  { name: 'oblique-wide', center: [-118.54, 34.046] as [number, number], zoom: 14.5, pitch: 70, bearing: 45 },
  { name: 'top-down-far', center: [-118.53, 34.045] as [number, number], zoom: 13.2, pitch: 0, bearing: 0 },
]

// SwiftShader software rasterization: small viewport + bounded frame-count
// sampling keep the run inside the budget while staying deterministic
const SETTLE_MS = 5_000
const SAMPLE_FRAMES = 30
const SAMPLE_MAX_MS = 25_000

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return NaN
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))
  return sorted[idx]
}

async function sampleScene(page: Page, scene: (typeof SCENES)[number]) {
  await page.evaluate((s) => {
    window.__map!.jumpTo({ center: s.center, zoom: s.zoom, pitch: s.pitch, bearing: s.bearing })
  }, scene)
  await page.waitForTimeout(SETTLE_MS) // tiles fetch/upload/settle

  const before = await page.evaluate(() => ({
    lariac: window.__splats ? { ...window.__splats.stats } : null,
    usgs: window.__usgsSplats ? { ...window.__usgsSplats.stats } : null,
    resources: performance.getEntriesByType('resource').length,
  }))

  await page.evaluate(() => {
    window.__frameSamples = []
    window.__map!.repaint = true // continuous render for honest frame timing
    let last = performance.now()
    const tick = (t: number) => {
      window.__frameSamples!.push(t - last)
      last = t
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
  await page
    .waitForFunction(
      (n) => (window.__frameSamples?.length ?? 0) >= n,
      SAMPLE_FRAMES,
      { timeout: SAMPLE_MAX_MS },
    )
    .catch(() => {
      /* slow software frames: report whatever accumulated */
    })
  const samples = await page.evaluate(() => {
    window.__map!.repaint = false
    return window.__frameSamples!.slice(1)
  })
  const after = await page.evaluate(() => ({
    lariac: window.__splats ? { ...window.__splats.stats } : null,
    usgs: window.__usgsSplats ? { ...window.__usgsSplats.stats } : null,
    resources: performance.getEntriesByType('resource').length,
    memoryMB: (performance as unknown as { memory?: { usedJSHeapSize: number } })
      .memory ? (performance as unknown as { memory: { usedJSHeapSize: number } })
      .memory.usedJSHeapSize / 1048576 : null,
  }))

  const sorted = [...samples].sort((a, b) => a - b)
  const sum = (s: SplatStats | null, e: SplatStats | null, k: keyof SplatStats) =>
    s && e ? e[k] - s[k] : 0
  return {
    scene: scene.name,
    frames: samples.length,
    frame_ms_p50: Number(percentile(sorted, 50).toFixed(2)),
    frame_ms_p95: Number(percentile(sorted, 95).toFixed(2)),
    frame_ms_max: Number(percentile(sorted, 100).toFixed(2)),
    splats_per_frame:
      samples.length > 0
        ? Math.round(
            (sum(before.lariac, after.lariac, 'drawnSplats')
              + sum(before.usgs, after.usgs, 'drawnSplats')) / samples.length,
          )
        : 0,
    nodes_per_frame:
      samples.length > 0
        ? Math.round(
            (sum(before.lariac, after.lariac, 'drawnNodes')
              + sum(before.usgs, after.usgs, 'drawnNodes')) / samples.length,
          )
        : 0,
    resident_mb: Number(
      (((after.lariac?.residentBytes ?? 0) + (after.usgs?.residentBytes ?? 0)) / 1048576).toFixed(1),
    ),
    requests_during_scene: after.resources - before.resources,
    js_heap_mb: after.memoryMB ? Number(after.memoryMB.toFixed(1)) : null,
  }
}

test.use({ viewport: { width: 800, height: 500 } })

test('deterministic renderer benchmark (report-only)', async ({ page }, testInfo) => {
  test.setTimeout(300_000)
  await page.goto('/')
  const renderer = await page.evaluate(() => {
    const gl = document.createElement('canvas').getContext('webgl2')
    const ext = gl?.getExtension('WEBGL_debug_renderer_info')
    return gl && ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : 'unknown'
  })
  await page.waitForFunction(() => window.__mapReady === true)
  await page.waitForFunction(() => window.__splats !== undefined, undefined, { timeout: 60_000 })
  await page.waitForFunction(() => window.__usgsSplats !== undefined, undefined, { timeout: 60_000 })

  const results = []
  for (const scene of SCENES) {
    results.push(await sampleScene(page, scene))
  }
  const report = { gl_renderer: renderer, hardware_accelerated: !/swiftshader|llvmpipe|software/i.test(renderer), scenes: results }
  console.log(`RENDERER_BENCH ${JSON.stringify(report)}`)
  testInfo.annotations.push({ type: 'renderer-bench', description: JSON.stringify(report) })
})
