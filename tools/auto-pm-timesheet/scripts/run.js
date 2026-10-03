// auto-pm-timesheet entry point
// call example inside Codex cua_repl:
//   const { run } = await import('D:/My_play/project_curd/tools/auto-pm-timesheet/scripts/run.js');
//   await run({ date: '2026-10-08', project: 'HubeiJianHang RiskWarning Phase2',
//               task: 'Docs', hours: 8, description: 'write docs' });

const ID = 'ctl00_ctl00_ctl00_CB_CB_ContentPlaceHolderBody_CtlAccountEmployeeTimeEntryDayView1';
const fs = require('fs');

async function bindTab() {
  return await cua.getTab('1', { browser: 'iab' });
}

async function ensureLoggedIn(tab) {
  await tab.playwright.goto('http://pm.git.com.cn/Employee/Default.aspx');
  await tab.playwright.waitForTimeout(1500);
  if (!tab.playwright.url().includes('Default.aspx')) {
    await tab.playwright.locator('input[name*="user" i], input[id*="user" i]').first().fill(process.env.PM_USER);
    await tab.playwright.locator('input[type="password"]').first().fill(process.env.PM_PASSWORD);
    await tab.playwright.locator('input[type="submit"], button:has-text("登录")').first().click();
    await tab.playwright.waitForTimeout(2500);
  }
}

async function gotoTimesheet(tab, date) {
  await tab.playwright.goto('http://pm.git.com.cn/Employee/AccountEmployeeTimeEntryDayView.aspx?StartDate=' + date);
  await tab.playwright.waitForTimeout(2000);
}

function rowId(n) {
  if (n === 0) return 'ctl02';
  if (n === 1) return 'ctl04';
  return 'ctl0' + (n + 3);
}

async function fillRow(tab, n, p) {
  const base = '#' + ID + '_BulkEditGridViewVB1_' + rowId(n);
  await tab.playwright.locator(base + '_ddlAccountProjectId').selectOption({ label: p.project });
  await tab.playwright.waitForTimeout(800);
  await tab.playwright.locator(base + '_ddlAccountProjectTaskId').selectOption({ label: p.task });
  await tab.playwright.locator(base + '_ddlAccountWorkTypeId').selectOption({ label: p.work_type || '本地' });
  const hh = String(p.hours).padStart(2, '0');
  await tab.playwright.locator(base + '_TotalTime').fill(hh + ':00');
  await tab.playwright.locator(base + '_Hours').fill(String(p.hours));
  try { await tab.playwright.locator(base + '_Hours2').fill(String(p.hours)); } catch (e) {}
  await tab.playwright.locator(base + '_SubRemark').fill(p.description);
}

async function saveAndSubmit(tab) {
  tab.playwright.on('dialog', d => d.accept());
  await tab.playwright.locator('#' + ID + '_btnSave').click();
  await tab.playwright.waitForTimeout(2000);
  await tab.playwright.locator('#' + ID + '_btnSubmit').click();
  await tab.playwright.waitForTimeout(2000);
}

async function verify(tab, n) {
  const base = '#' + ID + '_BulkEditGridViewVB1_' + rowId(n);
  const status = await tab.playwright.locator(base + '_imgStatus').getAttribute('alt').catch(() => '');
  const project = await tab.playwright.locator(base + '_ddlAccountProjectId option:checked').textContent();
  const task = await tab.playwright.locator(base + '_ddlAccountProjectTaskId option:checked').textContent();
  const hours = await tab.playwright.locator(base + '_Hours').inputValue();
  const desc = await tab.playwright.locator(base + '_SubRemark').inputValue();
  return { status, project, task, hours, desc };
}

async function run(payload) {
  if (!process.env.PM_USER || !process.env.PM_PASSWORD) {
    throw new Error('Missing PM_USER / PM_PASSWORD env vars');
  }
  const tab = await bindTab();
  await ensureLoggedIn(tab);
  await gotoTimesheet(tab, payload.date);
  await fillRow(tab, payload.rowIndex || 0, payload);
  await saveAndSubmit(tab);
  const result = await verify(tab, payload.rowIndex || 0);
  const buf = await tab.screenshot();
  fs.writeFileSync('timesheet-' + payload.date + '.png', buf);
  return result;
}

module.exports = { run };
