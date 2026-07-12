// Product journeys (FRONTEND-001/E2E-001): search, deep link, the DINS-joined
// property's evidence, one-snapshot coherence between the visible badge and
// the API, community numbers matching the release, forecast insufficiency,
// the correction path, and the API-down last-known-good fallback.

import { expect, test } from '@playwright/test'

declare global {
  interface Window {
    __mapReady?: boolean
  }
}

// independently verified DINS-joined property (calfire_dins observations)
const DINS_APN = '4409012016'

test('deep link renders the property card with API-served evidence', async ({ page }) => {
  await page.goto(`/property/${DINS_APN}`)
  await page.waitForFunction(() => window.__mapReady === true)
  const card = page.locator('.spatial-card')
  await expect(card).toBeVisible()
  await expect(card).toContainText('APN 4409-012-016')
  // the DINS damage assessment observation in the evidence timeline, under
  // its source-naming label (the card shows human labels, not raw source ids)
  await expect(card).toContainText(/damage/i)
  await expect(card).toContainText(/DINS damage assessment/)
})

test('one snapshot everywhere: badge, card data, and header numbers match the API', async ({ page }) => {
  await page.goto('/map')
  await page.waitForFunction(() => window.__mapReady === true)

  const release = await page.evaluate(async () => {
    const r = await (await fetch('/v1/releases/current')).json()
    return {
      release_id: r.release_id as string,
      snapshot_id: r.snapshot_id as string,
      properties: r.coverage.properties as number,
      permit_issued: r.coverage.permit_issued as number,
    }
  })

  // visible identity matches the API's current release
  const badge = page.getByTestId('release-badge')
  await expect(badge).toContainText(release.release_id.slice(0, 16))
  await expect(badge).toContainText(release.snapshot_id.slice(0, 17))

  // real community numbers in the header equal the release values: the
  // destroyed-parcels count verbatim, and the permit rate derived from the
  // same release coverage the header uses
  const nums = page.locator('.header .metric-num')
  await expect(
    nums.filter({ hasText: release.properties.toLocaleString('en-US') }).first(),
  ).toBeVisible()
  const pct = release.properties
    ? `${Math.round((release.permit_issued / release.properties) * 100)}%`
    : '–'
  await expect(nums.filter({ hasText: pct }).first()).toBeVisible()

  // and the parcel MAP itself requests this release's tiles
  const tileReq = page.waitForRequest(
    (req) => req.url().includes(`/v1/releases/${release.release_id}/tiles/parcels/`),
    { timeout: 30_000 },
  )
  await page.evaluate(() => {
    ;(window as unknown as { __map: { zoomTo: (z: number) => void } }).__map.zoomTo(15.4)
  })
  await tileReq
})

test('search finds an address and opens its card', async ({ page }) => {
  await page.goto('/map')
  await page.waitForFunction(() => window.__mapReady === true)
  const input = page.locator('.search-box input')
  await input.fill('4409012016')
  const results = page.locator('.search-results button')
  await expect(results.first()).toBeVisible()
  await results.first().click()
  await expect(page.locator('.spatial-card')).toBeVisible()
  await expect(page).toHaveURL(/\/property\/\d{10}/)
})

test('forecast surface shows the typed insufficiency for a qualifying property', async ({ page }) => {
  // land on the app first so relative /v1 fetches resolve against the web host
  await page.goto('/map')
  // find a qualifying property THROUGH the API (same source the card uses)
  const apn = await page.evaluate(async () => {
    const rel = await (await fetch('/v1/releases/current')).json()
    const props = await (
      await fetch(`/v1/releases/${rel.release_id}/properties?page_size=50`)
    ).json()
    for (const item of props.items) {
      if (item.milestones?.application_submitted) return item.apn as string
    }
    return null
  })
  expect(apn).not.toBeNull()
  await page.goto(`/property/${apn}`)
  await page.waitForFunction(() => window.__mapReady === true)
  const panel = page.locator('.forecast-panel')
  await expect(panel).toBeVisible({ timeout: 30_000 })
  await expect(panel).toContainText(/INSUFFICIENT_POINT_IN_TIME_HISTORY|estimated chance/)
})

test('model status and research export are inspectable on /status', async ({ page }) => {
  await page.goto('/status')
  const model = page.getByTestId('model-status')
  await expect(model).toBeVisible()
  await expect(model).toContainText(/INSUFFICIENT_POINT_IN_TIME_HISTORY|Reviewed champion/)
  await expect(page.locator('a', { hasText: 'snapshot-addressed metrics CSV' })).toBeVisible()
})

test('correction journey: report form submits (or is rate-limited) with a visible outcome', async ({ page }) => {
  await page.goto(`/property/${DINS_APN}`)
  await page.waitForFunction(() => window.__mapReady === true)
  const details = page.locator('.correction summary')
  await details.click()
  await page.locator('.correction textarea').fill(
    'E2E journey drill: the cleanup date shown appears earlier than the county PDF.',
  )
  await page.locator('.correction button[type="submit"]').click()
  // either accepted (role=status) or rate-limited (role=alert) — both are
  // working, honest outcomes of the production path
  await expect(
    page.locator('.correction [role="status"], .correction [role="alert"]').first(),
  ).toBeVisible({ timeout: 20_000 })
})

test('API down: last-known-good bundle keeps the journey usable and says so', async ({ page }) => {
  await page.route('**/v1/**', (route) => route.abort())
  await page.goto('/map')
  await page.waitForFunction(() => window.__mapReady === true)
  // offline badge is explicit
  await expect(page.getByTestId('release-badge')).toContainText('last-known-good')
  // static bundle still paints parcels and the header still has numbers
  await expect(page.locator('.legend')).toContainText('Evidenced milestone')
  const headerText = await page.locator('.header').textContent()
  expect(headerText).toMatch(/\d/)
  // the card still opens from the static details bundle
  await page.goto(`/property/${DINS_APN}`)
  await page.waitForFunction(() => window.__mapReady === true)
  await expect(page.locator('.spatial-card')).toBeVisible()
})
