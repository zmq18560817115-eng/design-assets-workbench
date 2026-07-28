/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 便于容器化部署：产出自包含的 standalone 输出
  output: "standalone",
  // 注意：不用 next.config 的 rewrites 代理后端。
  // 因为 standalone 产物会在「构建时」固化 rewrites 的目标地址，导致运行时
  // 修改 BACKEND_URL 不生效。改用 app/api、app/uploads 下的运行时代理路由。
};

module.exports = nextConfig;
