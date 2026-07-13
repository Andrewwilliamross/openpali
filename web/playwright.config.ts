import { defineConfig } from '@playwright/test'

// E2E against the RUNNING Compose stack (web container through the accel
// proxy). Start it first:
//   python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d web api proxy
export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 30_000 },
  retries: 0,
  // one worker: two Chromium instances contend for CPU under SwiftShader and
  // starve tile fetch/render timing in the map specs
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:58080',
    // in-cluster the browser reaches external tile hosts only through the
    // labeled egress proxy; internal services bypass it
    ...(process.env.E2E_PROXY
      ? {
          proxy: {
            server: process.env.E2E_PROXY,
            bypass: 'web,api,localhost,127.0.0.1',
          },
        }
      : {}),
    // Headless WebGL runs on SwiftShader/ANGLE — correctness evidence only.
    // Every spec records the unmasked GL renderer so headless results are
    // never mistaken for GPU performance claims (SPATIAL-002).
    launchOptions: {
      args: ['--enable-unsafe-swiftshader', '--disable-dev-shm-usage'],
    },
    trace: 'retain-on-failure',
    video: 'off', // ffmpeg component not installed (download host not allowlisted)
  },
})
