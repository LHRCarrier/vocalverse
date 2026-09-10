<script setup lang="ts">
/**
 * 管理端控制台 · 联调桥接页（AGENTS 工作流程 §3 · docs/50 §14.3）。
 *
 * 依赖开关与开启方式：
 * - **本页自身无需任何开关**（dev-only，`import.meta.env.DEV` 下的 `/preview` 子树，
 *   生产构建 Rollup 整枝剔除，零体积零路由）；
 * - 它探测的两个上游需要后端就绪：
 *   · Java 控制台域 → `VOICEVERSE_CONSOLE_ENABLED=true`（默认 true）+ 已 bootstrap 出超级管理员；
 *   · Python 运维域 → `APP_OPS_TELEMETRY_ENABLED=true`（默认 true）；
 * - 本页**不 import `apps/admin` 的任何源码**（模块隔离要求，docs/50 §3.1）：
 *   只做三件事——探活、展示角色↔权限对照、列联调清单。
 *
 * 与其它 preview 页的关键差别：**没有 mock 兜底**。这类"桥接页"的价值恰恰在于
 * 报告真实连通性，给它加假数据就等于把唯一的用途抹掉。三种失败态必须分开显示：
 * ① Python 404 = 运维端点未挂载/开关关；② Java 401(46001) = 服务在但控制台未登录
 * （这其实是**正常**状态，说明路由通了）；③ 网络失败 = 代理/服务未起。
 */
import { onMounted, ref } from 'vue'

interface ProbeResult {
  label: string
  url: string
  status: 'ok' | 'unauthorized' | 'not-found' | 'down' | 'error'
  detail: string
  httpStatus: number | null
  code: number | null
}

const probes = ref<ProbeResult[]>([])
const loading = ref(true)

/** 三个内置角色与权限码（与 docs/50 §4.2 同源；只读展示，便于组员核对后端 RBAC seed） */
const ROLES = [
  {
    code: 'super',
    name: '超级管理员',
    tone: 'badge-info',
    scope: '全部权限码（含角色与权限编辑）',
    note: '由 bootstrap 引导创建；唯一可分配 super 的角色',
  },
  {
    code: 'ops',
    name: '运维',
    tone: 'badge-ok',
    scope: 'ops:overview/metric/alert:read|write、ops:trace:read、console:audit:read',
    note: '**不含** ops:trace:content:read —— 看性能不需要看用户对话内容',
  },
  {
    code: 'operator',
    name: '运营',
    tone: 'badge-warn',
    scope: 'content:*（歌曲/听力/书籍/场景/媒体/工单）、moderation:word 已删除、console:audit:read',
    note: '负责上架下架；题库降为只读',
  },
  {
    code: 'moderator',
    name: '审核',
    tone: 'badge-muted',
    scope: 'moderation:queue|decide、moderation:report:read|handle、content:{song,listening,book,media}:read、console:audit:read',
    note: '内容只读（含媒体，用于视频审核）；处置走决定接口',
  },
]

const CHECKLIST = [
  { step: '起依赖', cmd: 'docker compose up -d postgres redis', note: '控制台与 App 共用同一 DB/Redis' },
  { step: '起 Python', cmd: 'cd services/python; uv run uvicorn app.main:app --reload --port 8000', note: '运维指标 + LLM trace + 书籍/媒体' },
  { step: '起 Java', cmd: 'cd services/java; mvn spring-boot:run', note: '控制台身份/RBAC/审计/审核/内容' },
  { step: '起控制台', cmd: 'cd apps/admin; pnpm dev', note: 'http://localhost:5174（避开 App 的 5173）' },
  { step: '首次登录', cmd: '用 VOICEVERSE_CONSOLE_BOOTSTRAP_* 引导的超级管理员登录', note: '控制台账号与 App 账号互相独立' },
  { step: '验收·运维', cmd: '服务总览看到依赖探测 → 性能指标出图 → 产生一次 LLM 调用后 Trace 列表有条目', note: 'trace 为空时先确认 APP_LLM_TRACE_ENABLED' },
  { step: '验收·审核', cmd: '手工建单 → 决定 hide → 该帖在 App 的 feed/详情/评论/通知四处都不再出现', note: '**四处都要看**，只验 feed 会漏掉通知面的泄漏' },
  { step: '验收·运营', cmd: '歌曲下架 → 状态变 archived；缺 LRC 的歌曲上架 → 收到 46011 + 字段级原因', note: '下架对用户侧暂无效果（已知缺口 G-2）' },
  { step: '验收·权限', cmd: '用 ops 账号打开「系统 · 管理员」→ 应跳 403 并显示所需权限码', note: '前端裁剪 + 后端 46002 双层' },
]

async function probe(label: string, url: string, expectAuth: boolean): Promise<ProbeResult> {
  const base: ProbeResult = { label, url, status: 'error', detail: '', httpStatus: null, code: null }
  try {
    // 不带令牌：故意探"未登录"分支，这是最省事的连通性证明
    const res = await fetch(url, { headers: { Accept: 'application/json' } })
    base.httpStatus = res.status
    let body: { code?: number; message?: string } | null = null
    try {
      body = (await res.json()) as { code?: number; message?: string }
    } catch {
      body = null
    }
    base.code = body?.code ?? null
    if (res.ok && body?.code === 0) {
      base.status = 'ok'
      base.detail = '端点已挂载且当前会话可读'
    } else if (expectAuth && (res.status === 401 || body?.code === 46001)) {
      base.status = 'unauthorized'
      base.detail = `服务已就绪且路由已挂载（未登录属正常，code=${body?.code ?? res.status}）`
    } else if (res.status === 404) {
      base.status = 'not-found'
      base.detail = `404：路由未挂载或代理未生效（检查开关与 vite/nginx 前缀）`
    } else {
      base.status = 'error'
      base.detail = `${res.status} ${body?.message ?? '非 Envelope 响应'}`
    }
  } catch (err) {
    base.status = 'down'
    base.detail = `连不上：${(err as Error).message}（服务未启动或代理目标错误）`
  }
  return base
}

const STATUS_TEXT: Record<ProbeResult['status'], string> = {
  ok: '通',
  unauthorized: '通（需登录）',
  'not-found': '未挂载',
  down: '不可达',
  error: '异常',
}

onMounted(async () => {
  probes.value = await Promise.all([
    probe('Python 运维域 · 服务总览', '/api/v1/console/ops/overview', true),
    probe('Java 控制台域 · 当前身份', '/manage/api/v1/console/auth/me', true),
  ])
  loading.value = false
})
</script>

<template>
  <div class="acp">
    <header class="acp-head">
      <h1>管理端控制台 · 联调桥接</h1>
      <p>
        独立 SPA 在 <code>apps/admin</code>（端口 <strong>5174</strong>，入口
        <code>/console/</code>）。本页只做探活与对照，<strong>不含任何控制台源码</strong>——
        模块隔离是硬要求（docs/50 §3.1）。设计与拷问见 <code>docs/50</code> / <code>docs/51</code>。
      </p>
    </header>

    <section class="acp-card">
      <h2>① 上游连通性</h2>
      <p class="acp-sub">
        不带令牌探测（故意命中"未登录"分支）。<strong>「通（需登录）」是成功状态</strong>：
        说明服务在、路由挂载了、只是本页没有控制台会话。
      </p>
      <p v-if="loading" class="acp-muted">探测中…</p>
      <ul v-else class="acp-probes">
        <li v-for="p in probes" :key="p.url">
          <span class="badge" :class="`badge-${p.status}`">{{ STATUS_TEXT[p.status] }}</span>
          <span class="acp-probe-label">{{ p.label }}</span>
          <code class="acp-probe-url">{{ p.url }}</code>
          <span class="acp-probe-detail">{{ p.detail }}</span>
        </li>
      </ul>
    </section>

    <section class="acp-card">
      <h2>② 角色 ↔ 权限对照</h2>
      <p class="acp-sub">核对后端 RBAC seed 是否与本表一致；不一致以代码常量表为准并修文档。</p>
      <table class="acp-table">
        <thead>
          <tr>
            <th>角色</th>
            <th>code</th>
            <th>范围</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in ROLES" :key="r.code">
            <td><span class="badge" :class="r.tone">{{ r.name }}</span></td>
            <td><code>{{ r.code }}</code></td>
            <td class="acp-scope">{{ r.scope }}</td>
            <td class="acp-note">{{ r.note }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="acp-card">
      <h2>③ 联调清单（逐项打勾再合）</h2>
      <ol class="acp-checklist">
        <li v-for="(c, i) in CHECKLIST" :key="i">
          <span class="acp-step">{{ c.step }}</span>
          <code>{{ c.cmd }}</code>
          <span class="acp-note">{{ c.note }}</span>
        </li>
      </ol>
    </section>

    <section class="acp-card acp-warn">
      <h2>④ 三条容易漏的验收点</h2>
      <ul>
        <li>
          <strong>隐藏要在四处都验</strong>：feed / 详情 / 评论 / <strong>通知中心</strong>。
          只验 feed 会通过自测却仍然泄漏（docs/51 B-3：谓词是 18 处不是 8 处）。
        </li>
        <li>
          <strong>跨令牌双向拒绝</strong>：App 令牌进控制台要拒，<strong>控制台令牌进 App 也要拒</strong>。
          后者曾被漏掉（docs/51 C-4/C-5）。
        </li>
        <li>
          <strong>trace 内容默认不落库</strong>：<code>APP_LLM_TRACE_CONTENT_CAPTURE=false</code> 时
          <code>llm_span_contents</code> 必须零行；答辩域（<code>kind='defense'</code>）**即便开启也硬排除**。
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.acp {
  padding: 20px 24px 48px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 1100px;
}
.acp-head h1 {
  margin: 0 0 6px;
  font-size: 20px;
}
.acp-head p {
  margin: 0;
  font-size: 13px;
  color: var(--vv-text-secondary, #667085);
  line-height: 1.7;
}
.acp-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px 18px;
}
.acp-card h2 {
  margin: 0 0 4px;
  font-size: 15px;
}
.acp-sub {
  margin: 0 0 12px;
  font-size: 12.5px;
  color: #667085;
  line-height: 1.6;
}
.acp-muted {
  margin: 0;
  font-size: 13px;
  color: #667085;
}
.acp-probes {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.acp-probes li {
  display: grid;
  grid-template-columns: 108px 200px 1fr;
  gap: 8px;
  align-items: baseline;
}
.acp-probe-url {
  font-size: 11.5px;
  color: #344054;
}
.acp-probe-detail {
  font-size: 12px;
  color: #667085;
}
.acp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.acp-table th,
.acp-table td {
  text-align: left;
  padding: 7px 8px;
  border-bottom: 1px solid #f0f0f0;
  vertical-align: top;
}
.acp-table th {
  font-weight: 600;
  color: #344054;
}
.acp-scope {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11.5px;
  color: #344054;
}
.acp-note {
  font-size: 11.5px;
  color: #667085;
}
.acp-checklist {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12.5px;
}
.acp-checklist code {
  font-size: 11.5px;
  color: #344054;
  background: #f8f8f7;
  padding: 1px 5px;
  border-radius: 4px;
  margin: 0 6px;
}
.acp-step {
  font-weight: 600;
}
.acp-warn ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  line-height: 1.75;
  color: #475467;
}
.badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 500;
}
.badge-ok {
  background: #dcfce7;
  color: #14532d;
}
.badge-unauthorized {
  background: #e8edff;
  color: #1e40af;
}
.badge-not-found {
  background: #fff4d6;
  color: #7c2d12;
}
.badge-down,
.badge-error {
  background: #fee2e2;
  color: #991b1b;
}
.badge-info {
  background: #e8edff;
  color: #1e40af;
}
.badge-warn {
  background: #fff4d6;
  color: #7c2d12;
}
.badge-muted {
  background: #f0f0f0;
  color: #475467;
}
</style>

<!--
删除清单（AGENTS 工作流程 §3：可删无影响；删除后 apps/web 四连 + check-bundle 必须全绿）
删除本页时，逐项执行：
1) 删除文件：apps/web/src/views/preview/AdminConsolePreview.vue（本文件）
2) apps/web/src/views/preview/registry.ts：删掉 previewPages 数组中
   path 为 '/preview/admin-console' 的那一行（group: '管理端'）
3) apps/web/src/router/preview.ts：删掉 children 中
   { path: 'admin-console', component: () => import('@/views/preview/AdminConsolePreview.vue') } 这一项
删除后校验：
  cd apps/web
  pnpm lint && pnpm typecheck && pnpm test:run && pnpm build && node scripts/check-bundle.mjs
本页不 import apps/admin 任何源码、不写任何后端文件，因此无需其它清理。
契约快照零 diff（本页不新增/修改任何后端端点）。
-->
