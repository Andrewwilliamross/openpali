#!/usr/bin/env node
/** Raster exports of the code-native SVG identity. Requires Sharp. */
const path = require('node:path');
const sharp = require('sharp');
(async () => {
  for (const name of ['banner', 'social-card', 'avatar', 'favicon']) {
    await sharp(path.join(__dirname, `${name}.svg`)).png().toFile(path.join(__dirname, `${name}.png`));
    console.log(`${name}.png`);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
