#!/usr/bin/env node
/** Export the field-office identity. Requires sharp; no network calls. */
const fs = require("node:fs/promises");
const path = require("node:path");
const sharp = require("sharp");
const root = path.resolve(__dirname, "..");
const dir = path.join(root, "assets/brand/field-office");
const blue = "#1557ff",
  ink = "#172c52";
const bird = `<path fill="#e5edff" d="M41 21 58 12 70 23 72 46 91 58 75 75 43 72 34 49Z"/><path fill="white" d="m41 21 17-9 12 11-6 17-24 10-6-1Z"/><path fill="${blue}" d="m42 37 22 3-43 44 9-31Z"/><path fill="#0b3ac0" d="m42 37-12 16-9 31 29-36Z"/><path fill="${blue}" d="m63 50 28 8-16 17-21-10Z"/><circle fill="${ink}" cx="56" cy="29" r="3.2"/><path fill="none" stroke="${blue}" stroke-width="3.5" d="m59 72-3 12h-9m26-10-2 10h-7"/>`;
const wrap = (w, h, body) =>
  `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${body}</svg>`;
(async () => {
  const outlines = JSON.parse(
    await fs.readFile(path.join(dir, "type-outlines.json"), "utf8"),
  );
  const type = (str, x, y, size, color = ink) => {
    const t = outlines[str],
      s = size / t.units;
    return `<g fill="${color}" transform="translate(${x} ${y}) scale(${s} ${-s})">${t.parts.map((p) => `<path transform="translate(${p.x} 0)" d="${p.d}"/>`).join("")}</g>`;
  };
  const data = async (name) =>
    `data:image/png;base64,${(await fs.readFile(path.join(dir, name))).toString("base64")}`;
  const hero = await data("hero-source.png");
  await sharp(path.join(dir, "hero-source.png"))
    .webp({ quality: 86, effort: 6 })
    .toFile(path.join(dir, "hero.webp"));
  await sharp(path.join(dir, "hero-source.png"))
    .resize(900)
    .webp({ quality: 84, effort: 6 })
    .toFile(path.join(dir, "hero-900.webp"));
  for (const name of ["follow-source", "build-tools", "correct-record"])
    await sharp(path.join(dir, `sources/${name}.png`))
      .resize(640)
      .png({ palette: true, quality: 95, effort: 10 })
      .toFile(path.join(dir, `${name}.png`));
  const background = (w, h) =>
    `<rect width="${w}" height="${h}" fill="white"/>`;
  const small = (value, x, y, size = 14, color = ink) =>
    `<text x="${x}" y="${y}" font-family="Arial,sans-serif" font-size="${size}" fill="${color}">${value}</text>`;
  const banner = wrap(
    1600,
    600,
    background(1600, 600) +
      `<image x="565" y="-35" width="1040" height="694" xlink:href="${hero}"/>` +
      type("openpali", 68, 76, 38, blue) +
      small("*", 202, 58, 22, blue) +
      type("A place with", 68, 235, 93) +
      type("footnotes.", 68, 334, 109, blue) +
      small("Public evidence for the Palisades rebuild.", 72, 403, 24) +
      `<path d="M72 447h58" stroke="${blue}" stroke-width="2"/>` +
      small("A SHARED RECORD. ROOM TO HELP.", 72, 486, 13, blue),
  );
  const social = wrap(
    1280,
    640,
    background(1280, 640) +
      `<image x="477" y="74" width="835" height="557" xlink:href="${hero}"/>` +
      type("openpali", 62, 74, 37, blue) +
      small("*", 193, 56, 22, blue) +
      type("A place with", 60, 248, 80) +
      type("footnotes.", 60, 338, 96, blue) +
      small("Public evidence for", 65, 405, 22) +
      small("the Palisades rebuild.", 65, 435, 22) +
      small("GITHUB.COM / ANDREWWILLIAMROSS / OPENPALI", 65, 588, 11, blue),
  );
  const square = wrap(
    1080,
    1080,
    background(1080, 1080) +
      `<image x="0" y="341" width="1080" height="720" xlink:href="${hero}"/>` +
      type("openpali", 65, 83, 39, blue) +
      small("*", 201, 65, 22, blue) +
      type("A place with", 65, 234, 102) +
      type("footnotes.", 65, 350, 123, blue) +
      small("PUBLIC EVIDENCE FOR THE PALISADES REBUILD.", 70, 1029, 17, blue),
  );
  for (const [name, svg] of [
    ["banner", banner],
    ["social-card", social],
    ["social-square", square],
  ]) {
    await fs.writeFile(
      path.join(dir, `${name}.svg`),
      svg.replace(hero, "hero-source.png"),
    );
    await sharp(Buffer.from(svg))
      .png()
      .toFile(path.join(dir, `${name}.png`));
  }
  const logo = wrap(
    290,
    75,
    type("openpali", 5, 58, 69, blue) + small("*", 257, 30, 36, blue),
  );
  await fs.writeFile(path.join(dir, "wordmark.svg"), logo);
  const avatar = wrap(
    512,
    512,
    `<rect width="512" height="512" rx="100" fill="#eef3ff"/><g transform="translate(-16 -5) scale(5)">${bird}</g>`,
  );
  await fs.writeFile(path.join(dir, "avatar.svg"), avatar);
  await sharp(Buffer.from(avatar)).png().toFile(path.join(dir, "avatar.png"));
  await fs.writeFile(
    path.join(dir, "favicon.svg"),
    wrap(
      32,
      32,
      `<rect width="32" height="32" rx="7" fill="#eef3ff"/><path fill="white" d="m15 5 7 2 1 10 6 3-5 6-10-1-3-9Z"/><path fill="${blue}" d="m15 11 6 1L5 28l5-12Zm6 6 8 3-5 6-7-4Z"/><circle fill="${ink}" cx="18" cy="9" r="1.3"/>`,
    ),
  );
  const sticker = wrap(
    600,
    300,
    `<rect x="2" y="2" width="596" height="296" rx="36" fill="white" stroke="${blue}" stroke-width="3"/><g transform="translate(12 26) scale(2.3)">${bird}</g>` +
      type("openpali", 246, 133, 75, blue) +
      small("FOLLOW THE SOURCE.", 252, 181, 16, blue),
  );
  await fs.writeFile(path.join(dir, "sticker.svg"), sticker);
  const files = await fs.readdir(dir);
  const manifest = {
    concept: "The Field Office — A place with footnotes.",
    palette: { blue, ink, paper: "#ffffff" },
    hero: {
      description:
        "Original AI-generated conceptual coastal paper atlas. Not geographic or property evidence.",
      tool: "Built-in ImageGen",
    },
    fonts: {
      Fraunces: "SIL Open Font License 1.1",
      DMSans: "SIL Open Font License 1.1",
    },
    files: {},
  };
  for (const name of files) {
    const st = await fs.stat(path.join(dir, name));
    if (st.isFile() && name !== "manifest.json")
      manifest.files[name] = { bytes: st.size };
  }
  await fs.writeFile(
    path.join(dir, "manifest.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
  console.log(
    "Exported field-office artwork, role images, banners, social cards, wordmark, avatar, favicon and sticker.",
  );
})();
