# VocalVerse Java 管理端（Spring Boot）

> 薄管理端：用户管理 / 场景、歌曲、LRC 库 CRUD / 工单 / JWT 签发。
> **不进语音/SSE/LLM 热路径**（docs/06 第 1 章）；schema 由 Python 侧 Alembic 统一管理（`ddl-auto=none`）。

## 本地开发

```powershell
# 前置：JDK 21 (Temurin) + Maven 3.9
cd services/java
mvn -N wrapper:wrapper          # 生成 mvnw（一次性；此后用 ./mvnw）
mvn spring-boot:run             # 或 ./mvnw spring-boot:run
# 健康检查：http://localhost:8080/actuator/health
# OpenAPI：  http://localhost:8080/swagger-ui.html
```

## 测试

```powershell
mvn -B -ntp verify              # spotless:check + 单测（H2 内存库，无需 Docker）
```

## 契约约定

- 统一响应 envelope `{code, message, data}`（成功 `code=0`）；错误码表 `docs/api/error-codes.md`
- 鉴权：access JWT 15min + refresh 7d（httpOnly cookie）；JWT 由本服务签发、Python 共享 secret 验签
- 测试用 H2（MODE=PostgreSQL）；集成测试用 Testcontainers 打 `@Tag("integration")`（CI 默认跳过）
