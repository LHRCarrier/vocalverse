<script setup lang="ts">
/**
 * 社区 S1 联调测试页（dev-only · docs/13 §8 预览工作流 · docs/40 P3-7）
 *
 * 用途：真实链路冒烟入口——Java 连通性自检 + 跳转移动端社区页（feed/发帖/评论/互动/打卡卡）。
 * 后端无 test-only 开关（社区接口即生产接口，例外登记 docs/13 §8），配好演示环境即可用：
 *   - VOICEVERSE_COMMUNITY_POST_ENABLED=true（演示环境开启发帖；生产默认 false）
 *   - 演示账号 demoadult / demoteen / demosenior（密码 demo123456）
 *   - 社区演示种子由 Java CommunitySeeder 提供（虚构作者 8 帖 + 历史打卡卡）
 * 验收后删除：本文件 + registry.ts 一行 + router/preview.ts 一行。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { pingJava } from '@/api/client'

const router = useRouter()
const javaStatus = ref('检测中…')
const javaOk = ref(false)

async function checkJava() {
  javaStatus.value = '检测中…'
  try {
    await pingJava()
    javaOk.value = true
    javaStatus.value = 'Java 8080 可达 ✓（/manage/api/v1/ping）'
  } catch {
    javaOk.value = false
    javaStatus.value = 'Java 未达 ✗（先启动 8080 服务；方式 B 需先起 DB 容器）'
  }
}

void checkJava()
</script>

<template>
  <section class="preview-community">
    <h1>社区内容 S1 · 真实流联调台</h1>
    <p class="muted">数据源 = Java <code>/manage/api/v1/community/*</code>；feed 领域 Tab 服务端过滤（为你推荐=全量混排含打卡卡）。</p>

    <ul class="checklist">
      <li>
        开启发帖：<code>VOICEVERSE_COMMUNITY_POST_ENABLED=true</code>（application.yml 环境变量；生产默认关闭）
      </li>
      <li>种子：Java CommunitySeeder（7 位虚构作者 + 8 条原创内容帖 + 2 条历史打卡卡）</li>
      <li>打卡卡：练习会话收尾 → Python 内部 REST /internal/checkin → 每日一卡（整体分 + 次数）</li>
      <li>演示账号：demoadult / demoteen / demosenior（demo123456）</li>
    </ul>

    <p :class="{ ok: javaOk }">{{ javaStatus }}</p>

    <button class="btn" type="button" @click="router.push('/m/home')">进入移动端社区页（/m/home）</button>
    <button class="btn ghost" type="button" @click="checkJava">重新检测 Java</button>
  </section>
</template>

<style scoped>
.preview-community {
  max-width: 560px;
  margin: 40px auto;
  padding: 24px;
  font-family: system-ui, sans-serif;
}

.checklist {
  padding-left: 18px;
  font-size: 14px;
  line-height: 1.9;
}

.muted {
  color: #666;
}

.ok {
  color: #0a7d38;
  font-weight: 600;
}

.btn {
  margin: 8px 10px 0 0;
  padding: 10px 18px;
  border: 1px solid #222;
  border-radius: 999px;
  background: #222;
  color: #fff;
  font-size: 14px;
}

.btn.ghost {
  background: #fff;
  color: #222;
}
</style>
