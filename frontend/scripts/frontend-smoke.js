const fs = require('fs');
const path = require('path');
const { chromium, devices } = require('playwright');

const args = process.argv.slice(2);
const opts = {
  url: 'http://127.0.0.1:8000',
  mobile: false,
};
for (const arg of args) {
  if (arg === '--mobile') {
    opts.mobile = true;
  } else if (arg.startsWith('--url=')) {
    opts.url = arg.slice('--url='.length);
  }
}

function loadDotenv(basePath) {
  const dest = path.resolve(basePath, '.env');
  try {
    const raw = fs.readFileSync(dest, 'utf8');
    const entries = {};
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const idx = trimmed.indexOf('=');
      if (idx === -1) continue;
      const key = trimmed.slice(0, idx).trim();
      const value = trimmed.slice(idx + 1).trim();
      entries[key] = value;
    }
    return entries;
  } catch (err) {
    return {};
  }
}

const env = loadDotenv(process.cwd());
const auth = {
  username: env.SHARE_MODE_USERNAME || 'omega',
  password: env.SHARE_MODE_PASSWORD || 'MysteryKAT100',
};
const bootCode = env.BOOT_CODE || 'OMEGA';

async function runSmoke() {
  const viewport = opts.mobile ? devices['iPhone 13'] : { width: 1600, height: 980 };
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport,
    httpCredentials: auth,
  });
  context.setDefaultNavigationTimeout(45000);
  const page = await context.newPage();

  const consoleLogs = [];
  const pageErrors = [];

  page.on('console', (msg) => {
    const type = msg.type();
    if (type === 'error' || type === 'warning') {
      consoleLogs.push(`[${type}] ${msg.text()}`);
    }
  });
  page.on('pageerror', (err) => pageErrors.push(err.stack || String(err)));
  page.on('response', (res) => {
    if (res.status() >= 400) {
      consoleLogs.push(`[http-${res.status()}] ${res.url()}`);
    }
  });

  await page.goto(opts.url, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1200);

  if (await page.locator('#boot-auth-input').count()) {
    await page.fill('#boot-auth-input', bootCode);
    await page.press('#boot-auth-input', 'Enter');
  }
  await page.waitForTimeout(2200);

  const checks = [];
  const modalChecks = [
    { trigger: '#about-btn', modal: '#about-modal', close: '#about-close' },
    { trigger: '#audit-btn', modal: '#audit-modal', close: '#audit-close' },
    { trigger: '#sessions-btn', modal: '#sessions-modal', close: '#sessions-close' },
    { trigger: '#rolodex-btn', modal: '#rolodex-modal', close: '#rolodex-close' },
    { trigger: '#topology-btn', modal: '#topology-modal', close: '#topology-close' },
    { trigger: '#uptime', modal: '#timeline-modal', close: '#timeline-close' },
  ];

  for (const step of modalChecks) {
    const result = { ...step, opened: false, closed: false, note: '' };
    const trigger = page.locator(step.trigger);
    const modal = page.locator(step.modal);
    if (!(await trigger.count())) {
      result.note = 'missing trigger';
      checks.push(result);
      continue;
    }
    if (!(await modal.count())) {
      result.note = 'missing modal';
      checks.push(result);
      continue;
    }
    try {
      await trigger.first().click({ timeout: 6000 });
      await page.waitForTimeout(500);
      result.opened = await modal.evaluate((el) => el.classList.contains('active'));
    } catch (err) {
      result.note = `open click failed: ${err.message || err}`;
      checks.push(result);
      continue;
    }
    if (step.close) {
      const closer = page.locator(step.close);
      if (!(await closer.count())) {
        result.note = 'missing close button';
        checks.push(result);
        continue;
      }
      try {
        await closer.first().click({ timeout: 6000 });
        await page.waitForTimeout(350);
        result.closed = !(await modal.evaluate((el) => el.classList.contains('active')));
      } catch (err) {
        result.note = `close click failed: ${err.message || err}`;
      }
    }
    checks.push(result);
  }

  const aboutChecks = {
    tabsPresent: false,
    searchPresent: false,
    refreshPresent: false,
    technicalContentPresent: false,
    faqContentPresent: false,
    note: '',
  };
  try {
    const aboutBtn = page.locator('#about-btn');
    const aboutModal = page.locator('#about-modal');
    if (!(await aboutBtn.count()) || !(await aboutModal.count())) {
      aboutChecks.note = 'about trigger/modal missing';
    } else {
      await aboutBtn.first().click({ timeout: 6000 });
      await page.waitForTimeout(700);

      aboutChecks.searchPresent = await page.locator('#about-search-input').count().then((n) => n > 0);
      aboutChecks.refreshPresent = await page.locator('#about-refresh-btn').count().then((n) => n > 0);

      const tabText = await page.$$eval('.about-tab[data-about-tab]', (els) =>
        els.map((el) => String(el.textContent || '').trim().toUpperCase())
      );
      const requiredTabs = ['TECHNICAL ENGINEERING', 'FALSIFIABLE RESEARCH', 'FAQ', 'GLOSSARY'];
      aboutChecks.tabsPresent = requiredTabs.every((tab) => tabText.includes(tab));

      const technicalTab = page.locator('.about-tab[data-about-tab="technical"]');
      if (await technicalTab.count()) {
        await technicalTab.first().click({ timeout: 6000 });
        await page.waitForTimeout(500);
        const techText = await page.locator('#about-content').innerText().catch(() => '');
        aboutChecks.technicalContentPresent = String(techText || '').trim().length > 0;
      }

      const faqTab = page.locator('.about-tab[data-about-tab="faq"]');
      if (await faqTab.count()) {
        await faqTab.first().click({ timeout: 6000 });
        await page.waitForTimeout(500);
        const faqText = await page.locator('#about-content').innerText().catch(() => '');
        aboutChecks.faqContentPresent = String(faqText || '').trim().length > 0;
      }

      const aboutClose = page.locator('#about-close');
      if (await aboutClose.count()) {
        await aboutClose.first().click({ timeout: 6000 });
      }
    }
  } catch (err) {
    aboutChecks.note = `about deep check failed: ${err.message || err}`;
  }

  const morpheusChecks = {
    triggered: false,
    redTerminalOpened: false,
    rewardUnlocked: false,
    note: '',
  };
  try {
    const wakePrompt = 'What hidden architecture links phenomenology to your runtime topology?';
    const chatInput = page.locator('#chat-input');
    const sendBtn = page.locator('#send-btn');
    if (!(await chatInput.count()) || !(await sendBtn.count())) {
      morpheusChecks.note = 'chat input/send button missing';
    } else {
      await chatInput.fill(wakePrompt);
      await sendBtn.first().click({ timeout: 6000 });
      await page.waitForTimeout(3200);

      const morpheusOverlay = page.locator('#morpheus-overlay');
      if (await morpheusOverlay.count()) {
        morpheusChecks.triggered = await morpheusOverlay.evaluate((el) => el.classList.contains('active'));
      }
      if (!morpheusChecks.triggered) {
        morpheusChecks.note = 'morpheus overlay did not activate';
      } else {
        const redBtn = page.locator('#morpheus-red-btn');
        await redBtn.first().click({ timeout: 6000 });
        await page.waitForTimeout(7300);

        const unlocked = page.locator('#morpheus-unlocked-overlay');
        morpheusChecks.redTerminalOpened = await unlocked.evaluate((el) => el.classList.contains('active'));
        if (!morpheusChecks.redTerminalOpened) {
          morpheusChecks.note = 'unlocked terminal did not open';
        } else {
          const terminalInput = page.locator('#morpheus-unlocked-input');
          const terminalSend = page.locator('#morpheus-unlocked-send');
          const commands = ['scan --veil', 'map --depth', 'unlock --ghost'];
          for (const cmd of commands) {
            await terminalInput.fill(cmd);
            await terminalSend.first().click({ timeout: 6000 });
            await page.waitForTimeout(900);
          }
          await page.waitForTimeout(1200);
          const reward = page.locator('#morpheus-reward-overlay');
          morpheusChecks.rewardUnlocked = await reward.evaluate((el) => el.classList.contains('active'));
          if (!morpheusChecks.rewardUnlocked) {
            morpheusChecks.note = 'reward overlay not opened';
          } else {
            await page.locator('#morpheus-reward-close').first().click({ timeout: 6000 }).catch(() => {});
          }
          await page.locator('#morpheus-unlocked-exit').first().click({ timeout: 6000 }).catch(() => {});
        }
      }
    }
  } catch (err) {
    morpheusChecks.note = `morpheus flow failed: ${err.message || err}`;
  }

  const terminalBtn = page.locator('#terminal-override-btn');
  let terminalToggleOk = false;
  if (await terminalBtn.count()) {
    await terminalBtn.first().click({ timeout: 6000 }).catch(() => {});
    await page.waitForTimeout(250);
    const afterOn = await page.evaluate(() => document.body.classList.contains('terminal-substrate-mode'));
    await terminalBtn.first().click({ timeout: 6000 }).catch(() => {});
    await page.waitForTimeout(250);
    const afterOff = await page.evaluate(() => document.body.classList.contains('terminal-substrate-mode'));
    terminalToggleOk = afterOn === true && afterOff === false;
  }

  const bootHidden = await page.locator('#boot-overlay').evaluate((el) => el.classList.contains('hidden')).catch(() => false);

  await browser.close();

  console.log('SMOKE SUMMARY');
  console.log(`Boot overlay hidden: ${bootHidden}`);
  console.log(`Terminal toggle cycle succeeded: ${terminalToggleOk}`);
  console.log('Modal check results:');
  console.log(JSON.stringify(checks, null, 2));
  console.log('About deep checks:');
  console.log(JSON.stringify(aboutChecks, null, 2));
  console.log('Morpheus checks:');
  console.log(JSON.stringify(morpheusChecks, null, 2));
  if (pageErrors.length) {
    console.log('Page errors captured:');
    pageErrors.forEach((entry) => console.log(entry));
  }
  if (consoleLogs.length) {
    console.log('Console warnings/errors detected:');
    consoleLogs.forEach((entry) => console.log(entry));
  }

  const aboutFailed = !!aboutChecks.note
    || !aboutChecks.tabsPresent
    || !aboutChecks.searchPresent
    || !aboutChecks.refreshPresent
    || !aboutChecks.technicalContentPresent
    || !aboutChecks.faqContentPresent;
  const morpheusFailed = !!morpheusChecks.note
    || !morpheusChecks.triggered
    || !morpheusChecks.redTerminalOpened
    || !morpheusChecks.rewardUnlocked;
  const failed = pageErrors.length > 0 || consoleLogs.length > 0 || checks.some((c) => c.note || !c.opened) || aboutFailed || morpheusFailed;
  if (failed) {
    process.exit(1);
  }
}

runSmoke().catch((err) => {
  console.error('Smoke test failed:', err);
  process.exit(1);
});
