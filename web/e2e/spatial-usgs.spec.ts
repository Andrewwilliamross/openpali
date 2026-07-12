// SPATIAL-001 browser evidence: the release-served USGS post-fire assets
// reach ACTUAL renderer draw calls, tile requests, picking, legend, and the
// property-evidence card — through the same production API a user hits.
//
// Headless note: WebGL here runs on SwiftShader/ANGLE. This spec proves
// CORRECTNESS (requests, draws, picking, labeling); it makes no performance
// claims. The unmasked GL renderer is recorded in the test output.

import { expect, test, type Page } from '@playwright/test'

const AOI_CENTER: [number, number] = [-118.5248, 34.0432]

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
      loaded: () => boolean
      jumpTo: (o: { center: [number, number]; zoom: number; pitch: number }) => void
      project: (l: [number, number]) => { x: number; y: number }
      queryTerrainElevation: (l: [number, number]) => number | null
    }
    __usgsSplats?: { stats: SplatStats }
    __splats?: { stats: SplatStats }
  }
}

async function glRenderer(page: Page): Promise<string> {
  return page.evaluate(() => {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl2')
    if (!gl) return 'no-webgl2'
    const ext = gl.getExtension('WEBGL_debug_renderer_info')
    return ext
      ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL))
      : String(gl.getParameter(gl.RENDERER))
  })
}

test('USGS post-fire surfels: tile requests, draw calls, picking, labels', async ({ page }, testInfo) => {
  const spatialRequests: string[] = []
  page.on('request', (req) => {
    if (req.url().includes('/spatial/usgs-')) spatialRequests.push(req.url())
  })

  await page.goto('/')
  testInfo.annotations.push({ type: 'gl-renderer', description: await glRenderer(page) })

  // surface page errors into the report (headless diagnosis)
  const pageErrors: string[] = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error') pageErrors.push(m.text())
  })
  // map up + release-pinned USGS layer installed (default mode is 3D).
  // __mapReady is a one-shot 'load' signal; map.loaded() polls false
  // whenever the custom layers keep the render loop warm.
  await page.waitForFunction(() => window.__mapReady === true).catch((e) => {
    throw new Error(`map load: ${e}; page errors: ${pageErrors.join(' | ')}`)
  })
  await page.waitForFunction(() => window.__usgsSplats !== undefined, undefined, {
    timeout: 60_000,
  })

  // fly into the frozen AOI so SSE demands USGS tiles
  await page.evaluate(([lon, lat]) => {
    window.__map!.jumpTo({ center: [lon, lat], zoom: 16.5, pitch: 60 })
  }, AOI_CENTER)

  // the layer must actually DRAW (frames with instanced splat draws)
  await page.waitForFunction(
    () => (window.__usgsSplats?.stats.drawnSplats ?? 0) > 0,
    undefined,
    { timeout: 60_000 },
  )
  const stats = await page.evaluate(() => window.__usgsSplats!.stats)
  expect(stats.frames).toBeGreaterThan(0)
  expect(stats.drawnNodes).toBeGreaterThan(0)
  expect(stats.drawnSplats).toBeGreaterThan(1000)
  testInfo.annotations.push({
    type: 'usgs-draw-stats',
    description: JSON.stringify(stats),
  })

  // release-qualified asset requests actually went over the wire
  const manifestReqs = spatialRequests.filter((u) => u.includes('manifest.json'))
  const splatReqs = spatialRequests.filter((u) => u.endsWith('.splat'))
  expect(manifestReqs.length).toBeGreaterThan(0)
  expect(splatReqs.length).toBeGreaterThan(0)
  expect(splatReqs[0]).toMatch(/\/v1\/releases\/rel-[a-f0-9]+\/spatial\/usgs-surfel-aoi\/sv-[a-f0-9]+\//)

  // terrain: release-served terrarium PNGs for the post-fire hillshade
  await expect
    .poll(() => spatialRequests.filter((u) => u.includes('usgs-terrain-aoi') && u.endsWith('.png')).length, {
      timeout: 30_000,
    })
    .toBeGreaterThan(0)

  // legend labels the source with its ACQUISITION date (flight), never ours
  const legend = page.locator('.legend')
  await expect(legend).toContainText('USGS post-fire lidar bare earth (flown 2025-01-21, preliminary)')

  // picking: click the AOI center -> a parcel detail card opens with the
  // post-fire surface evidence badge
  const point = await page.evaluate(([lon, lat]) => {
    const p = window.__map!.project([lon, lat])
    return { x: Math.round(p.x), y: Math.round(p.y) }
  }, AOI_CENTER)
  await page.mouse.click(point.x, point.y)
  const card = page.locator('.spatial-card')
  await expect(card).toBeVisible()
  await expect(card).toContainText(/Post-fire surface \(2025-01-21\)/)
  await expect(card).toContainText(/APN \d{4}-\d{3}-\d{3}/)
})

test('2D journey stays usable and the post-fire hillshade is present', async ({ page }) => {
  await page.goto('/')
  await page.waitForFunction(() => window.__mapReady === true)
  // leave 3D (the toggle's accessible name is its aria-label)
  await page.getByRole('button', { name: 'Toggle 3D view' }).click()
  // parcels remain interactive in 2D: legend + evidence categories visible
  await expect(page.locator('.legend')).toContainText('Evidenced milestone')
  // release-served post-fire DEM is queryable where the AOI sits
  const hasSource = await page.evaluate(
    () =>
      (window.__map as unknown as { getSource?: (id: string) => unknown })
        .getSource?.('postfire-dem') !== undefined,
  )
  expect(hasSource).toBe(true)
})
