const { chromium } = require('playwright');
const path = require('path');
const IMG = path.resolve(__dirname, '../images/ceo/2026-08-27/01_cover.jpg');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: path.join(__dirname,'auth.json'), locale:'ko-KR', viewport:{width:1440,height:950} });
  const page = await context.newPage();
  await page.goto('https://blog.naver.com/rjsrkdwlzladl1004?Redirect=Write', { waitUntil:'domcontentloaded' });
  await page.waitForTimeout(6000);
  const frame = page.frames().find(f => f.url().includes('PostWriteForm'));
  const cancel = frame.locator('[data-group="popupLayer"] button:has-text("취소")').first();
  if (await cancel.count() && await cancel.isVisible().catch(()=>false)) { await cancel.click({force:true}); await page.waitForTimeout(1500); }

  // 본문에 커서 두기
  const body = frame.locator('.se-component.se-text .se-text-paragraph').last();
  const bb = await body.boundingBox();
  await page.mouse.click(bb.x + bb.width/2, bb.y + bb.height/2);
  await page.waitForTimeout(400);
  await page.keyboard.type('이미지 테스트', { delay: 20 });
  await page.waitForTimeout(500);

  // 사진 버튼 → 파일 선택창 가로채기
  const photo = frame.locator('button:has-text("사진")').first();
  const pb = await photo.boundingBox();
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser', { timeout: 15000 }),
    page.mouse.click(pb.x + pb.width/2, pb.y + pb.height/2),
  ]);
  console.log('✅ 파일 선택창 가로챔');
  await chooser.setFiles([IMG]);
  console.log('파일 전달:', path.basename(IMG));

  await page.waitForTimeout(9000);
  const imgCount = await frame.locator('.se-component.se-image').count();
  console.log('삽입된 이미지 컴포넌트 수:', imgCount);
  console.log(imgCount > 0 ? '✅ 이미지 삽입 성공' : '❌ 실패');
  await browser.close();
})();
