// 블로그 글을 에디터에 채워넣고 임시저장한다. 발행은 하지 않는다.
// 사용: node write_post.js <원고json> <날짜> [--headed]
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const [specPath, date] = process.argv.slice(2);
const HEADED = process.argv.includes('--headed');
const BLOG_ID = 'rjsrkdwlzladl1004';

// 마크다운 → 에디터용 평문 (굵게 표시 **…** 는 제거, 문단 유지)
function toPlain(md) {
  return md.split('\n').map(l => l.replace(/\*\*/g, '').replace(/^- /, '· ').trimEnd());
}


// Playwright의 가림막 판정이 래퍼 div를 오인하므로 좌표로 직접 클릭한다.
async function clickAt(page, locator) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const box = await locator.boundingBox();
  if (!box) throw new Error('클릭 대상의 위치를 찾지 못함');
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForTimeout(400);
}

// 에디터 확인 팝업("작성 중인 글이 있습니다")을 닫는다.
// 팝업은 페이지 로드 후 늦게 뜨므로 나타날 때까지 기다렸다가 누르고,
// dim 레이어가 완전히 사라진 뒤에 반환한다.
async function dismissPopup(frame, page, choice = '취소') {
  const dim = frame.locator('.se-popup-dim');
  for (let waited = 0; waited < 12000; waited += 500) {
    if (await dim.first().isVisible().catch(() => false)) break;
    await page.waitForTimeout(500);
  }
  for (let i = 0; i < 6; i++) {
    if (!(await dim.first().isVisible().catch(() => false))) break;
    const btn = frame.locator(`[data-group="popupLayer"] button:has-text("${choice}")`).first();
    if (await btn.count()) {
      await btn.click({ force: true }).catch(() => {});
      await page.waitForTimeout(1000);
    } else break;
  }
  await dim.first().waitFor({ state: 'hidden', timeout: 8000 }).catch(() => {});
}

(async () => {
  const week = JSON.parse(fs.readFileSync(specPath, 'utf-8'));
  const car = week.carousels.find(c => c.date === date);
  if (!car) { console.log(`❌ ${date} 원고 없음`); process.exit(1); }

  const title = car.blog_title;  // 따옴표는 제목의 일부라 그대로 둔다
  const lines = toPlain(car.blog);
  console.log(`제목: ${title}`);
  console.log(`본문: ${lines.length}줄`);

  const browser = await chromium.launch({ headless: !HEADED });
  const context = await browser.newContext({
    storageState: path.join(__dirname, 'auth.json'), locale: 'ko-KR',
    viewport: { width: 1440, height: 950 },
  });
  const page = await context.newPage();
  await page.goto(`https://blog.naver.com/${BLOG_ID}?Redirect=Write`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);

  const frame = page.frames().find(f => f.url().includes('PostWriteForm'));
  if (!frame) { console.log('❌ 에디터 프레임 못 찾음'); await browser.close(); process.exit(1); }

  // "작성 중인 글이 있습니다" 복구 팝업 → 취소(새 글로 시작)
  await dismissPopup(frame, page);

  await clickAt(page, frame.locator('.se-documentTitle .se-text-paragraph').first());
  await page.keyboard.type(title, { delay: 15 });
  await page.waitForTimeout(600);

  await clickAt(page, frame.locator('.se-component.se-text .se-text-paragraph').last());
  for (let i = 0; i < lines.length; i++) {
    if (lines[i]) await page.keyboard.type(lines[i], { delay: 4 });
    if (i < lines.length - 1) await page.keyboard.press('Enter');
  }
  await page.waitForTimeout(1200);

  // 임시저장 (발행 아님)
  await clickAt(page, frame.locator('button:has-text("저장")').first());
  await page.waitForTimeout(2500);

  const titleGot = (await frame.locator('.se-documentTitle').innerText()).trim();
  const bodyGot  = (await frame.locator('.se-container').innerText()).trim();
  console.log(`\n입력 확인 — 제목 ${titleGot.length}자 / 본문 ${bodyGot.length}자`);
  console.log('✅ 임시저장 완료 (발행 안 함)');

  await browser.close();
})();
