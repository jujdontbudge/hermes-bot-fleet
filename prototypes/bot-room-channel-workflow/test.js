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

    // Browser Profile and cap=browser are one authority, synchronized in both directions.
    {
      const page = await browser.newPage();
      await page.goto(`${base}?variant=guided`);
      const browserCap = 'input[name="cap"][value="browser"]';
      assert.strictEqual(await page.inputValue('#browserProfile'), 'dedicated'); assertions++;
      assert.strictEqual(await page.isChecked(browserCap), true); assertions++;
      assert((await page.textContent('#browserHint')).includes('server profile')); assertions++;

      await page.selectOption('#browserProfile', 'none');
      assert.strictEqual(await page.isChecked(browserCap), false); assertions++;
      assert((await page.textContent('#browserHint')).includes('no server Browser Profile')); assertions++;
      await page.check(browserCap);
      assert.strictEqual(await page.inputValue('#browserProfile'), 'dedicated'); assertions++;
      await page.uncheck(browserCap);
      assert.strictEqual(await page.inputValue('#browserProfile'), 'none'); assertions++;

      // Validation still denies a contradiction introduced without a UI change event.
      await page.evaluate(() => { document.querySelector('#browserProfile').value = 'dedicated'; });
      await page.check('#reviewConfirm');
      await page.click('#validateBot');
      assert((await page.textContent('#validationResult')).includes('must agree')); assertions++;

      // Disabled creation has neither browser state nor browser capability.
      await page.selectOption('#browserProfile', 'none');
      await page.fill('#botName', 'no-browser-worker');
      await page.click('#botForm button[type="submit"]');
      const disabledBot = await page.evaluate(() => window.prototypeState.bots['no-browser-worker']);
      assert.strictEqual(disabledBot.browser, 'NONE'); assertions++;
      assert(!disabledBot.capabilities.includes('browser')); assertions++;
      await page.close();
    }

    // A dedicated server profile starts fail-closed in RECOVERING with browser capability.
    {
      const page = await browser.newPage();
      await page.goto(`${base}?variant=guided`);
      await page.fill('#botName', 'server-browser-worker');
      await page.check('#reviewConfirm');
      await page.click('#botForm button[type="submit"]');
      const serverBot = await page.evaluate(() => window.prototypeState.bots['server-browser-worker']);
      assert.strictEqual(serverBot.browser, 'RECOVERING'); assertions++;
      assert(serverBot.capabilities.includes('browser')); assertions++;
      assert((await page.locator('#liveState').innerText()).includes('Browser\nRECOVERING')); assertions++;
      await page.close();
    }

    // Dedicated browser authority on Mac is explicitly Mac-owned, never a server profile.
    {
      const page = await browser.newPage();
      await page.goto(`${base}?variant=guided`);
      await page.fill('#botName', 'mac-browser-worker');
      await page.check('input[name="runtime"][value="mac"]');
      assert((await page.textContent('#browserHint')).includes('MAC-OWNED')); assertions++;
      assert((await page.textContent('#implications')).includes('no server Browser Profile is created')); assertions++;
      await page.check('#reviewConfirm');
      await page.click('#botForm button[type="submit"]');
      const macBot = await page.evaluate(() => window.prototypeState.bots['mac-browser-worker']);
      assert.strictEqual(macBot.browser, 'MAC-OWNED'); assertions++;
      assert(macBot.capabilities.includes('browser')); assertions++;
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
    assert.strictEqual(await page.inputValue('#credential'), 'secret://mac-researcher/web/search'); assertions++;
    await page.fill('#credential', 'secret://research-worker/web/search');
    await page.fill('#botName', 'mac-researcher-alt');
    assert.strictEqual(await page.inputValue('#credential'), 'secret://research-worker/web/search'); assertions++;
    await page.fill('#botName', 'mac-researcher');
    await page.check('input[name="runtime"][value="mac"]');
    assert((await page.textContent('#implications')).includes('single-use approval')); assertions++;
    await page.selectOption('#memoryMode', 'reviewed-non-secret-brief');
    await page.uncheck('input[name="cap"][value="web"]');
    await page.uncheck('input[name="cap"][value="browser"]');
    assert.strictEqual(await page.inputValue('#browserProfile'), 'none'); assertions++;
    assert((await page.textContent('#browserHint')).includes('no Mac-owned browser authority')); assertions++;
    assert((await page.textContent('#implications')).includes('no browser capability or browser authority')); assertions++;
    await page.uncheck('input[name="cap"][value="kanban"]');
    await page.check('input[name="cap"][value="terminal"]');
    await page.check('input[name="cap"][value="files"]');
    await page.check('#reviewConfirm');
    await page.click('#validateBot');
    assert((await page.textContent('#validationResult')).includes('must exactly match Bot/profile name mac-researcher')); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.bots['mac-researcher']), undefined); assertions++;
    await page.fill('#credential', 'secret://mac-researcher/web/search');
    await page.click('#validateBot');
    assert((await page.textContent('#validationResult')).includes('ready')); assertions++;
    await page.click('#botForm button[type="submit"]');
    assert.strictEqual(await page.locator('#chat-title').innerText(), 'mac-researcher on johan-mac'); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.bots['mac-researcher'].browser), 'NONE'); assertions++;
    const createdBot = await page.evaluate(() => window.prototypeState.bots['mac-researcher']);
    assert.strictEqual(createdBot.memoryMode, 'reviewed-non-secret-brief'); assertions++;
    assert.deepStrictEqual(createdBot.capabilities, ['terminal', 'files']); assertions++;
    assert.strictEqual(createdBot.profileSeed, 'fresh-bundled'); assertions++;
    assert.strictEqual(createdBot.installedSkill, 'source-verifier'); assertions++;
    assert.deepStrictEqual(createdBot.firstRoutine, { name: 'Daily source watch', schedule: 'weekdays 08:30 Europe/Stockholm' }); assertions++;
    assert.strictEqual(createdBot.credentialHandle, 'secret://mac-researcher/web/search'); assertions++;
    assert(!Object.keys(createdBot).some(key => /token|secretValue/i.test(key))); assertions++;
    assert.strictEqual(await page.locator('#roomBot option[value="mac-researcher"]').count(), 1); assertions++;
    assert.strictEqual(await page.locator('#mentions option[value="@mac-researcher"]').count(), 1); assertions++;
    assert.strictEqual(await page.locator('#channelBot option[value="mac-researcher"]').count(), 1); assertions++;
    const createdRoutine = await page.evaluate(() => window.prototypeState.routines['Daily source watch']);
    assert.deepStrictEqual(createdRoutine, { owner: 'mac-researcher', schedule: 'weekdays 08:30 Europe/Stockholm', result: 'paused offline' }); assertions++;
    const createdRoutineRow = page.locator('#routineRows tr').filter({ hasText: 'Daily source watch' });
    assert((await createdRoutineRow.innerText()).includes('mac-researcher')); assertions++;
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

    // Room membership, mention routing, and offline behavior for the created Bot.
    await page.click('[data-view="room"]');
    await page.selectOption('#roomBot', 'mac-researcher');
    await page.click('#addRoomBot');
    assert.strictEqual(await page.locator('[data-member="mac-researcher"]').count(), 1); assertions++;
    await page.fill('#roomInput', '@test-worker verify and @mac-researcher assist');
    await page.click('#roomForm button');
    let roomText = await page.locator('#roomLog').innerText();
    assert(roomText.includes('test-worker')); assertions++;
    assert(roomText.includes('mac-researcher unavailable or not a room member')); assertions++;

    // Mac reconnect makes every Mac-owned Bot eligible; laptop-worker remains addable.
    await page.click('[data-view="operate"]');
    await page.click('#toggleLaptop');
    assert.strictEqual(await page.textContent('#laptopStatus'), 'online · approval gated'); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.bots['mac-researcher'].online), true); assertions++;
    await page.click('[data-view="room"]');
    await page.fill('#roomInput', '@mac-researcher continue after reconnect');
    await page.click('#roomForm button');
    roomText = await page.locator('#roomLog').innerText();
    assert(roomText.includes('continue after reconnect')); assertions++;
    assert.strictEqual(await page.locator('#roomLog article.message.bot b', { hasText: 'mac-researcher' }).count(), 1); assertions++;
    await page.selectOption('#roomBot', 'laptop-worker');
    await page.click('#addRoomBot');
    assert.strictEqual(await page.locator('[data-member="laptop-worker"]').count(), 1); assertions++;

    // Telegram channel mapping and Bot-bound credential derivation.
    await page.click('[data-view="channel"]');
    await page.selectOption('#channelBot', 'test-worker');
    assert.strictEqual(await page.inputValue('#channelCredential'), 'secret://test-worker/telegram/gateway'); assertions++;
    await page.selectOption('#channelBot', 'mac-researcher');
    assert.strictEqual(await page.inputValue('#channelCredential'), 'secret://mac-researcher/telegram/gateway'); assertions++;
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
    await page.evaluate(() => { document.querySelector('#channelCredential').value = 'secret://chief/telegram/gateway'; });
    await page.click('#channelForm button');
    assert((await page.textContent('#channelResult')).includes('must belong to the selected owning Bot')); assertions++;
    assert.strictEqual(await page.evaluate(() => window.prototypeState.channel), null); assertions++;
    await page.selectOption('#channelBot', 'test-worker');
    await page.selectOption('#channelBot', 'mac-researcher');
    assert.strictEqual(await page.inputValue('#channelCredential'), 'secret://mac-researcher/telegram/gateway'); assertions++;
    await page.click('#channelForm button');
    assert((await page.textContent('#channelResult')).includes('outbound polling to mac-researcher')); assertions++;
    const channel = await page.evaluate(() => window.prototypeState.channel);
    assert.strictEqual(channel.ownerBot, 'mac-researcher'); assertions++;
    assert.strictEqual(channel.allowlistedUserId, 999000001); assertions++;
    assert.strictEqual(channel.allowlistedChatId, -1009990000001); assertions++;
    assert.strictEqual(typeof channel.allowlistedUserId, 'number'); assertions++;
    assert.strictEqual(typeof channel.allowlistedChatId, 'number'); assertions++;
    assert.strictEqual(channel.pairingState, 'paired'); assertions++;
    assert.strictEqual(channel.admissionState, 'approved'); assertions++;
    assert.strictEqual(channel.displayAlias, 'human:johan'); assertions++;
    assert.strictEqual(channel.credentialHandle, 'secret://mac-researcher/telegram/gateway'); assertions++;
    const channelStateText = await page.locator('#liveState').innerText();
    assert(channelStateText.includes('user 999000001')); assertions++;
    assert(channelStateText.includes('chat -1009990000001')); assertions++;
    assert(channelStateText.includes('paired/approved')); assertions++;
    assert(!channelStateText.includes('human:johan')); assertions++;

    // Created and fixture routine inspection, then complete safe browser ownership cycle.
    await page.click('[data-view="operate"]');
    await createdRoutineRow.locator('.runRoutine').click();
    assert((await page.locator('#activityLog').innerText()).includes('Daily source watch: paused offline')); assertions++;
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
