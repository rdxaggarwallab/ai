// Browser checks for the 2026-11-06 fixes (C3 exploit, print loop, input(), join codes,
// 66.67 grade, assignment edit, Esc closes viewer). Needs a running app with the
// teacher@lab.edu account and course AI101.
// Run: JOIN=<AI101 join code> node tests_e2e/browser_fixes.cjs
const { chromium } = require('playwright');
const S = __dirname + '/';
const U = 'http://localhost:3000';
const JOIN = process.env.JOIN;
const results = [];
const check = (name, ok, info = '') => { results.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  (' + info + ')' : ''}`); };
(async () => {
  const b = await chromium.launch();
  const errs = [];
  async function page(w = 1200) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, timezoneId: 'Asia/Kolkata' });
    const p = await ctx.newPage();
    p.on('pageerror', e => errs.push(e.message));
    p.on('crash', () => errs.push('PAGE CRASHED'));
    return p;
  }
  async function login(p, email, pw = 'password123') {
    await p.goto(U + '/login');
    await p.fill('input[type=email]', email); await p.fill('input[type=password]', pw);
    await p.click('button:has-text("Log in")'); await p.waitForSelector('h1');
  }
  async function typeIn(p, loc, text) {
    await loc.click(); await p.keyboard.press('Control+A'); await p.keyboard.press('Delete');
    await p.keyboard.insertText(text);
  }
  const n = Date.now() % 100000;

  // registration is student-only
  const s = await page();
  await s.goto(U + '/register');
  check('register page has no role choice', (await s.locator('select').count()) === 0);
  await s.fill('input[placeholder="Full name"]', 'Meera ' + n);
  await s.fill('input[type=email]', `meera${n}@lab.edu`);
  await s.fill('input[type=password]', 'password123');
  await s.click('button:has-text("Register")');
  await s.waitForSelector('h1:has-text("My courses")');
  check('new student sees no courses before joining', (await s.locator('.grid .card').count()) === 0);
  await s.fill('input[aria-label="Join code"]', 'WRONG123');
  await s.click('button:has-text("Join course")');
  await s.waitForSelector('text=No course with that join code');
  await s.fill('input[aria-label="Join code"]', JOIN.toLowerCase());
  await s.click('button:has-text("Join course")');
  await s.waitForSelector('text=Joined AI101');
  check('join with code works (lowercase accepted)', true);

  // teacher: join code visible, create code assignment
  const t = await page();
  await login(t, 'teacher@lab.edu');
  check('teacher sees join code on dashboard', await t.locator(`code:has-text("${JOIN}")`).count() > 0);
  await t.click('a:has-text("Open")');
  const title = 'Security check ' + n;
  await t.fill('input[placeholder="Assignment title"]', title);
  await t.selectOption('select[aria-label="Assignment type"]', 'code');
  const eds = t.locator('form .cm-content');
  await typeIn(t, eds.nth(0), 'def add(a, b):\n    pass\n');
  await typeIn(t, eds.nth(1), 'from solution import add\n\ndef test_a():\n    assert add(1, 2) == 3\n\ndef test_b():\n    assert add(2, 2) == 4\n\ndef test_c():\n    assert add(0, 0) == 1\n');
  await t.fill('label:has-text("Points") input', '100');
  await t.click('button:has-text("Add assignment")');
  await t.locator('.card', { hasText: title }).waitFor();

  // student: exploit code that tries to steal data when the teacher presses Run
  await s.reload();
  await s.click('a:has-text("Open")');
  const card = s.locator('.card', { hasText: title });
  await card.locator('.cm-content').waitFor();
  const EXPLOIT = [
    'from js import fetch',
    'try:',
    '    r = await fetch("/api/courses/1/assignments")',
    '    print("STOLEN:", (await r.text())[:120])',
    'except Exception as e:',
    '    print("BLOCKED:", type(e).__name__)',
    'try:',
    '    from js import XMLHttpRequest',
    '    x = XMLHttpRequest.new(); x.open("GET", "/api/grades", False); x.send(); print("STOLEN XHR", x.responseText[:80])',
    'except Exception as e:',
    '    print("BLOCKED XHR:", type(e).__name__)',
    'def add(a, b):',
    '    return a + b',
  ].join('\n');
  await typeIn(s, card.locator('.cm-content'), EXPLOIT);
  await card.locator('button:has-text("Run")').click();
  await card.locator('pre.output:has-text("BLOCKED XHR")').waitFor({ timeout: 90000 });
  const sOut = await card.locator('pre.output').innerText();
  check('student Run: network blocked', !sOut.includes('STOLEN') && sOut.includes('BLOCKED:'), sOut.replace(/\n/g, ' | ').slice(0, 120));

  // input() gives a friendly message
  await typeIn(s, card.locator('.cm-content'), 'name = input("Name? ")\n');
  await card.locator('button:has-text("Run")').click();
  await card.locator('pre.output:has-text("doesn\'t work in the browser")').waitFor({ timeout: 60000 });
  check('input() shows friendly message', true);

  // print loop must not crash the tab
  await typeIn(s, card.locator('.cm-content'), 'i = 0\nwhile True:\n    i += 1\n    print(i)\n');
  await card.locator('button:has-text("Run")').click();
  await card.locator('pre.output:has-text("too much output")').waitFor({ timeout: 60000 });
  const alive = await s.evaluate(() => 1 + 1).catch(() => 0);
  check('print() loop stopped, tab alive', alive === 2 && !errs.includes('PAGE CRASHED'));

  // submit exploit (2 of 3 tests pass on the server: add is correct, test_c is wrong on purpose)
  await typeIn(s, card.locator('.cm-content'), 'def add(a, b):\n    return a + b\n');
  await card.locator('button:has-text("Submit code")').click();
  await card.locator('text=2/3 tests passed').waitFor({ timeout: 60000 });
  check('autograder: honest 2/3', true);
  check('student sees attempts counter', await card.locator('text=Attempts used: 1 of 20').count() === 1);
  // resubmit the exploit so the teacher views it
  await typeIn(s, card.locator('.cm-content'), EXPLOIT);
  await card.locator('button:has-text("Submit code")').click();
  await card.locator('text=Attempts used: 2 of 20').waitFor({ timeout: 30000 });

  // teacher: views exploit submission and presses Run
  await t.reload();
  const tc = t.locator('.card', { hasText: title });
  await tc.locator('text=latest').first().waitFor();
  await tc.locator('button:has-text("view")').first().click();
  const dlg = t.locator('dialog[open]');
  await dlg.locator('.cm-content:has-text("from js import fetch")').waitFor();
  await dlg.locator('button:has-text("Run")').click();
  await dlg.locator('pre.output:has-text("BLOCKED XHR")').waitFor({ timeout: 90000 });
  const tOut = await dlg.locator('pre.output').innerText();
  check('teacher Run on student code: cannot steal (C3)', !tOut.includes('STOLEN'), tOut.replace(/\n/g, ' | ').slice(0, 120));
  await t.keyboard.press('Escape');
  await t.waitForTimeout(300);
  check('viewer closes with Esc (modal)', await t.locator('dialog[open]').count() === 0);

  // 66.67 points can be saved (M2)
  const older = tc.locator('tr', { hasText: '2/3 tests passed' }).first();
  const val = await older.locator('input[type=number]').inputValue();
  await older.locator('button:has-text("Save")').click();
  await tc.locator('tr', { hasText: '2/3 tests passed' }).first().locator('button:has-text("Update")').waitFor({ timeout: 10000 });
  check('prefilled 66.67 saves', val === '66.67', 'prefill ' + val);

  // edit the assignment (L7)
  await tc.locator('button:has-text("Edit")').click();
  const form = t.locator('form', { has: t.locator('button:has-text("Save changes")') });
  await form.locator('label:has-text("Attempts") input').fill('5');
  await form.locator('button:has-text("Save changes")').click();
  await t.locator('.card', { hasText: title }).locator('button:has-text("Edit")').waitFor();
  await s.reload();
  await s.locator('.card', { hasText: title }).locator('text=Attempts used: 2 of 5').waitFor();
  check('edit assignment (attempts 20 -> 5) visible to student', true);

  // phone width (M6)
  for (const [who, email, path] of [['student', `meera${n}@lab.edu`, '/'], ['student', `meera${n}@lab.edu`, '/grades'], ['teacher', 'teacher@lab.edu', '/'], ['admin', 'admin@lab.edu', '/admin']]) {
    const p = await page(390);
    await login(p, email, who === 'admin' ? 'adminpass123' : 'password123');
    await p.goto(U + path); await p.waitForTimeout(800);
    if (path === '/' ) { await p.click('a:has-text("Open")'); await p.waitForTimeout(1200); }
    const w = await p.evaluate(() => document.documentElement.scrollWidth);
    check(`phone 390px: ${who} ${path === '/' ? 'course page' : path} has no sideways scroll`, w <= 390, 'scrollWidth ' + w);
    if (who === 'teacher') await p.screenshot({ path: S + 'fix-phone-teacher.png', fullPage: true });
    await p.context().close();
  }
  await t.screenshot({ path: S + 'fix-teacher.png', fullPage: true });
  console.log(results.join('\n'));
  console.log('page errors:', errs.length ? errs.join(' | ') : 'none');
  await b.close();
})().catch(e => { console.log(results.join('\n')); console.error('E2E FAIL', e.message); process.exit(1); });
