import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const allowedCategories = new Set(["恒温杯", "吸奶器", "羊脂膏"]);
const contentTypes: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".bmp": "image/bmp" };

function repositoryRoot() {
  return process.cwd().endsWith(`${path.sep}frontend`) ? path.resolve(process.cwd(), "..") : process.cwd();
}

export async function GET(request: NextRequest) {
  const relativePath = request.nextUrl.searchParams.get("path") ?? "";
  const normalized = relativePath.replace(/\\/g, "/");
  const parts = normalized.split("/");
  const category = parts[0] === "公司成品素材" ? parts[1] : parts[0];
  if (!allowedCategories.has(category) || normalized.includes("..") || /holdout|奶瓶/i.test(normalized)) return NextResponse.json({ detail: "图片路径不允许" }, { status: 403 });
  const root = repositoryRoot();
  const resolved = path.resolve(root, ...parts);
  if (!resolved.startsWith(`${root}${path.sep}`)) return NextResponse.json({ detail: "图片路径不允许" }, { status: 403 });
  try {
    const data = await fs.readFile(resolved);
    return new NextResponse(data, { headers: { "Content-Type": contentTypes[path.extname(resolved).toLowerCase()] ?? "application/octet-stream", "Cache-Control": "private, max-age=60" } });
  } catch {
    return NextResponse.json({ detail: "图片不存在" }, { status: 404 });
  }
}
