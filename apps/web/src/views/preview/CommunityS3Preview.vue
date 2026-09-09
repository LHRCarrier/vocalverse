<script setup lang="ts">
/**
 * 社区 S3 联调测试页（dev-only · docs/13 §8 预览工作流 · docs/47 §8）
 *
 * 用途：真实链路冒烟入口 —— Python 媒体服务连通性 + 上传实弹 + 跳转移动端详情/资料页。
 * 后端**无 test-only 开关**（媒体/社区接口即生产接口，例外登记 docs/13 §8），配好演示环境即可用：
 *   - 媒体服务：Python 8000（`GET /readyz` 可达即可；上传需登录 token）
 *   - 社区发帖：`VOICEVERSE_COMMUNITY_POST_ENABLED=true`（演示环境开启；生产默认 false）
 *   - 演示账号：demoadult / demo123456
 *
 * 验收后删除（可删无影响，删除清单）：
 *   1) 本文件 `apps/web/src/views/preview/CommunityS3Preview.vue`；
 *   2) `apps/web/src/views/preview/registry.ts` 中 `/preview/community-s3` 那一行；
 *   3) `apps/web/src/router/preview.ts` 中 `community-s3` 路由那一行。
 * 删除后：`pnpm lint && pnpm typecheck && pnpm test:run && pnpm build` 全绿（生产构建本就整枝剔除 preview 子树）。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { fetchMyMedia, precheck, uploadMedia } from '@/api/media'
import { pingJava } from '@/api/client'
import { readyz } from '@/api/client'

import type { MediaAssetView } from '@/api/media'

const router = useRouter()
const pythonStatus = ref('检测中…')
const javaStatus = ref('检测中…')
const uploadStatus = ref('')
const uploaded = ref<MediaAssetView[]>([])
const mine = ref<MediaAssetView[]>([])
const busy = ref(false)

async function checkBackends() {
  pythonStatus.value = '检测中…'
  try {
    const r = await readyz()
    pythonStatus.value = `Python 8000 可达 ✓（env=${r.data.app_env}）`
  } catch {
    pythonStatus.value = 'Python 未达 ✗（先启动 8000；见 scripts/dev-up.ps1）'
  }
  try {
    await pingJava()
    javaStatus.value = 'Java 8080 可达 ✓'
  } catch {
    javaStatus.value = 'Java 未达 ✗（社区接口需要 8080）'
  }
}

/** 上传一张本地图片走真实媒体管道（前端预校验 → XHR → MediaView） */
async function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const bad = precheck(file, 'image')
  if (bad) {
    uploadStatus.value = `预校验拒绝：${bad}`
    return
  }
  busy.value = true
  uploadStatus.value = '上传中…'
  try {
    const view = await uploadMedia(file, 'image', {
      onProgress: (r) => (uploadStatus.value = `上传中… ${Math.round(r * 100)}%`),
    })
    uploaded.value = [view, ...uploaded.value]
    uploadStatus.value = `上传成功：${view.url}（${view.mimeType} / ${view.size}B）`
  } catch (err) {
    uploadStatus.value = `上传失败：${err instanceof Error ? err.message : String(err)}`
  } finally {
    busy.value = false
  }
}

async function loadMine() {
  mine.value = await fetchMyMedia(10)
  if (!mine.value.length) uploadStatus.value = '我的上传为空（或未登录）'
}

void checkBackends()
</script>

<template>
  <section class="preview-community">
    <h1>社区内容 S3 · 媒体闭环联调台</h1>
    <p class="muted">
      覆盖：媒体上传（图/视频/头像）· 帖子详情（<code>/m/post/:id</code>）· 真实头像 ·
      我的资料（<code>/m/me/profile</code>）· 正文划词查义（复用读书域词卡）。
    </p>

    <ul class="checklist">
      <li>媒体服务：Python <code>POST/GET/DELETE /api/v1/media</code>（需登录 token；读允许匿名）</li>
      <li>社区发帖：<code>VOICEVERSE_COMMUNITY_POST_ENABLED=true</code>（生产默认关闭）</li>
      <li>演示账号：demoadult / demo123456</li>
      <li>存储：<code>APP_MEDIA_DIR</code>（默认 <code>./data/media</code>）；容器需挂 <code>./data/media</code> 卷</li>
      <li>视频上限 64MB 需同时放开 <code>apps/web/nginx.conf</code> 的 <code>client_max_body_size</code></li>
    </ul>

    <p :class="{ ok: pythonStatus.includes('✓') }">{{ pythonStatus }}</p>
    <p :class="{ ok: javaStatus.includes('✓') }">{{ javaStatus }}</p>

    <div class="row">
      <label class="btn">
        选一张图片上传
        <input class="file" type="file" accept="image/*" :disabled="busy" @change="onFile">
      </label>
      <button class="btn ghost" type="button" @click="loadMine">拉我的上传</button>
      <button class="btn ghost" type="button" @click="checkBackends">重新检测</button>
    </div>

    <p v-if="uploadStatus" class="status">{{ uploadStatus }}</p>

    <ul v-if="uploaded.length" class="thumbs">
      <li v-for="m in uploaded" :key="m.id">
        <img :src="m.url" :alt="m.mimeType">
        <code>{{ m.id.slice(0, 8) }}</code>
      </li>
    </ul>

    <p v-if="mine.length" class="muted">我的上传（最近 {{ mine.length }} 条）：{{ mine.map((m) => m.id.slice(0, 6)).join(', ') }}</p>

    <div class="row">
      <button class="btn" type="button" @click="router.push('/m/home')">进入社区（/m/home）</button>
      <button class="btn ghost" type="button" @click="router.push('/m/compose')">去发帖（/m/compose）</button>
      <button class="btn ghost" type="button" @click="router.push('/m/me/profile')">我的资料（/m/me/profile）</button>
    </div>
  </section>
</template>

<style scoped>
.preview-community {
  max-width: 640px;
  margin: 40px auto;
  padding: 0 20px 60px;
}

.muted {
  color: #6f6f6a;
  font-size: 13px;
  line-height: 1.7;
}

.checklist {
  margin: 16px 0;
  padding-left: 18px;
  color: #3a3a36;
  font-size: 13px;
  line-height: 1.9;
}

.ok {
  color: #16a34a;
  font-weight: 600;
}

.status {
  margin: 12px 0;
  font-weight: 600;
}

.row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border: none;
  border-radius: 999px;
  background: #1c1c1a;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn.ghost {
  background: transparent;
  border: 1.5px solid #d8d5cf;
  color: #1c1c1a;
}

.file {
  display: none;
}

.thumbs {
  display: flex;
  gap: 10px;
  padding: 0;
  list-style: none;
}

.thumbs img {
  width: 96px;
  height: 96px;
  object-fit: cover;
  border-radius: 12px;
}
</style>
