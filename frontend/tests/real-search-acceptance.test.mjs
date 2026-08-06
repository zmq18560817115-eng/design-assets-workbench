import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL(
  "../app/layout-search/acceptance/real-search-acceptance-v1/page.tsx",
  import.meta.url,
), "utf8");

test("real acceptance page exposes only human judgment actions", () => {
  for (const label of ["合适", "不合适", "不确定", "当前没有合适结果", "审核人（必填）"]) {
    assert.match(page, new RegExp(label));
  }
  assert.doesNotMatch(page, /runLayoutSearchEvaluation|ground-truth|executeHoldout/i);
});

test("real acceptance page states that holdout remains sealed", () => {
  assert.match(page, /只展示7条 Calibration/);
  assert.match(page, /3条 Holdout 保持封存/);
  assert.match(page, /暂无合适公司模式；系统未跨品类强行推荐/);
});
