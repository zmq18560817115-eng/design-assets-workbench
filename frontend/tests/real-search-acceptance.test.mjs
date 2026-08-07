import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../app/layout-search/acceptance/real-search-acceptance-v1/page.tsx", import.meta.url), "utf8");

test("page uses plain-language four-step review", () => {
  for (const label of ["真实需求推荐验收", "第一步：看需求", "第二步：看系统推荐", "第四步：统一确认", "适合作为参考", "不适合作为参考", "暂时无法判断"]) assert.match(page, new RegExp(label));
  assert.match(page, /查看技术信息/);
  assert.match(page, /查看原始Brief/);
  assert.match(page, /清空本机草稿/);
});

test("draft stays local and uncertain suggestions are not bulk applied", () => {
  assert.match(page, /localStorage\.setItem/);
  assert.match(page, /assist\.choice !== "uncertain"/);
  assert.doesNotMatch(page, /addRealSearchAcceptanceFeedback/);
});

test("formal submit is gated and no-result uses a clear empty state", () => {
  assert.match(page, /allComplete \?/);
  assert.match(page, /window\.confirm/);
  assert.match(page, /submitRealSearchAcceptance/);
  assert.match(page, /暂无符合该品类需求的案例和排版模式/);
  assert.match(page, /确认目前没有合适结果/);
});
