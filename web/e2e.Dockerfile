# Browser-evidence job (SPATIAL-001/FRONTEND): Playwright + Chromium against
# the RUNNING web/api services on the internal Compose network. Headless
# SwiftShader — correctness evidence only, recorded as such in the specs.
FROM mcr.microsoft.com/playwright:v1.61.1-noble@sha256:5b8f294aff9041b7191c34a4bab3ac270157a28774d4b0660e9743297b697e48

WORKDIR /e2e
RUN npm init -y >/dev/null && npm i --no-save @playwright/test@1.61.1
COPY playwright.config.ts ./
COPY e2e ./e2e

ENV E2E_BASE_URL=http://web:80
CMD ["npx", "playwright", "test", "--reporter=list"]
