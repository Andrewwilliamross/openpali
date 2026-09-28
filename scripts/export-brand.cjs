#!/usr/bin/env node
// Archived Parcel P exporter (first design study).
// Current Signal artwork: node assets/brand/signal/export-assets.cjs.
// Historical reproduction requires sharp, resolved through NODE_PATH.
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
