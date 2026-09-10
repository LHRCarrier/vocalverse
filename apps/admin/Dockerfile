# 管理端控制台镜像（docs/50 §13.1）。
#
# 多阶段：node 构建产物 → nginx 静态托管 + 反代两个上游。
# 与 apps/web/Dockerfile 同构（先 pnpm install，再 build，再拷 dist），
# 差别只在 base 路径与自己的 nginx server 块。
FROM node:22-slim AS build

WORKDIR /app
# 只复制清单，最大化利用层缓存（源码变动不触发重新 install）
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM nginx:1.27-alpine

# 控制台用独立的 server 块，用户端 nginx.conf 零改动
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/console/ >/dev/null 2>&1 || exit 1
