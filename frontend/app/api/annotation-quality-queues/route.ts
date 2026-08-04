import { readFile } from "fs/promises";
import path from "path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const candidates = [
    path.resolve(process.cwd(), "../backend/acceptance_data/pairing-audit/annotation-quality-queues.json"),
    path.resolve(process.cwd(), "backend/acceptance_data/pairing-audit/annotation-quality-queues.json"),
  ];
  for (const filename of candidates) {
    try {
      return NextResponse.json(JSON.parse(await readFile(filename, "utf8")));
    } catch {
      // Try the next workspace layout.
    }
  }
  return NextResponse.json({ detail: "质量分组文件尚未生成" }, { status: 503 });
}
