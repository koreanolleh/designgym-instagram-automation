// 네이버 로그인 → 세션을 auth.json으로 저장.
// 어제 실패 원인: NID_AUT/NID_SES가 '세션 쿠키'라 브라우저를 닫으면 디스크에 안 남았음.
// 해결: (1) "로그인 상태 유지" 체크 (2) storageState로 세션 쿠키까지 명시적으로 저장.
const { chromium } = require('playwright');
const path = require('path');

const AUTH = path.join(__dirname, 'auth.json');

(async () => {
  const context = await chromium.launchPersistentContext(path.join(__dirname, 'profile'), {
    headless: false,
    viewport: { width: 1280, height: 900 },
    locale: 'ko-KR',
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto('https://nid.naver.com/nidlogin.login');

  console.log('');
  console.log('  네이버 로그인 창이 열렸습니다.');
  console.log('  ★ "로그인 상태 유지"를 반드시 체크하고 로그인해주세요.');
  console.log('  로그인이 감지되면 자동으로 저장하고 창을 닫습니다. (최대 5분 대기)');
  console.log('');

  const deadline = Date.now() + 5 * 60 * 1000;
  let ok = false;

  while (Date.now() < deadline) {
    const cookies = await context.cookies();
    const auth = cookies.find(c => c.name === 'NID_AUT');
    const ses  = cookies.find(c => c.name === 'NID_SES');
    if (auth && ses) {
      const persistent = auth.expires && auth.expires > 0;
      console.log(`  ✅ 로그인 감지됨 (NID_AUT ${persistent ? '영구쿠키' : '세션쿠키'})`);
      if (!persistent) {
        console.log('  ⚠️  "로그인 상태 유지"가 꺼진 것 같습니다. auth.json으로는 저장되지만');
        console.log('     안정성을 위해 체크 후 다시 로그인하는 걸 권장합니다.');
      }
      await context.storageState({ path: AUTH });
      console.log(`  💾 세션 저장 완료 → ${AUTH}`);
      ok = true;
      break;
    }
    await page.waitForTimeout(2000);
  }

  if (!ok) console.log('  ❌ 5분 안에 로그인이 감지되지 않았습니다.');
  await context.close();
  console.log('  창을 닫았습니다. 터미널로 돌아가셔도 됩니다.');
})();
