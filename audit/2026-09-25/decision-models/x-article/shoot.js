const { chromium } = require(require('child_process').execSync('npm root -g').toString().trim() + '/playwright');
(async () => {
  const b = await chromium.launch();
  const names = { cover: "0-cover", kinds: "1-three-kinds", prize: "2-the-prize", rounds: "3-four-rounds", freewin: "4-the-free-win", score: "5-scoreboard", ships: "6-what-ships" };
  for (const [id, name] of Object.entries(names)) {
    const pg = await b.newPage({ viewport: { width: 2100, height: 1000 }, deviceScaleFactor: id === "cover" ? 1.5 : 2 });
    await pg.goto('file://' + __dirname + '/graphics.html');
    await pg.evaluate(() => document.fonts.ready);
    await pg.waitForTimeout(300);
    await pg.locator('#' + id).screenshot({ path: __dirname + '/' + name + '.png' });
    await pg.close();
  }
  await b.close();
})();
