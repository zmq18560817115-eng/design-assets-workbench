// 运行时反向代理：把 /api、/uploads 请求转发到后端。
// 关键：在「请求时」读取 BACKEND_URL 环境变量，而不是构建时——
// 这样 Next standalone 产物 / Docker 里改 BACKEND_URL 才会即时生效。
import { NextRequest, NextResponse } from "next/server";

function backendBase(): string {
  return process.env.BACKEND_URL || "http://127.0.0.1:8000";
}

// 需要剥离的逐跳(hop-by-hop)头，避免转发后出错
const STRIP_REQ = ["host", "connection"];
const STRIP_RESP = ["content-encoding", "content-length", "transfer-encoding", "connection"];

export async function proxyTo(
  req: NextRequest,
  prefix: string,
  path: string[]
): Promise<NextResponse> {
  const target = `${backendBase()}${prefix}/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  STRIP_REQ.forEach((h) => headers.delete(h));

  const method = req.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD"
      ? undefined
      : Buffer.from(await req.arrayBuffer());

  let resp: Response;
  try {
    resp = await fetch(target, { method, headers, body, redirect: "manual" });
  } catch (e) {
    return NextResponse.json(
      { detail: `后端不可达：${backendBase()}（请检查 BACKEND_URL 与后端服务）` },
      { status: 502 }
    );
  }

  const respHeaders = new Headers(resp.headers);
  STRIP_RESP.forEach((h) => respHeaders.delete(h));

  return new NextResponse(resp.body, {
    status: resp.status,
    statusText: resp.statusText,
    headers: respHeaders,
  });
}
