# 前端镜像：Next.js standalone 多阶段构建
FROM node:20-slim AS builder

# 可选：构建时用国内 npm 镜像加速
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm config set registry ${NPM_REGISTRY} && npm ci

COPY . .
RUN npm run build

# 运行阶段：只保留自包含产物
FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
# BACKEND_URL 在运行时注入（见 docker-compose.yml）
CMD ["node", "server.js"]
