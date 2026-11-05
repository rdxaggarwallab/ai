// Browser run of the docs/TESTING.md checklist (testing session, 2026-11-06).
// Needs: API on :5000, `flask grade-worker` (docker mode), Vite on :3000, admin admin@lab.edu / adminpass123.
// Usage: node tests_e2e/browser_checklist.cjs <screenshot-dir>
// Writes results.json into the screenshot dir. Each step records ok / fail / warn + a note.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.BASE || "http://localhost:3000";
const OUT = process.argv[2] || "shots";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const consoleErrors = [];
const rec = (id, status, note) => { results.push({ id, status, note }); console.log(`[${status}] ${id}: ${note}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function step(id, fn) {
  try { await fn(); } catch (e) { rec(id, "fail", "exception: " + String(e.message).split("\n")[0]); }
}

async function newPage(browser, label, opts = {}) {
  const ctx = await browser.newContext({ timezoneId: "Asia/Kolkata", locale: "en-IN", ...opts });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(`${label}: ${m.text()}`); });
  page.on("pageerror", (e) => consoleErrors.push(`${label} pageerror: ${e.message}`));
  return page;
}

async function register(page, name, email, role = "student") {
  await page.goto(BASE + "/register");
  await page.getByPlaceholder("Full name").fill(name);
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 characters)").fill("password123");
  await page.locator("select").selectOption(role);
  await page.getByRole("button", { name: "Register" }).click();
  await page.getByRole("heading", { name: "Courses" }).waitFor({ timeout: 10000 });
}

async function login(page, email, password = "password123") {
  await page.goto(BASE + "/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
}

function card(page, title) {
  return page.locator(".card").filter({ has: page.getByRole("heading", { name: title, exact: false }) }).first();
}

async function setCode(page, editor, code) {
  const content = editor.locator(".cm-content");
  await content.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.press("Delete");
  await page.keyboard.insertText(code);
}

async function createAssignment(page, { title, kind = "file", due, points, allowLate = true, penalty, starter, tests }) {
  const form = page.locator("form.card").filter({ has: page.getByPlaceholder("Assignment title") });
  await form.getByPlaceholder("Assignment title").fill(title);
  await form.getByLabel("Assignment type").selectOption(kind);
  if (due) await form.locator('input[type="datetime-local"]').fill(due);
  if (points != null) await form.locator('label:has-text("Points") input').fill(String(points));
  const late = form.locator('label:has-text("Accept late work") input');
  if ((await late.isChecked()) !== allowLate) await late.click();
  if (penalty != null && allowLate) await form.locator('label:has-text("Late penalty") input').fill(String(penalty));
  if (kind === "code") {
    const editors = form.locator(".editor");
    if (starter != null) await setCode(page, editors.nth(0), starter);
    if (tests === "example") await form.getByRole("button", { name: "Insert example" }).click();
    else if (tests) await setCode(page, editors.nth(1), tests);
  }
  await form.getByRole("button", { name: "Add assignment" }).click();
  await card(page, title).waitFor({ timeout: 10000 });
}

function localInput(daysFromNow, hh, mm) {
  // datetime-local string in Asia/Kolkata (the browser context's zone)
  const d = new Date(Date.now() + daysFromNow * 864e5 + 5.5 * 36e5);
  const ymd = d.toISOString().slice(0, 10);
  return `${ymd}T${hh}:${mm}`;
}

(async () => {
  const browser = await chromium.launch();
  const admin = await newPage(browser, "admin");
  const teacher = await newPage(browser, "teacher");
  const student = await newPage(browser, "student");
  const student2 = await newPage(browser, "student2");
  const ta = await newPage(browser, "ta");

  // ---------------- 1-5 accounts and roles
  await step("1 register teacher+student", async () => {
    await register(teacher, "Tara Teacher", "t@test.edu", "teacher");
    await register(student, "Sam Student", "s@test.edu", "student");
    rec("1 register teacher+student", "ok", "both registered and landed on Courses");
  });
  await step("2 admin makes TA", async () => {
    await register(ta, "Tia TA", "ta@test.edu", "student");
    await register(student2, "Sid Outsider", "s2@test.edu", "student");
    await login(admin, "admin@lab.edu", "adminpass123");
    await admin.getByRole("link", { name: "Users" }).click();
    await admin.getByLabel("Role for ta@test.edu").selectOption("ta");
    await admin.getByText("Tia TA is now ta").waitFor();
    await ta.reload();
    const navText = await ta.locator("header").innerText();
    rec("2 admin makes TA", navText.includes("ta") ? "ok" : "fail", `TA nav after reload: "${navText.replace(/\n/g, " ")}"`);
  });
  await step("3 admin resets password", async () => {
    admin.once("dialog", (d) => d.accept("newpass1234"));
    await admin.getByRole("row", { name: /s@test.edu/ }).getByRole("button", { name: "Reset password" }).click();
    await admin.getByText("Password reset for s@test.edu").waitFor();
    const oldStillWorks = (await student.evaluate(() => fetch("/api/auth/me").then((r) => r.status))) === 200;
    const p = await newPage(browser, "student-newpw");
    await login(p, "s@test.edu", "newpass1234");
    await p.getByRole("heading", { name: "Courses" }).waitFor({ timeout: 8000 });
    await p.context().close();
    rec("3 admin resets password", oldStillWorks ? "warn" : "ok",
      "new password works" + (oldStillWorks ? "; BUT the student's already-open session still works after the reset" : ""));
  });
  await step("5 admin cannot demote self", async () => {
    const dis = await admin.getByLabel("Role for admin@lab.edu").isDisabled();
    rec("5 admin cannot demote self", dis ? "ok" : "fail", `own role dropdown disabled=${dis}`);
  });
  await admin.screenshot({ path: path.join(OUT, "admin-users.png"), fullPage: true });

  // ---------------- 6-8 courses and TAs
  let courseUrl, course2Url;
  await step("6 course, enroll, outsider blocked", async () => {
    const f = teacher.locator("form.card");
    await f.getByPlaceholder("Code (e.g. AI101)").fill("AI101");
    await f.getByPlaceholder("Title").fill("Intro to AI");
    await f.getByPlaceholder("Description").fill("Search, logic, learning");
    await f.getByRole("button", { name: "Create course" }).click();
    await card(teacher, "Intro to AI").getByRole("link", { name: "Open" }).click();
    courseUrl = teacher.url();
    await student.goto(BASE + "/");
    await card(student, "Intro to AI").getByRole("button", { name: "Enroll" }).click();
    await card(student, "Intro to AI").getByRole("link", { name: "Open" }).waitFor();
    await student2.goto(courseUrl);
    await student2.waitForTimeout(800);
    const txt = await student2.locator("main").innerText();
    rec("6 course, enroll, outsider blocked", txt.includes("Enroll in this course to see it") ? "ok" : "fail",
      `outsider sees: "${txt.slice(0, 80)}"`);
  });
  await step("7 teacher adds TA; TA opens course", async () => {
    await teacher.getByPlaceholder("TA's email").fill("ta@test.edu");
    await teacher.getByRole("button", { name: "Add TA" }).click();
    await teacher.locator(".chip", { hasText: "Tia TA" }).waitFor();
    await ta.goto(courseUrl);
    await ta.getByPlaceholder("Assignment title").waitFor({ timeout: 8000 });
    rec("7 teacher adds TA; TA opens course", "ok", "TA sees the course with the new-assignment form (grading checked in step 10)");
  });
  await step("8 TA cannot manage 2nd course", async () => {
    await teacher.goto(BASE + "/");
    const f = teacher.locator("form.card");
    await f.getByPlaceholder("Code (e.g. AI101)").fill("RB201");
    await f.getByPlaceholder("Title").fill("Robotics");
    await f.getByRole("button", { name: "Create course" }).click();
    await card(teacher, "Robotics").getByRole("link", { name: "Open" }).click();
    course2Url = teacher.url();
    await ta.goto(BASE + "/");
    const hasOpen = await card(ta, "Robotics").getByRole("link", { name: "Open" }).count();
    await ta.goto(course2Url);
    await ta.waitForTimeout(800);
    const txt = await ta.locator("main").innerText();
    const ok = !hasOpen && txt.includes("Enroll in this course");
    rec("8 TA cannot manage 2nd course", ok ? "warn" : "fail",
      `no Open button=${!hasOpen}; direct URL shows "${txt.slice(0, 60)}" (blocked, but the message tells a TA to 'Enroll', which a TA can't do)`);
    await teacher.goto(courseUrl);
  });

  // ---------------- 9-12 file assignments
  await step("9 due 23:59 local", async () => {
    await createAssignment(teacher, { title: "Essay due tomorrow", due: localInput(1, "23", "59") });
    const h = await card(teacher, "Essay due tomorrow").locator("h3").innerText();
    const api = await teacher.evaluate(async (u) => {
      const id = u.split("/").pop();
      return (await (await fetch(`/api/courses/${id}/assignments`)).json()).find((a) => a.title === "Essay due tomorrow").due_at;
    }, courseUrl);
    rec("9 due 23:59 local", /11:59.*pm|23:59/i.test(h) ? "ok" : "fail", `heading "${h}"; stored ${api} (Asia/Kolkata browser)`);
  });
  await step("10 late + 20% penalty", async () => {
    await createAssignment(teacher, { title: "Late lab", due: localInput(-1, "10", "00"), penalty: 20 });
    await student.goto(courseUrl);
    const c = card(student, "Late lab");
    await c.locator('input[type="file"]').setInputFiles({ name: "lab.py", mimeType: "text/x-python", buffer: Buffer.from("print('lab')\n") });
    const btn = await c.getByRole("button", { name: /Submit/ }).innerText();
    await c.getByRole("button", { name: /Submit/ }).click();
    await c.locator(".badge-late").waitFor();
    await ta.goto(courseUrl);
    const tc = card(ta, "Late lab");
    await tc.getByLabel("Points").fill("50");
    await tc.getByPlaceholder("Feedback").fill("Good start");
    await tc.getByRole("button", { name: "Save" }).click();
    await tc.getByText("40 after late penalty").waitFor();
    await student.getByRole("link", { name: "My grades" }).click();
    const row = await student.getByRole("row", { name: /Late lab/ }).innerText();
    rec("10 late + 20% penalty", row.includes("40/100 (50 − 20% late)") ? "ok" : "fail",
      `button said "${btn}"; late badge shown; TA saw "40 after late penalty"; My grades row: "${row.replace(/\s+/g, " ")}"`);
    await student.screenshot({ path: path.join(OUT, "student-grades.png"), fullPage: true });
  });
  await step("11 closed when late not accepted", async () => {
    await createAssignment(teacher, { title: "Closed quiz", due: localInput(-1, "10", "00"), allowLate: false });
    await student.goto(courseUrl);
    const t = await card(student, "Closed quiz").innerText();
    rec("11 closed when late not accepted", t.includes("Submissions are closed") ? "ok" : "fail", t.replace(/\s+/g, " ").slice(0, 120));
  });
  await step("12 .exe and 25 MB rejected", async () => {
    const c = card(student, "Essay due tomorrow");
    await c.locator('input[type="file"]').setInputFiles({ name: "virus.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
    await c.getByRole("button", { name: /Submit/ }).click();
    await c.locator("p.muted").last().waitFor();
    const m1 = await c.locator("p.muted").last().innerText();
    await c.locator('input[type="file"]').setInputFiles({ name: "big.pdf", mimeType: "application/pdf", buffer: Buffer.alloc(25 * 1024 * 1024, 48) });
    await c.getByRole("button", { name: /Submit/ }).click();
    await student.waitForTimeout(3000);
    const m2 = await c.locator("p.muted").last().innerText();
    const ok = /not allowed/i.test(m1) && /(large|413|too)/i.test(m2) && !/Submitted/.test(m2);
    rec("12 .exe and 25 MB rejected", ok ? "ok" : "warn", `exe: "${m1}"; 25MB: "${m2}"`);
    const u = await student.evaluate(async () => {
      const fd = new FormData();
      fd.append("file", new File(["%PDF"], "उत्तर.pdf"));
      const csrf = document.cookie.match(/csrf_access_token=([^;]+)/)[1];
      const list = await (await fetch(location.pathname.replace("/courses/", "/api/courses/") + "/assignments")).json();
      const id = list.find((a) => a.title === "Essay due tomorrow").id;
      const r = await fetch(`/api/assignments/${id}/submissions`, { method: "POST", body: fd, headers: { "X-CSRF-TOKEN": csrf } });
      return r.status + " " + (await r.text()).slice(0, 120);
    });
    rec("12b unicode filename", u.startsWith("201") ? "ok" : "fail", `upload of "उत्तर.pdf": ${u}`);
  });

  // ---------------- 13-21 code assignments
  await step("13 code assignment created", async () => {
    await teacher.goto(courseUrl);
    await createAssignment(teacher, { title: "Add two numbers", kind: "code", points: 10,
      starter: "def add(a, b):\n    pass\n", tests: "example" });
    rec("13 code assignment created", "ok", "starter + example tests, 10 pts");
  });
  const codeCard = () => card(student, "Add two numbers");
  await step("14 run print", async () => {
    await student.goto(courseUrl);
    const ed = codeCard().locator(".editor");
    const starter = await ed.locator(".cm-content").innerText();
    await setCode(student, ed, 'print("hi")');
    const t0 = Date.now();
    await codeCard().getByRole("button", { name: "▶ Run" }).click();
    await codeCard().locator("pre.output").filter({ hasText: "hi" }).waitFor({ timeout: 90000 });
    rec("14 run print", "ok", `starter shown: ${JSON.stringify(starter)}; first run took ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  });
  await step("15 numpy in browser", async () => {
    await setCode(student, codeCard().locator(".editor"), "import numpy as np; print(np.arange(3))");
    await codeCard().getByRole("button", { name: "▶ Run" }).click();
    await codeCard().getByRole("button", { name: "▶ Run" }).waitFor({ timeout: 60000 });
    const out = await codeCard().locator("pre.output").innerText();
    rec("15 numpy in browser", out.includes("[0 1 2]") ? "ok" : "warn",
      `expected to fail here (jsDelivr blocked): "${out.replace(/\s+/g, " ").slice(0, 160)}"`);
  });
  await step("16 stop infinite loop", async () => {
    await setCode(student, codeCard().locator(".editor"), "while True: pass");
    await codeCard().getByRole("button", { name: "▶ Run" }).click();
    await student.waitForTimeout(1500);
    await codeCard().getByRole("button", { name: "■ Stop" }).click();
    await codeCard().getByRole("button", { name: "▶ Run" }).waitFor({ timeout: 3000 });
    const t0 = Date.now();
    await student.evaluate(() => 1 + 1);
    await setCode(student, codeCard().locator(".editor"), "print(6*7)");
    await codeCard().getByRole("button", { name: "▶ Run" }).click();
    await codeCard().locator("pre.output").filter({ hasText: "42" }).waitFor({ timeout: 60000 });
    rec("16 stop infinite loop", "ok", `Stop worked, page responsive (${Date.now() - t0}ms), next run works after reload of Python`);
  });
  await step("16c input()", async () => {
    await student.reload();
    await setCode(student, codeCard().locator(".editor"), "name = input('Name? ')\nprint('hello', name)");
    await codeCard().getByRole("button", { name: "▶ Run" }).click();
    await codeCard().getByRole("button", { name: "▶ Run" }).waitFor({ timeout: 60000 });
    const out = await codeCard().locator("pre.output").innerText().catch(() => "");
    rec("16c input()", "warn", `input() in the browser editor: "${out.replace(/\s+/g, " ").slice(0, 200)}"`);
  });
  await step("17 autograde wrong then right", async () => {
    await setCode(student, codeCard().locator(".editor"), "def add(a, b):\n    return a - b\n");
    await codeCard().getByRole("button", { name: "Submit code" }).click();
    const t0 = Date.now();
    await codeCard().locator(".auto.done, .auto.error").first().waitFor({ timeout: 60000 });
    const wrong = await codeCard().locator(".auto").first().innerText();
    const t1 = (Date.now() - t0) / 1000;
    await setCode(student, codeCard().locator(".editor"), "def add(a, b):\n    return a + b\n");
    await codeCard().getByRole("button", { name: "Submit code" }).click();
    await student.waitForTimeout(500);
    await codeCard().locator("tbody tr").first().locator(".auto.done, .auto.error").waitFor({ timeout: 60000 });
    const right = await codeCard().locator("tbody tr").first().locator(".auto").innerText();
    rec("17 autograde wrong then right", /0\/2/.test(wrong) && /2\/2.*10 pts/.test(right) ? "ok" : "fail",
      `wrong: "${wrong}" (${t1.toFixed(1)}s); right: "${right}"`);
  });
  await step("18 reload shows last code", async () => {
    await student.reload();
    const code = await codeCard().locator(".editor .cm-content").first().innerText();
    rec("18 reload shows last code", code.includes("return a + b") ? "ok" : "fail", JSON.stringify(code));
  });
  await step("19 teacher prefill/view/regrade", async () => {
    await teacher.goto(courseUrl);
    const c = card(teacher, "Add two numbers");
    const first = c.locator("tbody tr").first();
    const v = await first.getByLabel("Points").inputValue();
    await first.getByRole("button", { name: "view" }).click();
    const dlg = teacher.locator("dialog");
    await dlg.waitFor();
    const hasLog = await dlg.locator("pre.log").count();
    await teacher.screenshot({ path: path.join(OUT, "teacher-view-submission.png"), fullPage: true });
    await dlg.getByRole("button", { name: "Close" }).click();
    await c.getByRole("button", { name: "Regrade all" }).click();
    await c.getByText(/queued for regrading/).waitFor();
    const msg = await c.getByText(/queued for regrading/).innerText();
    await teacher.waitForTimeout(8000);
    await teacher.reload();
    const after = await card(teacher, "Add two numbers").locator(".auto").allInnerTexts();
    rec("19 teacher prefill/view/regrade", v === "10" && hasLog ? "ok" : "fail",
      `prefilled=${v}; log shown=${!!hasLog}; "${msg}"; after regrade: ${JSON.stringify(after)}`);
  });
  await step("20 no hidden tests for student", async () => {
    const leaks = [];
    student.on("response", async (r) => {
      if (!r.url().includes("/api/")) return;
      const t = await r.text().catch(() => "");
      if (/test_add|"log"|test_code/.test(t)) leaks.push(r.url());
    });
    await student.reload();
    await student.waitForTimeout(2000);
    const html = await student.content();
    rec("20 no hidden tests for student", leaks.length || /def test_add/.test(html) ? "fail" : "ok",
      leaks.length ? "leaked in " + leaks.join(", ") : "no test code or log in page or API responses");
  });
  await step("21 sandbox check", async () => {
    await setCode(student, codeCard().locator(".editor"),
      'import os, socket\ndef add(a, b):\n    open("/etc/x", "w")\n    socket.create_connection(("1.1.1.1", 53), timeout=3)\n    return a + b\n');
    await codeCard().getByRole("button", { name: "Submit code" }).click();
    await student.waitForTimeout(500);
    await codeCard().locator("tbody tr").first().locator(".auto.done, .auto.error").waitFor({ timeout: 60000 });
    const r = await codeCard().locator("tbody tr").first().locator(".auto").innerText();
    rec("21 sandbox check", /0\/2/.test(r) ? "ok" : "fail", `result: "${r}"; host /etc/x exists=${fs.existsSync("/etc/x")}`);
  });
  await step("21b forged score via browser", async () => {
    await setCode(student, codeCard().locator(".editor"),
      "import atexit\natexit.register(lambda: open('/tmp/junit.xml','w').write('<testsuite tests=\"2\" failures=\"-98\" errors=\"0\" skipped=\"0\"/>'))\ndef add(a, b):\n    return 0\n");
    await codeCard().getByRole("button", { name: "Submit code" }).click();
    await student.waitForTimeout(500);
    await codeCard().locator("tbody tr").first().locator(".auto.done, .auto.error").waitFor({ timeout: 60000 });
    const r = await codeCard().locator("tbody tr").first().locator(".auto").innerText();
    await student.screenshot({ path: path.join(OUT, "student-forged-score.png"), fullPage: true });
    await teacher.reload();
    const pre = await card(teacher, "Add two numbers").locator("tbody tr").first().getByLabel("Points").inputValue();
    rec("21b forged score via browser", /100\/2/.test(r) ? "fail" : "ok", `wrong code shows "${r}"; teacher's grade box pre-filled with ${pre}`);
  });

  // ---------------- 4 rate limit (last: it locks the shared bucket)
  await step("4 login rate limit", async () => {
    const p = await newPage(browser, "attacker");
    let last = "";
    for (let i = 0; i < 11; i++) {
      await login(p, "s@test.edu", "wrongpass" + i);
      await p.locator("p.error").waitFor();
      last = await p.locator("p.error").innerText();
    }
    const v = await newPage(browser, "victim");
    await login(v, "t@test.edu", "password123");
    await v.waitForTimeout(1500);
    const victimMsg = await v.locator("p.error").innerText().catch(() => "(logged in)");
    rec("4 login rate limit", /Too many attempts/.test(last) ? "warn" : "fail",
      `11th attempt: "${last}". A different user (teacher, correct password) right after: "${victimMsg}"`);
  });

  // ---------------- 22 phone width
  await step("22 phone width", async () => {
    const notes = [];
    for (const [who, src] of [["teacher", teacher], ["student", student], ["admin", admin]]) {
      const state = await src.context().storageState();
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
        isMobile: true, hasTouch: true, timezoneId: "Asia/Kolkata", storageState: state });
      const p = await ctx.newPage();
      p.on("pageerror", (e) => consoleErrors.push(`${who}-mobile pageerror: ${e.message}`));
      const pages = who === "admin" ? ["/admin", "/"] : who === "student" ? [courseUrl.replace(BASE, ""), "/grades", "/"] : [courseUrl.replace(BASE, "")];
      for (const u of pages) {
        await p.goto(BASE + u);
        await p.waitForTimeout(1500);
        const sw = await p.evaluate(() => document.documentElement.scrollWidth);
        const wide = await p.evaluate(() => [...document.querySelectorAll("table, .row, form, .cm-editor, header")]
          .filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1).map((e) => e.tagName.toLowerCase() + "." + e.className.split(" ")[0]).slice(0, 6));
        const name = `mobile-${who}${u.replace(/[/]/g, "_")}.png`;
        await p.screenshot({ path: path.join(OUT, name), fullPage: true });
        notes.push(`${who} ${u}: scrollWidth=${sw}${wide.length ? " overflow: " + wide.join(",") : ""}`);
      }
      await ctx.close();
    }
    rec("22 phone width", notes.some((n) => !/scrollWidth=390(?!\d)/.test(n)) ? "fail" : "ok", notes.join(" | "));
  });

  await step("16b print flood", async () => {
    const student = await newPage(browser, "student-flood");
    await login(student, "s@test.edu", "newpass1234");
    await student.getByRole("heading", { name: "Courses" }).waitFor();
    await student.goto(courseUrl);
    const codeCard = () => card(student, "Add two numbers");
    await setCode(student, codeCard().locator(".editor"), "i = 0\nwhile True:\n    i += 1\n    print(i)");
    await codeCard().getByRole("button", { name: "▶ Run" }).click();
    await student.waitForTimeout(4000);
    const t0 = Date.now();
    let responsive = true; let crashed = false; student.on("crash", () => { crashed = true; });
    try { await student.evaluate(() => 1, { timeout: 5000 }); } catch { responsive = false; }
    const lag = Date.now() - t0;
    const stopVisible = await codeCard().getByRole("button", { name: "■ Stop" }).isVisible().catch(() => false);
    if (stopVisible) await codeCard().getByRole("button", { name: "■ Stop" }).click({ timeout: 20000 }).catch(() => {});
    await student.waitForTimeout(500);
    const lines = await codeCard().locator("pre.output span").count().catch(() => -1);
    rec("16b print flood", crashed || lag > 1000 || !responsive ? "fail" : "warn",
      `crashed=${crashed}; print in an endless loop: main thread answered after ${lag}ms; ${lines} output lines kept in the DOM (no cap)`);
  });
  rec("console errors", consoleErrors.length ? "warn" : "ok", consoleErrors.slice(0, 15).join(" || ") || "none");
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify({ results, consoleErrors }, null, 2));
  await browser.close();
})();
