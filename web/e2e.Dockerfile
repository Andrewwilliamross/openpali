# Browser-evidence job (SPATIAL-001/FRONTEND): Playwright + Chromium against
# the RUNNING web/api services on the internal Compose network. Headless
# SwiftShader — correctness evidence only, recorded as such in the specs.
FROM mcr.microsoft.com/playwright:v1.61.1-noble@sha256:5b8f294aff9041b7191c34a4bab3ac270157a28774d4b0660e9743297b697e48

WORKDIR /e2e
RUN npm init -y >/dev/null && npm i --no-save @playwright/test@1.61.1 @axe-core/playwright@4
COPY playwright.config.ts ./
COPY e2e ./e2e

ENV E2E_BASE_URL=http://web:80
# correctness + accessibility gates by default; the report-only renderer
# benchmark runs via the dedicated compose job (command override)
CMD ["npx", "playwright", "test", "e2e/spatial-usgs.spec.ts", "e2e/a11y.spec.ts", "e2e/journeys.spec.ts", "--reporter=list"]
