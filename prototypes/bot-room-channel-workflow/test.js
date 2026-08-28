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
    await page.selectOption('#memoryMode', 'reviewed-non-secret-brief');
    await page.uncheck('input[name="cap"][value="web"]');
    await page.uncheck('input[name="cap"][value="browser"]');
    await page.uncheck('input[name="cap"][value="kanban"]');
    await page.check('input[name="cap"][value="terminal"]');
    await page.check('input[name="cap"][value="files"]');
    await page.check('#reviewConfirm');
    await page.click('#validateBot');
    assert((await page.textContent('#validationResult')).includes('ready')); assertions++;
    await page.click('#botForm button[type="submit"]');
    assert.strictEqual(await page.locator('#chat-title').innerText(), 'mac-researcher on johan-mac'); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.bots['mac-researcher'].browser), 'MAC-OWNED'); assertions++;
    const createdBot = await page.evaluate(() => window.prototypeState.bots['mac-researcher']);
    assert.strictEqual(createdBot.memoryMode, 'reviewed-non-secret-brief'); assertions++;
    assert.deepStrictEqual(createdBot.capabilities, ['terminal', 'files']); assertions++;
    assert.strictEqual(createdBot.profileSeed, 'fresh-bundled'); assertions++;
    assert.strictEqual(createdBot.installedSkill, 'source-verifier'); assertions++;
    assert.deepStrictEqual(createdBot.firstRoutine, { name: 'Daily source watch', schedule: 'weekdays 08:30 Europe/Stockholm' }); assertions++;
    assert.strictEqual(createdBot.credentialHandle, 'secret://research-worker/web/search'); assertions++;
    assert(!Object.keys(createdBot).some(key => /token|secretValue/i.test(key))); assertions++;
    assert((await page.locator('#chatMeta').innerText()).includes('memory: reviewed-non-secret-brief')); assertions++;
    assert((await page.locator('#chatMeta').innerText()).includes('capabilities: terminal, files')); assertions++;
    assert((await page.locator('#chatMeta').innerText()).includes('seed: fresh-bundled')); assertions++;
    assert((await page.locator('#chatMeta').innerText()).includes('skill: source-verifier')); assertions++;
    const createdStateText = await page.locator('#liveState').innerText();
    assert(createdStateText.includes('Memory\nreviewed-non-secret-brief')); assertions++;
    assert(createdStateText.includes('Capabilities\nterminal, files')); assertions++;
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
    assert((await page.locator('#telegramAuthorityHelp').innerText()).includes('alias is display-only')); assertions++;
    await page.fill('#telegramUserId', 'not-a-number');
    await page.click('#channelForm button');
    assert((await page.textContent('#channelResult')).includes('strict positive integer')); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.channel), null); assertions++;
    await page.fill('#telegramUserId', '999000001');
    await page.selectOption('#pairingState', 'unpaired');
    await page.click('#channelForm button');
    assert((await page.textContent('#channelResult')).includes('paired and approved')); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.channel), null); assertions++;
    await page.selectOption('#pairingState', 'paired');
    await page.click('#channelForm button');
    assert((await page.textContent('#channelResult')).includes('outbound polling to test-worker')); assertions++;
    const channel = await page.evaluate(() => window.prototypeState.channel);
    assert.strictEqual(channel.ownerBot, 'test-worker'); assertions++;
    assert.strictEqual(channel.allowlistedUserId, 999000001); assertions++;
    assert.strictEqual(channel.allowlistedChatId, -1009990000001); assertions++;
    assert.strictEqual(typeof channel.allowlistedUserId, 'number'); assertions++;
    assert.strictEqual(typeof channel.allowlistedChatId, 'number'); assertions++;
    assert.strictEqual(channel.pairingState, 'paired'); assertions++;
    assert.strictEqual(channel.admissionState, 'approved'); assertions++;
    assert.strictEqual(channel.displayAlias, 'human:johan'); assertions++;
    assert.strictEqual(channel.credentialHandle, 'secret://chief/telegram/gateway'); assertions++;
    const channelStateText = await page.locator('#liveState').innerText();
    assert(channelStateText.includes('user 999000001')); assertions++;
    assert(channelStateText.includes('chat -1009990000001')); assertions++;
    assert(channelStateText.includes('paired/approved')); assertions++;
    assert(!channelStateText.includes('human:johan')); assertions++;

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
