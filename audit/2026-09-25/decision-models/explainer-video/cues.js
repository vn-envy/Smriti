const { chromium } = require(require('child_process').execSync('npm root -g').toString().trim() + '/playwright');
(async () => {
  const br = await chromium.launch(); const pg = await br.newPage();
  await pg.goto('file://' + __dirname + '/explainer.html');
  const c = await pg.evaluate(() => ({ dur: window.DUR, sc: window.SC, cues: window.cues() }));
  require('fs').writeFileSync(__dirname + '/cues.json', JSON.stringify(c, null, 1));
  console.log(c.cues.length, 'cues, dur', c.dur); await br.close();
})();
