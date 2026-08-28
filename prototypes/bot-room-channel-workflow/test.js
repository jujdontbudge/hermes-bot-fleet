#!/usr/bin/env node
/* Headless acceptance test for the throwaway issue #8 prototype. */
const { chromium } = require('playwright');
const { pathToFileURL } = require('url');
const path = require('path');
const assert = require('assert');

(async () => {
  // Use the installed system Chrome so the runner needs no browser download.
  const executablePath = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({ headless: true, executablePath });
  const base = pathToFileURL(path.join(__dirname, 'index.html')).href;
  let assertions = 0;
  try {
    for (const variant of ['guided', 'canvas', 'console']) {
      const page = await browser.newPage();
      const errors = [];
      page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${base}?variant=${variant}`);
      assert(await page.locator('body').evaluate((el, v) => el.classList.contains(`variant-${v}`), variant)); assertions++;
      assert.strictEqual(await page.locator(`[data-variant="${variant}"]`).getAttribute('class'), 'active'); assertions++;
      await page.click('[data-view="chat"]');
      assert(await page.locator('#view-chat').evaluate(el => el.classList.contains('active'))); assertions++;
      assert.deepStrictEqual(errors, [], `${variant} browser errors: ${errors.join('; ')}`); assertions++;
      await page.close();
    }

    const page = await browser.newPage();
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}?variant=guided`);

    // Bot validation, runtime implications, creation, and canonical chat.
    await page.fill('#botName', 'Bad Name');
    await page.click('#validateBot');
    assert((await page.textContent('#validationResult')).includes('lowercase')); assertions++;
    await page.fill('#botName', 'mac-researcher');
    await page.check('input[name="runtime"][value="mac"]');
    assert((await page.textContent('#implications')).includes('single-use approval')); assertions++;
    await page.check('#reviewConfirm');
    await page.click('#validateBot');
    assert((await page.textContent('#validationResult')).includes('ready')); assertions++;
    await page.click('#botForm button[type="submit"]');
    assert.strictEqual(await page.locator('#chat-title').innerText(), 'mac-researcher on johan-mac'); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.bots['mac-researcher'].browser), 'MAC-OWNED'); assertions++;
    await page.fill('#canonicalInput', '@test-worker check this');
    await page.click('#canonicalForm button');
    assert((await page.locator('#canonicalLog').innerText()).includes('target permissions remain unchanged')); assertions++;

    // Room mention routing and offline behavior.
    await page.click('[data-view="room"]');
    await page.fill('#roomInput', '@test-worker verify and @laptop-worker assist');
    await page.click('#roomForm button');
    const roomText = await page.locator('#roomLog').innerText();
    assert(roomText.includes('test-worker')); assertions++;
    assert(roomText.includes('laptop-worker unavailable or not a room member')); assertions++;

    // Mac reconnect enables adding the Mac Bot to the Room.
    await page.click('[data-view="operate"]');
    await page.click('#toggleLaptop');
    assert.strictEqual(await page.textContent('#laptopStatus'), 'online · approval gated'); assertions++;
    await page.click('[data-view="room"]');
    await page.click('#addLaptop');
    assert.strictEqual(await page.locator('[data-member="laptop-worker"]').count(), 1); assertions++;

    // Telegram channel mapping.
    await page.click('[data-view="channel"]');
    await page.selectOption('#channelBot', 'test-worker');
    await page.click('#channelForm button');
    assert((await page.textContent('#channelResult')).includes('outbound polling to test-worker')); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.channel.bot), 'test-worker'); assertions++;

    // Routine inspection and complete safe browser ownership cycle.
    await page.click('[data-view="operate"]');
    await page.click('.runRoutine[data-routine="Acceptance smoke"]');
    assert((await page.locator('#activityLog').innerText()).includes('Acceptance smoke: failed')); assertions++;
    const chiefAction = '.browserAction[data-bot="chief"]';
    for (const expected of ['DRAINING', 'HUMAN', 'RECOVERING', 'AUTOMATION']) {
      await page.click(chiefAction);
      assert.strictEqual(await page.textContent('#chiefBrowser'), expected); assertions++;
    }
    assert((await page.locator('#liveState').innerText()).includes('Mac\nconnected')); assertions++;
    assert((await page.locator('#activityLog li').count()) <= 8); assertions++;
    assert.deepStrictEqual(errors, [], `interaction browser errors: ${errors.join('; ')}`); assertions++;
    await page.close();

    console.log(`PASS: ${assertions} assertions; variants=guided,canvas,console; consoleErrors=0`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.stack || error); process.exit(1); });
