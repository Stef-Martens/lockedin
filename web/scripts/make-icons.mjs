// Writes the app icons into web/public: a bold lime "L" on the dark page colour.
// Node built-ins only, so the output is the same on any machine: `node scripts/make-icons.mjs`.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";

const PAGE = [0x0f, 0x10, 0x11]; // --page
const ACCENT = [0xc8, 0xf1, 0x69]; // --accent
// The mark on a 512 grid, kept inside the maskable safe circle (radius 205 around the centre).
const RECTS = [
  [148, 112, 244, 400], // upright
  [148, 304, 364, 400], // foot
];
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "public");

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="96" fill="#0f1011"/>
  <path d="M148 112h96v192h120v96H148z" fill="#c8f169"/>
</svg>
`;

const CRC = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

/** Full-bleed square (iOS and Android round the corners themselves), 4×4 supersampled edges. */
function png(size) {
  const SS = 4;
  const scale = 512 / size;
  const inside = (x, y) => RECTS.some(([x0, y0, x1, y1]) => x >= x0 && x < x1 && y >= y0 && y < y1);
  const rows = [];
  for (let py = 0; py < size; py++) {
    const row = Buffer.alloc(1 + size * 3); // filter byte 0, then RGB
    for (let px = 0; px < size; px++) {
      let hit = 0;
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          if (inside((px + (sx + 0.5) / SS) * scale, (py + (sy + 0.5) / SS) * scale)) hit++;
        }
      }
      const a = hit / (SS * SS);
      for (let ch = 0; ch < 3; ch++) row[1 + px * 3 + ch] = Math.round(PAGE[ch] + (ACCENT[ch] - PAGE[ch]) * a);
    }
    rows.push(row);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // RGB
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(Buffer.concat(rows), { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

writeFileSync(join(out, "favicon.svg"), svg);
writeFileSync(join(out, "apple-touch-icon.png"), png(180));
writeFileSync(join(out, "icon-192.png"), png(192));
writeFileSync(join(out, "icon-512.png"), png(512));
console.log("Wrote favicon.svg, apple-touch-icon.png, icon-192.png, icon-512.png to", out);
