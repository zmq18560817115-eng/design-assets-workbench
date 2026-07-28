// build 后自动把静态资源拷进 standalone 产物，
// 使 `node .next/standalone/server.js` 能正确提供 CSS/JS 与 public 资源。
// （Next 的 standalone 输出默认不含 .next/static 与 public，需手动补齐。）
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const standalone = path.join(root, ".next", "standalone");

if (!fs.existsSync(standalone)) {
  // 未启用 standalone 输出时直接跳过
  process.exit(0);
}

function copyDir(src, dest) {
  if (!fs.existsSync(src)) return false;
  fs.cpSync(src, dest, { recursive: true });
  return true;
}

const staticOk = copyDir(
  path.join(root, ".next", "static"),
  path.join(standalone, ".next", "static")
);
const publicOk = copyDir(path.join(root, "public"), path.join(standalone, "public"));

console.log(
  `[postbuild] standalone 资源已补齐 → static:${staticOk ? "✓" : "skip"} public:${
    publicOk ? "✓" : "skip"
  }`
);
