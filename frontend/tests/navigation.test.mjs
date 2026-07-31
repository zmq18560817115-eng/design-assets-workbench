import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("legacy asset routes redirect to the unified asset center", async () => {
  const analyze = await source("../app/analyze/page.tsx");
  const batch = await source("../app/batch/page.tsx");
  const cases = await source("../app/cases/page.tsx");
  assert.match(analyze, /redirect\("\/assets\?tab=import"\)/);
  assert.match(batch, /redirect\("\/assets\?tab=import&mode=batch"\)/);
  assert.match(cases, /redirect\("\/assets\?tab=library"\)/);
});

test("designer navigation excludes administrator entries by default", async () => {
  const navigation = await source("../lib/navigation.ts");
  assert.match(navigation, /NEXT_PUBLIC_WORKBENCH_ROLE === "admin"/);
  const designerBlock = navigation.split("export const adminNavigation")[0];
  assert.doesNotMatch(designerBlock, /AI拆解校准|业务检索验收|Prompt与校验版本/);
});
