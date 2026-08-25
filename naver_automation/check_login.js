// auth.json 세션으로 블로그 관리 페이지에 실제로 들어가지는지 확인.
// HEADED=1 로 실행하면 창을 띄워서 확인(헤드리스 차단 여부 구분용).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const AUTH = path.join(__dirname, 'auth.json');

(async () => {
  if (!fs.existsSync(AUTH)) { console.log('❌ auth.json 없음 — 먼저 login.js 실행'); process.exit(1); }

  const headless = process.env.HEADED !== '1';
  const browser = await chromium.launch({ headless });
  const context = await browser.newContext({ storageState: AUTH, locale: 'ko-KR' });
  const page = await context.newPage();

  await page.goto('https://admin.blog.naver.com/rjsrkdwlzladl1004', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  const url = page.url();
  const title = await page.title();
  const loggedOut = url.includes('nid.naver.com') || /로그인/.test(title);

  console.log(`모드: ${headless ? 'headless' : 'headed'}`);
  console.log('URL  :', url.slice(0, 90));
  console.log('타이틀:', title);
  console.log(loggedOut ? '❌ 로그인 안 됨' : '✅ 로그인 유지됨');

  await browser.close();
})();
