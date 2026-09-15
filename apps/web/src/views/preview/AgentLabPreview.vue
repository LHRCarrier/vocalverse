<script setup lang="ts">
/**
 * Agent Lab · LLM 框架测试台（团队测试用，docs/26 §8）
 *
 * 能力：① 单轮/连跑真 LLM 回合（ContextBuilder→流式→META 补偿→MetaExecutor）
 *       ② 查看 system/user 原文（验证「system 全静态」契约）
 *       ③ 学习者画像只读查看
 * 依赖：后端 `/api/v1/agent-lab/*`（test-only，默认关闭；开启 = APP_AGENT_LAB_ENABLED=true）。
 * 删除无影响：本文件 + registry.ts 一行 + router/preview.ts 一行（dev-only，生产零体积）。
 */
import { ref } from 'vue'
import { NAlert, NButton, NCard, NCheckbox, NCode, NForm, NInput, NSelect, NTabPane, NTabs, NTag } from 'naive-ui'

const PYTHON = import.meta.env.VITE_PYTHON_BASE ?? ''

// ---------- 表单 ----------
const scenarioPresets = [
  { label: 'Maya · 咖啡馆（默认）', value: 'You are Maya, a friendly and patient barista at a cozy small cafe. You love chatting with customers and gently helping them practice English. Smile and be encouraging, but stay in character.' },
  { label: 'Jack · 机场', value: 'You are Jack, a brisk but friendly airport check-in agent. You guide the traveler through formalities and keep replies short and clear.' },
]
const corpusDefault = "I'd like a coffee, please.|请给我来杯咖啡\nCould I have a cappuccino?|来杯卡布奇诺\nHow much is it?|多少钱\nCan I drink it here?|可以在这喝吗\nThanks, that's all.|谢谢，就这些"
const form = ref({
  scenario_prompt: scenarioPresets[0].value,
  corpus_text: corpusDefault,
  difficulty: 2,
  user_text: 'hi, I would like a coffee please',
  action: 'normal',
  learner_profile: '',
  concluded_by_turn: false,
})
const history = ref<string[]>([])
const running = ref(false)

// ---------- 结果 ----------
const last = ref<{ system: string; user: string; result: Record<string, unknown> } | null>(null)
const runStats = ref<{ turns: number; meta_ok: number; meta_rate: number; compensated: number; concluded: boolean; tokens?: { prompt: number; completion: number } } | null>(null)
const runTable = ref<Array<Record<string, unknown>>>([])
const learner = ref<{ enabled: boolean; rendered: string; weak_phrases: string[]; weak_words: string[]; est_level: string | null } | null>(null)
const errorMsg = ref('')

const learnerExample = "Learner profile (internal): weak phrases: Could I have a cappuccino?; frequent word errors: cappuccino. Gently address these, do not overcorrect."

async function post(path: string, body: unknown) {
  const resp = await fetch(`${PYTHON}/api/v1/agent-lab${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const json = await resp.json()
  if (!resp.ok || json.code !== 0) throw new Error(json.message ?? `HTTP ${resp.status}`)
  return json.data
}

async function runTurn() {
  running.value = true
  errorMsg.value = ''
  try {
    const data = await post('/turn', { ...form.value, history: history.value })
    last.value = data
  } catch (e) {
    errorMsg.value = String(e)
  } finally {
    running.value = false
  }
}

async function runTurns(turns: string[]) {
  running.value = true
  errorMsg.value = ''
  try {
    const data = await post('/turns', { ...form.value, turns, history: history.value })
    runTable.value = data.results
    runStats.value = data.stats
  } catch (e) {
    errorMsg.value = String(e)
  } finally {
    running.value = false
  }
}

async function runFiveTurns() {
  await runTurns([
    'hi, I would like a coffee please',
    "I'd like a coffee, please. And what type do you have?",
    'How much is it? Can I have a cappuccino?',
    'Can I drink it here?',
    "ok thanks that's all, bye",
  ])
}

async function fetchLearner() {
  errorMsg.value = ''
  try {
    const resp = await fetch(`${PYTHON}/api/v1/agent-lab/learner?user_id=1`)
    const json = await resp.json()
    if (!resp.ok || json.code !== 0) throw new Error(json.message ?? `HTTP ${resp.status}`)
    learner.value = json.data
  } catch (e) {
    errorMsg.value = String(e)
  }
}

function tagType(v: unknown) {
  return v === true ? 'success' : v === false ? 'error' : 'default'
}
</script>

<template>
  <div class="mx-auto max-w-5xl p-6">
    <header class="mb-4">
      <h1 class="text-xl font-bold">Agent Lab · LLM 框架测试台</h1>
      <p class="text-sm text-[#667085]">
        团队测试用（真 DeepSeek Key）；后端 test-only 路由默认关闭 —— 开启需
        <code>APP_AGENT_LAB_ENABLED=true</code>。删除 = 删除本页 + 注册行 + 路由文件，零副作用。
      </p>
    </header>

    <NAlert v-if="errorMsg" type="error" class="mb-4" :show-icon="true">{{ errorMsg }}</NAlert>

    <NTabs type="line" class="mb-4">
      <NTabPane name="turn" tab="回合实验">
        <NAlert type="info" class="mb-4" :show-icon="true" title="怎么用 / 测什么 / 指标口径">
          <ol class="list-decimal pl-4 text-sm leading-6">
            <li><b>怎么用</b>：① 本页走真实 DeepSeek（Key 见后端 .env）；② 点「运行单轮」看单回合，点「连跑 5 轮冒烟」看会话级统计；③ <b>验证 system 契约</b>——每次运行的 system 应逐字相同（POC 铁证：动态进 system 会让 META 遵守率从 100% 跌到 0%）。</li>
            <li><b>测什么</b>：META 契约（流式直出/补偿后）、MetaExecutor（命中/收尾）、学习者画像注入、滚动摘要注入（连跑第 7 条消息后可在 user 原文看到 "Rolling summary" 行）、用量记账（tokens）。</li>
            <li>
              <b>指标口径与阈值</b>：<br>
              · META 直出率 = 流式自带可解析 META 的轮次/总轮次 —— 观察值 ~60%（全上下文），<b>不设硬门槛</b>（补偿是兜底）；
              · 补偿后 META 率 = (直出 + 补偿成功)/总轮次 —— <b>目标 100%</b>（低于 80% → 检查补偿 prompt/两调用回退预案）；
              · 补偿率 = 补偿轮次/总轮次 —— <b>&lt; 50% 良好</b>（过高说明主契约在退步）；
              · coach_note 有效 = MetaBlock.coach_note 非空占比 —— 目标 100%；
              · 覆盖度命中 = hits 非空的轮次（规则通道，与 META 无关，2/5 起步即正常）；
              · conclude 正确 = 第 5 轮（冒烟脚本末轮）为 true（连跑冒烟<b>末轮自动</b>注入「回合上限已到」，无需勾选；单轮勾选「收尾标记」= 模拟最后一轮）；
              · 往返耗时 ms（回合总时长，均值参考 ~1-2s/轮）；
              · tokens：prompt/completion 累计（同时验证 usage_log 落库——后端 usage_log 表应逐轮新增行）。
            </li>
          </ol>
        </NAlert>
        <NCard class="mb-4">
          <h2 class="mb-2 font-bold">参数</h2>
          <NForm label-placement="left" label-width="130">
            <NFormItem label="场景人设">
              <NSelect
                v-model:value="form.scenario_prompt"
                :options="scenarioPresets"
                :consistent-menu-width="false"
              />
            </NFormItem>
            <NFormItem label="语料（供粘贴）">
              <NInput v-model:value="form.corpus_text" type="textarea" :rows="4" placeholder="phrase|释义 每行一条" />
            </NFormItem>
            <NFormItem label="难度">
              <NSelect v-model:value="form.difficulty" :options="[1,2,3,4].map(v => ({ label: `L${v}`, value: v }))" style="width: 140px" />
            </NFormItem>
            <NFormItem label="用户转写">
              <NInput v-model:value="form.user_text" placeholder="用户说的内容（ASR 文本）" />
            </NFormItem>
            <NFormItem label="action">
              <NSelect v-model:value="form.action" :options="['normal','retry','hint','demo'].map(v => ({ label: v, value: v }))" style="width: 140px" />
            </NFormItem>
            <NFormItem label="画像行">
              <NInput v-model:value="form.learner_profile" type="textarea" :rows="2" :placeholder="`留空=不注入；示例：${learnerExample}`" />
            </NFormItem>
            <NFormItem label="收尾标记">
              <NCheckbox v-model:checked="form.concluded_by_turn">
                concluded_by_turn = True（模拟最后一轮；连跑时全轮生效，冒烟末轮则自动为 True）
              </NCheckbox>
            </NFormItem>
          </NForm>
          <div class="flex gap-2">
            <NButton type="primary" :loading="running" @click="runTurn">运行单轮</NButton>
            <NButton :loading="running" @click="runFiveTurns">连跑 5 轮冒烟</NButton>
            <NButton quaternary @click="fetchLearner">查看学习者画像</NButton>
          </div>
        </NCard>

        <template v-if="last">
          <NCard class="mb-4" title="system（应逐字稳定）" size="small">
            <NCode :code="last.system" language="plaintext" word-wrap />
          </NCard>
          <NCard class="mb-4" title="user（动态在 [context] 段）" size="small">
            <NCode :code="last.user" language="plaintext" word-wrap />
          </NCard>
          <NCard title="本回合结果" size="small">
            <div class="flex flex-wrap gap-2">
              <NTag :type="tagType(last.result.meta_ok)" size="small">META {{ last.result.meta_ok ? 'OK' : 'MISS' }}</NTag>
              <NTag v-if="last.result.compensated" type="warning" size="small">补偿调用</NTag>
              <NTag v-if="last.result.leaked" type="error" size="small">泄漏截断</NTag>
              <NTag size="small">{{ last.result.ms }}ms</NTag>
            </div>
            <p class="mt-2"><b>reply：</b>{{ last.result.reply }}</p>
            <p class="mt-1"><b>coach_note：</b>{{ last.result.coach_note ?? '（无）' }}</p>
            <p class="mt-1"><b>grammar：</b>{{ JSON.stringify(last.result.grammar) }}</p>
            <p class="mt-1"><b>hits：</b>{{ JSON.stringify(last.result.corpus_hits) }}</p>
            <p class="mt-1"><b>difficulty_delta / conclude：</b>{{ last.result.difficulty_delta }} / {{ last.result.conclude }}</p>
            <!-- ③ 语义子分（2026-09-04；LLM 判定、不进总分） -->
            <p class="mt-1"><b>content / vocab：</b>{{ JSON.stringify(last.result.content) }} / {{ JSON.stringify(last.result.vocab) }}</p>
          </NCard>
        </template>

        <template v-if="runStats">
          <NCard class="mt-4" title="连跑统计" size="small">
            <div class="flex flex-wrap gap-3">
              <NTag size="small" type="info">轮次 {{ runStats.turns }}</NTag>
              <NTag size="small" :type="runStats.meta_rate >= 80 ? 'success' : 'error'">补偿后 META {{ runStats.meta_rate }}%</NTag>
              <NTag size="small" type="warning">补偿 {{ runStats.compensated }}</NTag>
              <NTag size="small" :type="runStats.concluded ? 'success' : 'default'">收尾 {{ runStats.concluded }}</NTag>
              <NTag v-if="runStats.tokens" size="small" type="info">
                tokens {{ runStats.tokens.prompt }}p / {{ runStats.tokens.completion }}c
              </NTag>
            </div>
          </NCard>
          <NCard class="mt-4" title="逐轮结果" size="small">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-[#667085]">
                  <th class="py-1">#</th><th class="py-1">META</th><th class="py-1">补偿</th>
                  <th class="py-1">回复</th><th class="py-1">hits</th><th class="py-1">conclude</th><th class="py-1">ms</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in runTable" :key="String(r.turn)" class="border-t border-[#eee]">
                  <td class="py-1">{{ r.turn }}</td>
                  <td class="py-1"><NTag :type="r.meta_ok ? 'success' : 'error'" size="small">{{ r.meta_ok ? 'OK' : 'MISS' }}</NTag></td>
                  <td class="py-1">{{ r.compensated ? '✔' : '—' }}</td>
                  <td class="py-1 max-w-xs truncate">{{ r.reply }}</td>
                  <td class="py-1 max-w-xs truncate">{{ JSON.stringify(r.corpus_hits) }}</td>
                  <td class="py-1">{{ r.conclude }}</td>
                  <td class="py-1">{{ r.ms }}</td>
                </tr>
              </tbody>
            </table>
          </NCard>
        </template>
      </NTabPane>

      <NTabPane name="learner" tab="学习者画像">
        <NCard>
          <NButton quaternary class="mb-2" @click="fetchLearner">刷新</NButton>
          <template v-if="learner">
            <p class="mb-1">
              <NTag :type="learner.enabled ? 'success' : 'error'" size="small">
                learner_injection_enabled = {{ learner.enabled }}
              </NTag>
            </p>
            <NCode :code="learner.rendered || '（空画像：渲染为 空 行，不注入）'" language="plaintext" word-wrap />
            <p class="mt-2 text-sm"><b>weak_phrases：</b>{{ JSON.stringify(learner.weak_phrases) }}</p>
            <p class="text-sm"><b>weak_words：</b>{{ JSON.stringify(learner.weak_words) }}</p>
            <p class="text-sm"><b>est_level：</b>{{ learner.est_level ?? '（confidence 未达门槛）' }}</p>
          </template>
          <p v-else class="text-[#667085]">尚未加载（user_id=1；测试库为空时展示空画像属正常）</p>
        </NCard>
      </NTabPane>
    </NTabs>
  </div>
</template>
