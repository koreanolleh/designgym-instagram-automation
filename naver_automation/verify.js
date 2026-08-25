// 임시저장된 글을 불러와 제목·본문·이미지·카테고리를 확인한다.
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: path.join(__dirname,'auth.json'), locale:'ko-KR', viewport:{width:1440,height:950} });
  const page = await context.newPage();
  await page.goto('https://blog.naver.com/rjsrkdwlzladl1004?Redirect=Write', { waitUntil:'domcontentloaded' });
  await page.waitForTimeout(6000);
  const frame = page.frames().find(f => f.url().includes('PostWriteForm'));

  const help0 = frame.locator('.se-help-panel-close-button').first();
  if (await help0.count() && await help0.isVisible().catch(()=>false)) { await help0.click({force:true}); await page.waitForTimeout(800); }

  // 저장함 열기
  const cnt = frame.locator('button.save_count_btn__ZTLNa').first();
  const cb = await cnt.boundingBox();
  console.log('저장함 개수 표시:', (await cnt.innerText()).trim());
  await page.mouse.click(cb.x+cb.width/2, cb.y+cb.height/2);
  await page.waitForTimeout(2500);

  const listTxt = (await frame.locator('body').innerText()).replace(/\n+/g,' / ');
  const li = listTxt.indexOf('임시저장');
  console.log('저장함 목록:', listTxt.slice(Math.max(0,li-50), li+250));

  // 첫 번째 저장 글 불러오기
  const item = frame.locator('[class*="save_list"] li, [class*="list_item"]').first();
  if (await item.count()) {
    const ib = await item.boundingBox();
    if (ib) { await page.mouse.click(ib.x+50, ib.y+20); await page.waitForTimeout(3500); }
  }

  const title = (await frame.locator('.se-documentTitle').innerText().catch(()=>'')).trim();
  const imgs = await frame.locator('.se-component.se-image').count();
  const body = (await frame.locator('.se-container').innerText().catch(()=>'')).trim();

  console.log('제목:', JSON.stringify(title.slice(0,50)));
  console.log('이미지:', imgs, '장');
  console.log('전체 길이:', body.length, '자');

  // 발행 패널에서 카테고리 확인
  const pub = frame.locator('button.publish_btn__m9KHH').first();
  const b = await pub.boundingBox();
  if (b) {
    await page.mouse.click(b.x+b.width/2, b.y+b.height/2);
    await page.waitForTimeout(2500);
    const cat = (await frame.locator('button.selectbox_button__jb1Dt').first().innerText().catch(()=>'?')).trim();
    console.log('카테고리:', cat);
  }
  await browser.close();
})();
