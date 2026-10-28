import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
const dir = await mkdtemp(join(tmpdir(), "checkins-test-"));
const server = spawn(
  "python3",
  [
    "serve.py",
    "--no-browser",
    "--port",
    "18765",
    "--data-file",
    join(dir, "pdca.json"),
  ],
  { cwd: join(import.meta.dirname, "../.."), stdio: "ignore" },
);
let browser;
try {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch("http://127.0.0.1:18765/")).ok) break;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  browser = await chromium.launch({
    executablePath: process.env.CHROME || "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage();
  await page.goto("http://127.0.0.1:18765/checkins/");
  await page.locator("#add:not([disabled])").waitFor();
  async function add(name, type) {
    await page.locator("#add").click();
    await page.locator("#name").fill(name);
    await page.locator("#type").selectOption(type);
    await page.locator("#add-form button[type=submit]").click();
    await page.getByRole("heading", { name, exact: true }).waitFor();
  }
  await add("喝水", "count");
  await page
    .locator(".card")
    .filter({ hasText: "喝水" })
    .locator("[data-action=check]")
    .click();
  await page.getByText("已保存", { exact: false }).waitFor();
  assert.match(await page.locator("#today-count").innerText(), /1 次/);
  await add("阅读", "timer");
  await page
    .locator(".card")
    .filter({ hasText: "阅读" })
    .locator("[data-action=check]")
    .click();
  await page.getByText("● 计时中").waitFor();
  await page.reload();
  await page.getByText("● 计时中").waitFor();
  await page
    .locator(".card")
    .filter({ hasText: "阅读" })
    .locator("[data-action=check]")
    .click();
  await page.getByText("1 条记录").first().waitFor();
  await page
    .locator(".card")
    .filter({ hasText: "阅读" })
    .locator("[data-action=history]")
    .click();
  assert.match(await page.locator("#history-summary").innerText(), /共 1 条/);
  assert.equal(await page.locator("#time-chart svg").count(), 1);
  console.log("Browser check-in, timer recovery, history and charts passed.");
} finally {
  await browser?.close();
  server.kill();
  await rm(dir, { recursive: true, force: true });
}
