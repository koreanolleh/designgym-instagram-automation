// 블로그 글을 에디터에 채워넣는다 — 제목·본문·이미지·카테고리까지.
// ⚠️ 발행 버튼은 절대 누르지 않는다. 사장님이 직접 누르는 것으로 남긴다.
//
// 사용: node write_post.js <원고json> <날짜> [--category "운동 정보"] [--headed]

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const [specPath, date] = args;
const HEADED = args.includes('--headed');
const catIdx = args.indexOf('--category');
const CATEGORY = catIdx > -1 ? args[catIdx + 1] : '운동 정보';
const BLOG_ID = 'rjsrkdwlzladl1004';
const IMAGES_ROOT = path.resolve(__dirname, '../images/ceo');

// 마크다운 → 에디터 평문. **굵게** 표시는 제거하고 문단 구조만 살린다.
const toPlain = md => md.split('\n').map(l => l.replace(/\*\*/g, '').replace(/^- /, '· ').trimEnd());

async function clickAt(page, locator, label = '') {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const box = await locator.boundingBox();
  if (!box) throw new Error(`클릭 대상을 찾지 못함${label ? ': ' + label : ''}`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForTimeout(500);
}

// 에디터를 깨끗한 상태로 만든다: 복구 팝업 취소 + 도움말 패널 닫기
async function prepareEditor(frame, page) {
  const dim = frame.locator('.se-popup-dim');
  for (let waited = 0; waited < 12000; waited += 500) {
    if (await dim.first().isVisible().catch(() => false)) break;
    await page.waitForTimeout(500);
  }
  for (let i = 0; i < 6; i++) {
    if (!(await dim.first().isVisible().catch(() => false))) break;
    const btn = frame.locator('[data-group="popupLayer"] button:has-text("취소")').first();
    if (!(await btn.count())) break;
    await btn.click({ force: true }).catch(() => {});
    await page.waitForTimeout(1000);
  }
  await dim.first().waitFor({ state: 'hidden', timeout: 8000 }).catch(() => {});

  // 도움말 패널이 우측 발행 버튼을 가리므로 반드시 닫는다
  const help = frame.locator('.se-help-panel-close-button').first();
  if (await help.count() && await help.isVisible().catch(() => false)) {
    await clickAt(page, help, '도움말 닫기');
  }
}

(async () => {
  const week = JSON.parse(fs.readFileSync(specPath, 'utf-8'));
  const car = week.carousels.find(c => c.date === date);
  if (!car) { console.log(`❌ ${date} 원고 없음`); process.exit(1); }

  const title = car.blog_title;
  const lines = toPlain(car.blog);
  const cover = path.join(IMAGES_ROOT, date, '01_cover.jpg');
  const hasCover = fs.existsSync(cover);

  console.log(`제목: ${title}`);
  console.log(`본문: ${lines.length}줄 / 카테고리: ${CATEGORY} / 대표이미지: ${hasCover ? '있음' : '없음'}`);

  const browser = await chromium.launch({ headless: !HEADED });
  const context = await browser.newContext({
    storageState: path.join(__dirname, 'auth.json'), locale: 'ko-KR',
    viewport: { width: 1440, height: 950 },
  });
  const page = await context.newPage();
  await page.goto(`https://blog.naver.com/${BLOG_ID}?Redirect=Write`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(6000);

  const frame = page.frames().find(f => f.url().includes('PostWriteForm'));
  if (!frame) { console.log('❌ 에디터 프레임 못 찾음'); await browser.close(); process.exit(1); }
  await prepareEditor(frame, page);

  // 제목
  await clickAt(page, frame.locator('.se-documentTitle .se-text-paragraph').first(), '제목');
  await page.keyboard.type(title, { delay: 12 });
  await page.waitForTimeout(600);

  // 본문 첫 위치에 대표 이미지 먼저
  await clickAt(page, frame.locator('.se-component.se-text .se-text-paragraph').last(), '본문');
  if (hasCover) {
    const [chooser] = await Promise.all([
      page.waitForEvent('filechooser', { timeout: 15000 }),
      clickAt(page, frame.locator('button:has-text("사진")').first(), '사진'),
    ]);
    await chooser.setFiles([cover]);
    await page.waitForTimeout(9000);
    console.log(`이미지 삽입: ${await frame.locator('.se-component.se-image').count()}장`);
    // 이미지 뒤로 커서 이동
    await clickAt(page, frame.locator('.se-component.se-text .se-text-paragraph').last(), '본문 복귀');
  }

  // 본문
  for (let i = 0; i < lines.length; i++) {
    if (lines[i]) await page.keyboard.type(lines[i], { delay: 3 });
    if (i < lines.length - 1) await page.keyboard.press('Enter');
  }
  await page.waitForTimeout(1500);

  // 발행 패널 열기 → 카테고리 지정 (최종 발행은 누르지 않음)
  await clickAt(page, frame.locator('button.publish_btn__m9KHH').first(), '발행 패널');
  await page.waitForTimeout(2500);

  const selBox = frame.locator('button.selectbox_button__jb1Dt').first();
  const current = (await selBox.innerText().catch(() => '')).trim();
  if (current !== CATEGORY) {
    await clickAt(page, selBox, '카테고리 드롭다운');
    await page.waitForTimeout(1200);
    const opt = frame.locator(`:text-is("${CATEGORY}")`);
    let picked = false;
    for (let k = 0; k < await opt.count(); k++) {
      const box = await opt.nth(k).boundingBox().catch(() => null);
      if (box && box.x > 950 && box.y > 0) {
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        picked = true; break;
      }
    }
    await page.waitForTimeout(1000);
    console.log(picked ? `카테고리 선택: ${CATEGORY}` : `⚠️ 카테고리 "${CATEGORY}"를 찾지 못함`);
  } else {
    console.log(`카테고리 이미 ${CATEGORY}`);
  }

  // 임시저장 (발행 아님)
  await clickAt(page, frame.locator('button.save_btn__bzc5B').first(), '저장');
  await page.waitForTimeout(3000);

  const finalCat = (await frame.locator('button.selectbox_button__jb1Dt').first().innerText().catch(() => '?')).trim();
  const imgs = await frame.locator('.se-component.se-image').count();
  const bodyLen = (await frame.locator('.se-container').innerText()).trim().length;
  console.log(`\n최종 상태 — 카테고리 ${finalCat} / 이미지 ${imgs}장 / 총 ${bodyLen}자`);
  console.log('✅ 임시저장 완료. 발행 버튼은 누르지 않았습니다.');

  await browser.close();
})();
