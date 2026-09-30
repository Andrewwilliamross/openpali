#!/usr/bin/env node
/** Raster exports from the adjacent self-contained SVGs. Requires Sharp. */
const path = require("node:path");
const sharp = require("sharp");
(async () => {
  for (const name of ["avatar", "banner", "social-card"]) {
    await sharp(path.join(__dirname, `${name}.svg`))
      .png()
      .toFile(path.join(__dirname, `${name}.png`));
    console.log(`${name}.png`);
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
