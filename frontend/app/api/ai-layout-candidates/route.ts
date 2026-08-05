import { NextRequest, NextResponse } from "next/server";
import { proxyTo } from "@/lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return proxyTo(request, "/api", ["layout-pattern-candidates"]);
}

export async function PATCH(request: NextRequest) {
  const body = await request.clone().json();
  if (!String(body.candidate_id ?? "").trim()) {
    return NextResponse.json({ detail: "候选模式ID不能为空" }, { status: 422 });
  }
  return proxyTo(request, "/api", ["layout-pattern-candidates", body.candidate_id]);
}
