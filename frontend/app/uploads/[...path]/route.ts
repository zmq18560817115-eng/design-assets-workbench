// 把 /uploads/* 运行时代理到后端 /uploads/*（图片素材）
import { NextRequest } from "next/server";
import { proxyTo } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Ctx = { params: { path: string[] } };

const h = (req: NextRequest, ctx: Ctx) => proxyTo(req, "/uploads", ctx.params.path);

export { h as GET, h as HEAD };
