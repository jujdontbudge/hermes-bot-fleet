#!/usr/bin/env node
const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  const [base, credentialPath, screenshotPath] = process.argv.slice(2);
  if (!base || !credentialPath || !screenshotPath) throw new Error('base credentialPath screenshotPath required');
  const credential = fs.readFileSync(credentialPath, 'utf8').trim();
  fs.unlinkSync(credentialPath);
  const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({headless: true, ...(fs.existsSync(chromePath) ? {executablePath: chromePath} : {})});
  const context = await browser.newContext({viewport: {width: 1440, height: 900}});
  const response = await context.request.post(`${base}/__takeover_bootstrap`, {
    headers: {'X-Hermes-Takeover-Credential': credential},
  });
  if (response.status() !== 204 || response.headers()['cache-control'] !== 'no-store') throw new Error('bootstrap failed');
  const page = await context.newPage();
  await page.goto(`${base}/?autoconnect=1&resize=scale`, {waitUntil: 'domcontentloaded'});
  await page.waitForTimeout(5000);
  await page.screenshot({path: screenshotPath, fullPage: true});
  const canvasCount = await page.locator('canvas').count();
  if (canvasCount < 1) throw new Error('authenticated noVNC canvas not observed');
  await browser.close();
  console.log(JSON.stringify({bootstrap_status: 204, cache_control_no_store: true, credential_in_url: false, credential_file_consumed: !fs.existsSync(credentialPath), visual_capture_written: fs.existsSync(screenshotPath), secret_values_printed: false}));
})().catch(err => { console.error(err.message); process.exit(1); });
