import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const pendingStatuses = new Set(["candidate_match", "ambiguous"]);
const allowedDecisions = new Set([
  "confirmed", "rejected", "duplicate_excluded", "missing_original", "missing_annotation", "",
]);

function auditDirectory() {
  const candidates = [
    path.resolve(process.cwd(), "backend/acceptance_data/pairing-audit"),
    path.resolve(process.cwd(), "../backend/acceptance_data/pairing-audit"),
  ];
  return candidates;
}

async function csvPath() {
  for (const directory of auditDirectory()) {
    const candidate = path.join(directory, "pairing-review.csv");
    try { await fs.access(candidate); return candidate; } catch { /* try next */ }
  }
  throw new Error("pairing-review.csv 不存在");
}

function parseCsv(content: string): { headers: string[]; rows: Record<string, string>[] } {
  const lines: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < content.length; index += 1) {
    const char = content[index];
    if (quoted) {
      if (char === '"' && content[index + 1] === '"') { field += '"'; index += 1; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ",") { row.push(field); field = ""; }
    else if (char === "\n") { row.push(field.replace(/\r$/, "")); lines.push(row); row = []; field = ""; }
    else field += char;
  }
  if (field || row.length) { row.push(field.replace(/\r$/, "")); lines.push(row); }
  const headers = (lines.shift() ?? []).map((value) => value.replace(/^\uFEFF/, ""));
  return { headers, rows: lines.filter((line) => line.some(Boolean)).map((values) => Object.fromEntries(headers.map((header, i) => [header, values[i] ?? ""]))) };
}

function csvCell(value: string) {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function serializeCsv(headers: string[], rows: Record<string, string>[]) {
  return `\uFEFF${headers.map(csvCell).join(",")}\r\n${rows.map((item) => headers.map((header) => csvCell(item[header] ?? "")).join(",")).join("\r\n")}\r\n`;
}

function imageUrl(relativePath: string) {
  return relativePath ? `/api/pairing-review/image?path=${encodeURIComponent(relativePath)}` : "";
}

function reviewKey(item: Record<string, string>) {
  return `${item["品类"]}:${item["彩框图相对路径"]}`;
}

async function loadReviewState(file: string): Promise<Record<string, Record<string, string>>> {
  try { return JSON.parse(await fs.readFile(path.join(path.dirname(file), "pairing-review-state.json"), "utf8")); }
  catch { return {}; }
}

async function saveReviewState(file: string, state: Record<string, Record<string, string>>) {
  await fs.writeFile(path.join(path.dirname(file), "pairing-review-state.json"), JSON.stringify(state, null, 2), "utf8");
}

function originalCandidates(item: Record<string, string>, allRows: Record<string, string>[] = []) {
  const paths = new Set<string>();
  if (item["原图相对路径"]) paths.add(item["原图相对路径"]);
  for (const match of item["问题说明"].matchAll(/公司成品素材\/[\s\S]*?\.(?:png|jpe?g|webp|bmp)/gi)) paths.add(match[0]);
  if (item["配对状态"] === "ambiguous" && paths.size < 2) {
    const size = item["图片尺寸"].match(/原图(\d+x\d+)/)?.[1];
    for (const row of allRows) {
      if (row["品类"] !== item["品类"] || !row["原图相对路径"] || row["原图相对路径"] === item["原图相对路径"]) continue;
      if (size && !row["图片尺寸"].includes(size)) continue;
      paths.add(row["原图相对路径"]);
      if (paths.size >= 3) break;
    }
  }
  return [...paths].map((relativePath) => ({ relativePath, imageUrl: imageUrl(relativePath), filename: path.posix.basename(relativePath) }));
}

function present(item: Record<string, string>, sourceIndex: number, allRows: Record<string, string>[] = []) {
  return {
    id: `${item["品类"]}:${item["彩框图相对路径"]}`,
    sourceIndex,
    category: item["品类"],
    originalPath: item["原图相对路径"],
    annotationPath: item["彩框图相对路径"],
    originalImageUrl: imageUrl(item["原图相对路径"]),
    annotationImageUrl: imageUrl(item["彩框图相对路径"]),
    originalFilename: path.posix.basename(item["原图相对路径"] || "缺少原图"),
    annotationFilename: path.posix.basename(item["彩框图相对路径"] || "缺少彩框图"),
    pairingStatus: item["配对状态"],
    basis: item["配对依据"],
    similarity: item["相似度"],
    problem: item["问题说明"],
    humanDecision: item["人工确认结果"],
    reviewer: item["审核人"],
    reviewNotes: item["审核备注"],
    selectedOriginal: item["人工选择原图"] ?? "",
    candidates: originalCandidates(item, allRows),
  };
}

export async function GET() {
  try {
    const file = await csvPath();
    const { rows } = parseCsv(await fs.readFile(file, "utf8"));
    const state = await loadReviewState(file);
    for (const item of rows) Object.assign(item, state[reviewKey(item)] ?? {});
    const items = rows.map((item, sourceIndex) => ({ item, sourceIndex })).filter(({ item }) => pendingStatuses.has(item["配对状态"])).map(({ item, sourceIndex }) => present(item, sourceIndex, rows));
    return NextResponse.json({
      items,
      total: items.length,
      completed: items.filter((item) => Boolean(item.humanDecision && item.reviewer && item.reviewNotes)).length,
      counts: {
        candidate_match: items.filter((item) => item.pairingStatus === "candidate_match").length,
        ambiguous: items.filter((item) => item.pairingStatus === "ambiguous").length,
      },
      storage: "local_csv",
      writesDatabase: false,
      writesVerified: false,
    }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ detail: error instanceof Error ? error.message : "读取失败" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as { id?: string; decision?: string; reviewer?: string; selectedOriginal?: string; reset?: boolean };
    const decision = body.reset ? "" : (body.decision ?? "");
    if (!body.id || !allowedDecisions.has(decision)) return NextResponse.json({ detail: "请求参数无效" }, { status: 400 });
    if (!body.reset && !(body.reviewer ?? "").trim()) return NextResponse.json({ detail: "请先填写审核人" }, { status: 400 });
    const file = await csvPath();
    const parsed = parseCsv(await fs.readFile(file, "utf8"));
    if (!parsed.headers.includes("人工选择原图")) parsed.headers.push("人工选择原图");
    const index = parsed.rows.findIndex((item) => reviewKey(item) === body.id);
    if (index < 0 || !pendingStatuses.has(parsed.rows[index]["配对状态"])) return NextResponse.json({ detail: "待审核记录不存在" }, { status: 404 });
    const item = parsed.rows[index];
    const candidates = new Set(originalCandidates(item, parsed.rows).map((candidate) => candidate.relativePath));
    const selectedOriginal = body.reset ? "" : (body.selectedOriginal || item["原图相对路径"] || "");
    if (decision === "confirmed" && (!selectedOriginal || !item["彩框图相对路径"])) return NextResponse.json({ detail: "确认配对必须同时存在原图和彩框图" }, { status: 400 });
    if (decision === "confirmed" && item["配对状态"] === "ambiguous" && !body.selectedOriginal) return NextResponse.json({ detail: "请人工选择一个候选原图" }, { status: 400 });
    if (selectedOriginal && !candidates.has(selectedOriginal)) return NextResponse.json({ detail: "所选原图不属于当前候选" }, { status: 400 });
    const notes: Record<string, string> = {
      confirmed: `人工确认配对正确；选择原图：${selectedOriginal}`,
      rejected: "人工确认配对错误，排除本组候选",
      duplicate_excluded: "人工确认属于重复图片，排除后续审核队列",
      missing_original: "人工确认缺少公司成品原图",
      missing_annotation: "人工确认缺少彩框标注图",
      "": "",
    };
    item["人工确认结果"] = decision;
    item["审核人"] = body.reset ? "" : (body.reviewer ?? "").trim();
    item["审核备注"] = notes[decision];
    item["人工选择原图"] = decision === "confirmed" ? selectedOriginal : "";
    const temporary = `${file}.tmp`;
    const output = serializeCsv(parsed.headers, parsed.rows);
    let storage = "local_csv";
    await fs.writeFile(temporary, output, "utf8");
    try {
      await fs.rename(temporary, file);
    } catch (error) {
      // Windows can deny replacement renames while Explorer/indexers hold a
      // read handle. Direct overwrite is safe here because the temp write has
      // already validated serialization and this is a local ignored CSV.
      const code = error instanceof Error && "code" in error ? String((error as NodeJS.ErrnoException).code) : "";
      if (code !== "EPERM" && code !== "EEXIST" && code !== "EBUSY") throw error;
      try {
        await fs.writeFile(file, output, "utf8");
      } catch (writeError) {
        const writeCode = writeError instanceof Error && "code" in writeError ? String((writeError as NodeJS.ErrnoException).code) : "";
        if (writeCode !== "EPERM" && writeCode !== "EBUSY") throw writeError;
        const state = await loadReviewState(file);
        state[body.id] = {
          "人工确认结果": item["人工确认结果"], "审核人": item["审核人"],
          "审核备注": item["审核备注"], "人工选择原图": item["人工选择原图"],
        };
        await saveReviewState(file, state);
        storage = "local_review_state";
      }
      await fs.unlink(temporary).catch(() => undefined);
    }
    if (storage === "local_csv") {
      const state = await loadReviewState(file);
      delete state[body.id];
      await saveReviewState(file, state);
    }
    return NextResponse.json({ ok: true, item: present(item, index, parsed.rows), storage, writesDatabase: false, writesVerified: false });
  } catch (error) {
    return NextResponse.json({ detail: error instanceof Error ? error.message : "保存失败" }, { status: 500 });
  }
}
