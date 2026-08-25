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
// 구분선(---)은 에디터에서 의미가 없으므로 버린다.
const toPlain = md => md.split('\n')
  .map(l => l.replace(/\*\*/g, '').replace(/^- /, '· ').trimEnd())
  .filter(l => !/^-{3,}$/.test(l.trim()));

// 배치 계획이 없을 때: 표지=맨위, 마무리=맨끝, 나머지는 소제목마다.
function fallbackPlan(md, files) {
  const heads = md.split('\n').filter(l => /^\*\*.+\*\*$/.test(l.trim())).map(l => l.trim().replace(/\*\*/g, ''));
  const mid = files.slice(1, -1);
  const plan = [{ after: 'top', images: files.slice(0, 1) }];
  heads.forEach((h, i) => { if (mid[i]) plan.push({ after: h, images: [mid[i]] }); });
  if (files.length > 1) plan.push({ after: 'end', images: files.slice(-1) });
  return plan;
}

// 본문 줄 + 배치 계획 → [{텍스트 줄들}, {이미지}] 순서 시퀀스
function buildSequence(lines, plan) {
  const at = new Map();               // 줄 인덱스 → 그 줄 뒤에 넣을 이미지들
  let top = [], end = [];
  for (const step of plan) {
    if (step.after === 'top') { top = step.images; continue; }
    if (step.after === 'end') { end = step.images; continue; }
    const idx = lines.findIndex(l => l.includes(step.after));
    if (idx === -1) { console.log(`  ⚠️ 소제목 못 찾음: ${step.after}`); continue; }
    at.set(idx, (at.get(idx) || []).concat(step.images));
  }
  const seq = [];
  if (top.length) seq.push({ img: top });
  let buf = [];
  lines.forEach((l, i) => {
    buf.push(l);
    if (at.has(i)) { seq.push({ text: buf }); buf = []; seq.push({ img: at.get(i) }); }
  });
  if (buf.length) seq.push({ text: buf });
  if (end.length) seq.push({ img: end });
  return seq;
}

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
  // 캐러셀 이미지를 본문 소제목 자리에 나눠 넣는다(blog_image_plan).
  // 계획이 없으면 표지는 맨 위, 마무리는 맨 끝, 나머지는 소제목마다 하나씩.
  const imgDir = path.join(IMAGES_ROOT, date);
  const allImgs = fs.existsSync(imgDir)
    ? fs.readdirSync(imgDir).filter(f => f.endsWith('.jpg')).sort() : [];
  const plan = car.blog_image_plan || fallbackPlan(car.blog, allImgs);
  const planned = plan.reduce((n, s) => n + s.images.length, 0);

  console.log(`제목: ${title}`);
  console.log(`본문: ${lines.length}줄 / 카테고리: ${CATEGORY} / 이미지: ${planned}장 (${plan.length}곳 분산)`);

  const browser = await chromium.launch({ headless: !HEADED });
  const context = await browser.newContext({
    storageState: path.join(__dirname, 'auth.json'), locale: 'ko-KR',
    viewport: { width: 1440, height: 950 },
  });
  const page = await context.newPage();
  await page.goto(`https://blog.naver.com/${BLOG_ID}?Redirect=Write`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(6000);

  // 로그인 쿠키가 만료되면 로그인 페이지로 튕긴다. 에디터 못 찾음과 구분해서 알려준다.
  if (page.url().includes('nid.naver.com')) {
    console.log('❌ 네이버 로그인이 만료됐습니다. `node login.js`로 다시 로그인하세요.');
    await browser.close();
    process.exit(2);
  }

  const frame = page.frames().find(f => f.url().includes('PostWriteForm'));
  if (!frame) { console.log('❌ 에디터 프레임 못 찾음'); await browser.close(); process.exit(1); }
  await prepareEditor(frame, page);

  // 제목
  await clickAt(page, frame.locator('.se-documentTitle .se-text-paragraph').first(), '제목');
  await page.keyboard.type(title, { delay: 12 });
  await page.waitForTimeout(600);

  // 본문: 시퀀스대로 텍스트와 이미지를 번갈아 넣는다
  const seq = buildSequence(lines, plan);
  await clickAt(page, frame.locator('.se-component.se-text .se-text-paragraph').last(), '본문');

  let inserted = 0;
  for (let si = 0; si < seq.length; si++) {
    const step = seq[si];

    if (step.text) {
      for (let i = 0; i < step.text.length; i++) {
        if (step.text[i]) await page.keyboard.type(step.text[i], { delay: 3 });
        if (i < step.text.length - 1) await page.keyboard.press('Enter');
      }
      if (si < seq.length - 1) await page.keyboard.press('Enter');
      await page.waitForTimeout(400);
      continue;
    }

    const files = step.img.map(f => path.join(imgDir, f));
    const before = await frame.locator('.se-component.se-image').count();
    console.log(`  [${si + 1}/${seq.length}] 이미지 ${files.length}장 삽입 시도 (현재 ${before}장)`);

    let done = false;
    for (let tryN = 1; tryN <= 3 && !done; tryN++) {
      try {
        // 삽입 전 상태 정리: 도움말 패널이 툴바를 가릴 수 있다
        const help = frame.locator('.se-help-panel-close-button').first();
        if (await help.count() && await help.isVisible().catch(() => false)) {
          await clickAt(page, help, '도움말 닫기');
        }
        // 본문에 커서를 확실히 둔다(이미지가 선택된 상태면 사진 버튼이 다르게 동작)
        await clickAt(page, frame.locator('.se-component.se-text .se-text-paragraph').last(), '커서 배치');

        const [chooser] = await Promise.all([
          page.waitForEvent('filechooser', { timeout: 20000 }),
          clickAt(page, frame.locator('button:has-text("사진")').first(), '사진'),
        ]);
        await chooser.setFiles(files);

        // 2장 이상이면 "사진 첨부 방식"(개별사진/콜라주/슬라이드) 선택창이 뜬다.
        // 블로그 본문에는 개별사진이 맞다. 안 뜨면 그냥 지나간다.
        if (files.length > 1) {
          const layout = frame.locator(':text-is("개별사진")').first();
          try {
            await layout.waitFor({ state: 'visible', timeout: 12000 });
            await clickAt(page, layout, '개별사진 선택');
            console.log('     첨부 방식: 개별사진');
            await page.waitForTimeout(1500);
          } catch { console.log('     첨부 방식 선택창 없음'); }
        }

        for (let waited = 0; waited < 90000; waited += 2000) {
          await page.waitForTimeout(2000);
          if (await frame.locator('.se-component.se-image').count() >= before + files.length) { done = true; break; }
        }
        if (!done) console.log(`     업로드 대기 초과 (시도 ${tryN})`);
      } catch (e) {
        console.log(`     실패 ${tryN}: ${e.message.split('\n')[0].slice(0, 50)}`);
        if (tryN === 1) {
          await page.screenshot({ path: `/tmp/fail_step${si + 1}.png` });
          const toast = await frame.locator('[class*="toast"], [class*="alert"], [data-group="popupLayer"]').first()
            .innerText().catch(() => '');
          if (toast) console.log(`     화면 알림: ${toast.replace(/\n+/g, ' / ').slice(0, 100)}`);
        }
        await page.waitForTimeout(2000);
      }
    }
    inserted = await frame.locator('.se-component.se-image').count();
    console.log(`     → 누적 ${inserted}/${planned}장`);
    await clickAt(page, frame.locator('.se-component.se-text .se-text-paragraph').last(), '본문 복귀');
  }
  console.log(`\n이미지 삽입 완료: ${inserted}/${planned}장`);
  await page.waitForTimeout(1200);

  // 발행 패널 열기 → 카테고리 지정 (최종 발행 버튼은 절대 누르지 않는다)
  // 이미지 업로드 중 도움말 패널이 다시 뜨면 발행 버튼을 가리므로 매번 닫고 재시도한다.
  let catResult = '실패';
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const help = frame.locator('.se-help-panel-close-button').first();
      if (await help.count() && await help.isVisible().catch(() => false)) {
        await clickAt(page, help, '도움말 닫기');
      }
      await clickAt(page, frame.locator('button.publish_btn__m9KHH').first(), '발행 패널');

      const selBox = frame.locator('button.selectbox_button__jb1Dt').first();
      await selBox.waitFor({ state: 'visible', timeout: 8000 });

      const current = (await selBox.innerText()).trim();
      if (current === CATEGORY) { catResult = `${CATEGORY} (이미 지정됨)`; break; }

      await clickAt(page, selBox, '카테고리 드롭다운');
      await page.waitForTimeout(1200);
      const opt = frame.locator(`:text-is("${CATEGORY}")`);
      for (let k = 0; k < await opt.count(); k++) {
        const box = await opt.nth(k).boundingBox().catch(() => null);
        if (box && box.x > 950 && box.y > 0) {
          await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
          await page.waitForTimeout(1000);
          break;
        }
      }
      const after = (await selBox.innerText().catch(() => '')).trim();
      if (after === CATEGORY) { catResult = CATEGORY; break; }
      catResult = `선택 안 됨 (현재: ${after})`;
    } catch (e) {
      console.log(`  카테고리 시도 ${attempt} 실패: ${e.message.split('\n')[0].slice(0, 60)}`);
      await page.waitForTimeout(2000);
    }
  }
  console.log('카테고리:', catResult);

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
