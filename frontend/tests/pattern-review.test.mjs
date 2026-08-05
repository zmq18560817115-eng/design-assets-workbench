import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../app/patterns/page.tsx", import.meta.url), "utf8");
const route = await readFile(new URL("../app/api/ai-layout-candidates/route.ts", import.meta.url), "utf8");

test("patterns defaults to core candidates and hides technical details", () => {
  assert.match(page, /candidates\.filter\(item => item\.is_core_pending\)/);
  assert.match(page, /<details[^>]*data-testid="technical-details"/);
  assert.doesNotMatch(page, /data-testid="technical-details"[^>]*open/);
});

test("candidate state is split into decision, owner and formal status", () => {
  assert.match(page, /人工决定/);
  assert.match(page, /负责人确认/);
  assert.match(page, /正式模式/);
  assert.match(page, /candidate\.decision/);
  assert.match(page, /candidate\.owner_confirmed/);
  assert.match(page, /candidate\.formal_status/);
});

test("publication workflow exposes explicit Chinese actions and history", () => {
  for (const label of ["保留为独立模式", "合并到同品类模式", "拒绝该模式", "设计负责人确认", "创建并发布正式模式", "操作历史"]) {
    assert.match(page, new RegExp(label));
  }
  assert.match(page, /candidate\.missing_requirements\.length === 0/);
});

test("candidate route proxies persistence to the backend", () => {
  assert.match(route, /proxyTo/);
  assert.match(route, /layout-pattern-candidates/);
  assert.doesNotMatch(route, /writeFile|human_review_status/);
});
