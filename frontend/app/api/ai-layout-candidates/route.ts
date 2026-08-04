import { readFile, writeFile } from "fs/promises";
import path from "path";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function candidatesPath() {
  const base = process.cwd().endsWith("frontend") ? path.resolve(process.cwd(), "..") : process.cwd();
  return path.join(base, "backend", "acceptance_data", "layout-pattern-discovery", "layout-pattern-candidates.json");
}

export async function GET() {
  try {
    return NextResponse.json(JSON.parse(await readFile(candidatesPath(), "utf8")));
  } catch {
    return NextResponse.json({ detail: "候选模式尚未生成" }, { status: 503 });
  }
}

export async function PATCH(request: NextRequest) {
  const body = await request.json();
  const filename = candidatesPath();
  const document = JSON.parse(await readFile(filename, "utf8"));
  const candidate = document.candidates?.find((item: { candidate_id: string }) => item.candidate_id === body.candidate_id);
  if (!candidate) return NextResponse.json({ detail: "候选模式不存在" }, { status: 404 });
  if (typeof body.name === "string" && body.name.trim()) candidate.pattern_name_suggestion = body.name.trim();
  if (body.action === "confirm") candidate.human_review_status = "confirmed_pending_evidence";
  else if (body.action === "reject") candidate.human_review_status = "rejected";
  else if (body.action !== "rename") return NextResponse.json({ detail: "非法操作" }, { status: 422 });
  candidate.formal_layout_pattern_created = false;
  candidate.review_note = "候选审核不等于正式LayoutPattern；证据门禁满足后方可发布。";
  await writeFile(filename, JSON.stringify(document, null, 2), "utf8");
  return NextResponse.json(candidate);
}
