// usage: node frames.js START_FRAME END_FRAME OUTDIR [fps] [list of specific seconds]
const { chromium } = require(require('child_process').execSync('npm root -g').toString().trim() + '/playwright');
const fs = require('fs');
(async () => {
  const [a, b, out, fpsArg, ...secs] = process.argv.slice(2);
  const fps = +(fpsArg || 30);
  fs.mkdirSync(out, { recursive: true });
  const br = await chromium.launch({ args: ['--disable-gpu-vsync', '--force-color-profile=srgb'] });
  const pg = await br.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const errs = []; pg.on('pageerror', e => errs.push(String(e)));
  await pg.goto('file://' + __dirname + '/explainer.html');
  await pg.evaluate(() => document.fonts.ready);
  const frames = secs.length ? secs.map(s => Math.round(+s * fps)) : Array.from({ length: +b - +a }, (_, i) => +a + i);
  const t0 = Date.now();
  for (const f of frames) {
    await pg.evaluate((t) => window.render(t), f / fps);
    await pg.screenshot({ path: `${out}/f${String(f).padStart(5, '0')}.jpg`, type: 'jpeg', quality: 92, clip: { x: 0, y: 0, width: 1920, height: 1080 } });
  }
  console.log(JSON.stringify({ frames: frames.length, ms_per_frame: Math.round((Date.now() - t0) / frames.length), errs }));
  if (a === 'cues') {}
  await br.close();
})();
