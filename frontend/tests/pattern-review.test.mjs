import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../app/patterns/page.tsx", import.meta.url), "utf8");
const route = await readFile(new URL("../app/api/ai-layout-candidates/route.ts", import.meta.url), "utf8");

test("patterns defaults to core candidates and hides technical details", () => {
  assert.match(page, /candidates\.filter\(item => item\.is_core_pending\)/);
  assert.match(page, /<details[^>]*data-testid="technical-details"/);
  assert.doesNotMatch(page, /<details[^>]*open/);
});

test("candidate decisions archive without verified writes or deletion", () => {
  assert.match(route, /human_review_status = "merged"/);
  assert.match(route, /human_review_status = "rejected"/);
  assert.match(route, /formal_layout_pattern_created = false/);
  assert.match(route, /verified_write_count = 0/);
  assert.doesNotMatch(route, /unlink|rmSync|deleteFile/);
});

test("similar candidates are recommendations only", () => {
  assert.match(route, /system_recommendation: recommendation\.decision/);
  assert.match(route, /decision: "merge"/);
  assert.doesNotMatch(route, /human_review_status = recommendation\.decision/);
});
