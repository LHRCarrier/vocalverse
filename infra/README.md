# infra（部署与本地基础设施配置）

> 评审整改项（docs/09 P2-#11）：补齐被文档引用但缺失的目录。
> nginx 生产反代配置在 `apps/web/nginx.conf`（容器自带），DB seed 业务 schema 归 Alembic，故此处只放与本机/容器运行环境相关的配置。

## 目录

```
infra/
├── README.md        # 本文件
└── dev/
    └── .wslconfig    # WSL2 资源示例（Docker Desktop 默认内存 2GB 不够宿住 5 容器）
```

## dev/.wslconfig 使用

- 复制到 `C:\Users\<你>\.wslconfig`，然后 `wsl --shutdown` 重启 WSL2 与 Docker Desktop。
- 作用：Docker 内跑 PG+Redis+Python(torch)+Java 时默认 2GB 内存大概率 OOM；调至 8GB/4 核后 `scripts/dev.ps1` 一键起才会稳定。
