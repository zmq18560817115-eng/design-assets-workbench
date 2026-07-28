// 把 /api/* 运行时代理到后端 /api/*
import { NextRequest } from "next/server";
import { proxyTo } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Ctx = { params: { path: string[] } };

const h = (req: NextRequest, ctx: Ctx) => proxyTo(req, "/api", ctx.params.path);

export {
  h as GET,
  h as POST,
  h as PUT,
  h as PATCH,
  h as DELETE,
  h as OPTIONS,
  h as HEAD,
};
