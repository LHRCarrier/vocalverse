/**
 * 控制台 DTO 与契约常量（docs/50 §10）—— **barrel**，按域拆到 `./dto/*`。
 *
 * 拆分的唯一原因是 `max-lines`（350）：原单文件 436 行。**按域拆而不是按大小切**，
 * 因为域边界正好是"改内容上下架不会碰到 trace 类型"的边界（与后端 `console/**` 的分包一致）。
 *
 * ⚠️ 隔离说明：这里**不复用** `apps/web/src/api/generated/*`（那是 App 的契约生成物），
 * 控制台用自己的手写 DTO。理由见 docs/50 §3.1——两端契约独立演进，
 * 共享生成物会让控制台被 App 的契约变更绑住。
 *
 * 引入方无需关心拆分：`@/api` 与 `@/api/types` 的导入路径**保持不变**。
 */
export * from './dto/common'
export * from './dto/identity'
export * from './dto/moderation'
export * from './dto/content'
export * from './dto/ops'
