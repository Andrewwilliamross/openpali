// FRONTEND-002 accessibility gate: axe-core over every routed journey.
// Fails on critical/serious violations; all findings land in annotations.

import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

declare global {
  interface Window {
    __mapReady?: boolean
  }
}

async function scan(page: Page, ready: () => Promise<void>, path: string) {
  await page.goto(path)
  await ready()
  const results = await new AxeBuilder({ page })
    // the WebGL canvas itself is exempt from color-contrast machine checks;
    // everything overlaid on it (legend, cards, nav) is NOT
    .exclude('.map-container canvas')
    .analyze()
  const severe = results.violations
    .filter((v) => v.impact === 'critical' || v.impact === 'serious')
    .map((v) => ({
      ...v,
      // name the offending nodes so a failure is actionable from the log
      help: `${v.help} [${v.nodes.map((n) => n.target.join(' ')).join('; ')}]`,
    }))
  return { all: results.violations, severe }
}

test('a11y: /methods', async ({ page }, testInfo) => {
  const { all, severe } = await scan(
    page,
    () => page.getByRole('heading', { level: 1 }).waitFor(),
    '/methods',
  )
  testInfo.annotations.push({ type: 'axe', description: JSON.stringify(all.map((v) => v.id)) })
  expect(severe.map((v) => `${v.id}: ${v.help}`)).toEqual([])
})

test('a11y: /status', async ({ page }, testInfo) => {
  const { all, severe } = await scan(
    page,
    () => page.getByRole('heading', { level: 1 }).waitFor(),
    '/status',
  )
  testInfo.annotations.push({ type: 'axe', description: JSON.stringify(all.map((v) => v.id)) })
  expect(severe.map((v) => `${v.id}: ${v.help}`)).toEqual([])
})

test('a11y: /map with legend and controls', async ({ page }, testInfo) => {
  const { all, severe } = await scan(
    page,
    async () => {
      await page.waitForFunction(() => window.__mapReady === true)
      await page.locator('.legend').waitFor()
    },
    '/map',
  )
  testInfo.annotations.push({ type: 'axe', description: JSON.stringify(all.map((v) => v.id)) })
  expect(severe.map((v) => `${v.id}: ${v.help}`)).toEqual([])
})

test('keyboard: mode toggle and nav are reachable and operable', async ({ page }) => {
  await page.goto('/map')
  await page.waitForFunction(() => window.__mapReady === true)
  const toggle = page.getByRole('button', { name: 'Toggle 3D view' })
  await toggle.focus()
  await expect(toggle).toBeFocused()
  await page.keyboard.press('Enter') // 2D -> 3D without a pointer
  await expect(toggle).toHaveText(/2D|3D…/)
  const methods = page.locator('.app-nav a', { hasText: 'Methods' })
  await methods.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Methods')
})
