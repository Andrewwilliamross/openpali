#!/usr/bin/env node
// Optional authoring tool; install sharp outside the repository, then expose
// its node_modules directory through NODE_PATH. See Docs/Brand/README.md.
const path = require('node:path');
const sharp = require('sharp');
const root = path.resolve(__dirname, '..');
const names = ['banner', 'social-card', 'social-square', 'avatar',
  'mark', 'mark-white', 'wordmark', 'wordmark-white'];
(async () => {
  for (const name of names) {
    const source = path.join(root, 'assets', 'brand', `${name}.svg`);
    const destination = path.join(root, 'assets', 'brand', `${name}.png`);
    await sharp(source).png().toFile(destination);
    console.log(`Exported ${name}.png`);
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
