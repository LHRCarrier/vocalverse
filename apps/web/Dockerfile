# 前端构建 → nginx 静态托管（docker compose web 服务）
FROM node:22-alpine AS build
WORKDIR /build
COPY package.json pnpm-lock.yaml* ./
RUN npm i -g pnpm@9 && pnpm install --frozen-lockfile || pnpm install
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY --from=build /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
