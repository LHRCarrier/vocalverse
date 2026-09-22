<script setup lang="ts">
/**
 * 设置与隐私（docs/53 P5 ④）：账户抽屉三子页各为真实页面（不再 toast「M3 上线后开放」）。
 * - help：帮助与反馈 —— FAQ + 真实工单提交（POST /api/v1/tickets）+ 我的反馈（GET /tickets/mine）；
 * - privacy：数据与隐私 —— 收集范围/用途/存储/权利说明；
 * - about：关于声语界 —— 版本与素材声明。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { createTicket, fetchMyTickets } from '@/api/tickets'
import type { TicketKind, TicketView } from '@/api/tickets'
import { useAuthStore } from '@/stores/auth'
import '@/styles/mobile-uic.css'

type Section = 'help' | 'privacy' | 'about'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const TITLES: Record<Section, string> = {
  help: '帮助与反馈',
  privacy: '数据与隐私',
  about: '关于声语界',
}

const section = computed<Section>(() => {
  const s = String(route.params.section ?? '')
  return (['help', 'privacy', 'about'] as const).includes(s as Section) ? (s as Section) : 'help'
})
const title = computed(() => TITLES[section.value])

const FAQ = [
  { q: '怎么开始第一次练习？', a: '到酒馆开一局剧本，或在自由对话里随便聊两句；系统会逐句给出评分。' },
  { q: '跟唱评分怎么算的？', a: '逐句给音准、节奏、发音三维分，整首取加权平均；参考旋律来自歌曲的曲谱对齐。' },
  { q: '生词本里的词从哪来？', a: '阅读、社区划词时点「加入生词本」即收；状态可在生词本里循环切换。' },
  { q: '数据会保存多久？', a: '练习记录与学习画像长期保存用于复习；可在此页提交反馈要求处理。' },
]

/* ---------- 帮助与反馈：真实工单 ---------- */
const KIND_OPTIONS: { key: TicketKind; label: string }[] = [
  { key: 'feedback', label: '功能建议' },
  { key: 'bug', label: '问题反馈' },
  { key: 'content_correction', label: '内容纠误' },
]
const KIND_LABELS: Record<string, string> = {
  feedback: '功能建议',
  bug: '问题反馈',
  content_correction: '内容纠误',
}
const STATUS_LABELS: Record<string, string> = {
  open: '待处理',
  processing: '处理中',
  resolved: '已解决',
  closed: '已关闭',
}

const kind = ref<TicketKind>('feedback')
const titleInput = ref('')
const content = ref('')
const submitting = ref(false)
const submitMsg = ref('')
const submitError = ref('')
const tickets = ref<TicketView[]>([])
const ticketsError = ref('')

async function loadTickets() {
  try {
    tickets.value = await fetchMyTickets()
    ticketsError.value = ''
  } catch (e) {
    ticketsError.value = (e as Error).message || '加载失败'
  }
}
onMounted(() => {
  if (section.value === 'help' && auth.token) void loadTickets()
})

async function submit() {
  const text = content.value.trim()
  if (!text || submitting.value) return
  submitting.value = true
  submitError.value = ''
  submitMsg.value = ''
  try {
    const created = await createTicket({
      kind: kind.value,
      content: text,
      title: titleInput.value.trim() || undefined,
    })
    tickets.value = [created, ...tickets.value]
    content.value = ''
    titleInput.value = ''
    submitMsg.value = '已提交，管理员会尽快处理'
  } catch (e) {
    submitError.value = (e as Error).message || '提交失败，请稍后再试'
  } finally {
    submitting.value = false
  }
}

function dateLabel(iso?: string | null) {
  return iso ? iso.slice(0, 10) : ''
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar :title="title" back @back="router.push('/m/home')" />

    <div class="u-set">
      <!-- 帮助与反馈 -->
      <template v-if="section === 'help'">
        <section class="u-set__card">
          <div class="u-set__sub">提交反馈</div>
          <div class="u-set__chips">
            <button
              v-for="opt in KIND_OPTIONS"
              :key="opt.key"
              class="u-chip"
              :class="kind === opt.key ? 'u-chip--accent' : 'u-chip--ink'"
              type="button"
              :aria-pressed="kind === opt.key"
              @click="kind = opt.key"
            >
              {{ opt.label }}
            </button>
          </div>
          <label class="u-set__field">
            <span class="u-set__label">标题（选填）</span>
            <input v-model="titleInput" class="u-set__input" type="text" maxlength="128" placeholder="一句话概括">
          </label>
          <label class="u-set__field">
            <span class="u-set__label">详细描述</span>
            <textarea
              v-model="content"
              class="u-set__textarea"
              maxlength="5000"
              placeholder="遇到什么问题？希望改进什么？"
            />
          </label>
          <p v-if="submitMsg" class="u-set__ok" role="status">{{ submitMsg }}</p>
          <p v-if="submitError" class="u-set__err" role="alert">{{ submitError }}</p>
          <button
            class="u-btn u-btn--primary u-btn--block"
            type="button"
            :disabled="!content.trim() || submitting"
            @click="submit"
          >
            {{ submitting ? '提交中…' : '提交' }}
          </button>
        </section>

        <section class="u-set__card">
          <div class="u-set__sub">我的反馈</div>
          <p v-if="ticketsError" class="u-set__err">{{ ticketsError }}</p>
          <ul v-else-if="tickets.length" class="u-set__list">
            <li v-for="t in tickets" :key="t.id" class="u-set__row">
              <span class="u-set__body">
                <span class="u-set__rowtitle">
                  [{{ KIND_LABELS[t.kind] ?? t.kind }}] {{ t.title || t.content.slice(0, 40) }}
                </span>
                <span class="u-set__meta">
                  {{ dateLabel(t.createdAt) }}
                  <template v-if="t.adminReply"> · 回复：{{ t.adminReply }}</template>
                </span>
              </span>
              <span class="u-set__status" :class="`is-${t.status}`">{{ STATUS_LABELS[t.status] ?? t.status }}</span>
            </li>
          </ul>
          <p v-else class="u-set__hint">还没有提交过反馈。</p>
        </section>

        <section class="u-set__card">
          <div class="u-set__sub">常见问题</div>
          <details v-for="f in FAQ" :key="f.q" class="u-set__faq">
            <summary>{{ f.q }}</summary>
            <p class="u-set__p">{{ f.a }}</p>
          </details>
        </section>
      </template>

      <!-- 数据与隐私 -->
      <template v-else-if="section === 'privacy'">
        <section class="u-set__card">
          <div class="u-set__sub">我们收集什么</div>
          <p class="u-set__p">练习录音与评分结果、阅读与查词记录、打卡与埋点事件（页面浏览、推荐曝光/点击等），用于生成学习画像与推荐。</p>
          <p class="u-set__p">不会收集与学习无关的个人信息；录音仅用于当次评分与薄弱项分析。</p>
        </section>
        <section class="u-set__card">
          <div class="u-set__sub">存储与安全</div>
          <p class="u-set__p">数据存储在本项目的演示环境内，接口按账号隔离（每个请求校验登录态）。</p>
          <p class="u-set__p">生词本、批注、练习记录都可在对应页面自行删除。</p>
        </section>
        <section class="u-set__card">
          <div class="u-set__sub">你的权利</div>
          <p class="u-set__p">可在「我的资料」修改昵称与头像；可在生词本删除收录的词；如需导出或彻底删除数据，请通过「帮助与反馈」提交工单。</p>
        </section>
      </template>

      <!-- 关于声语界 -->
      <template v-else>
        <section class="u-set__card">
          <div class="u-set__sub">关于声语界</div>
          <p class="u-set__p">VocalVerse 声语界 · v0.1.0（M3 演示版）</p>
          <p class="u-set__p">英文歌跟唱、酒馆跑团、自由对话与英文小说阅读，练习数据汇聚成你的学习画像。</p>
        </section>
        <section class="u-set__card">
          <div class="u-set__sub">素材与致谢</div>
          <p class="u-set__p">演示歌曲仅使用公有领域/自创曲；词典释义来自开源 ECDICT 子集；语音合成使用开源引擎。</p>
        </section>
        <section class="u-set__card">
          <div class="u-set__sub">联系</div>
          <button class="u-btn u-btn--secondary u-btn--block" type="button" @click="router.push('/m/settings/help')">
            去「帮助与反馈」提交工单
          </button>
        </section>
      </template>
    </div>
  </div>
</template>
