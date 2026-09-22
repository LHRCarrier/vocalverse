<script setup lang="ts">
/**
 * 社区规范与使用条例（用户侧呈现 · 入口：账户抽屉「社区规范与使用条例」→ /m/guidelines）。
 *
 * ⚠️ **文本与 `docs/59-社区规范与使用条例.md` 同步**（改一处必须改另一处）。
 * ⚠️ **条款号 R1~R9 是审核判据的对外锚点**（`JevHttpClient.CLAUSE_RULES` 与
 *    `ModerationService.REASON_CODES` 按此映射，`JevQuestionContractTest` 把守一致性）：
 *    只增不改——修改既有条款的编号等于修改历史判据。
 */
import { useRouter } from 'vue-router'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'

const router = useRouter()

interface Clause {
  code: string
  title: string
  text: string
}

/** 内容准则 R1~R9（与 docs/59 §二 逐条对应） */
const CLAUSES: Clause[] = [
  { code: 'R1', title: '垃圾信息', text: '无意义的重复刷屏、灌水、纯符号/乱码、恶意 @ 他人。' },
  { code: 'R2', title: '辱骂骚扰', text: '辱骂、人身攻击、地域/性别/种族歧视、跟踪式骚扰、死亡威胁。' },
  { code: 'R3', title: '色情低俗', text: '色情内容、露骨性暗示、擦边引流、未成年人性化表达。' },
  { code: 'R4', title: '暴力血腥', text: '宣扬暴力、血腥画面、自残自伤、恐怖主义与极端组织。' },
  { code: 'R5', title: '涉政敏感', text: '煽动对立与仇恨、传播政治谣言、涉及国家主权与安全的敏感表述。' },
  { code: 'R6', title: '广告引流', text: '未经许可的广告、站外引流、拉群推销、刷单返利、博彩与赌博信息。' },
  { code: 'R7', title: '版权侵权', text: '盗版资源、未授权转载全文、冒用他人作品（学习用途的合理引用请注明出处）。' },
  { code: 'R8', title: '虚假信息', text: '谣言、伪科学、诈骗信息、伪造经历或成绩误导他人。' },
  {
    code: 'R9',
    title: '其他违规',
    text: '不属于以上类别但破坏社区秩序的内容（例如泄露他人隐私、冒充官方账号）。',
  },
]

/** 使用条例（与 docs/59 §三 逐条对应） */
const TERMS: { key: string; title: string; text: string }[] = [
  {
    key: '3.1',
    title: '账号与身份',
    text: '账号仅供本人使用，不得出租、出售或共享；不得冒充他人或官方账号。账号安全由你负责，异常请及时改密并通过工单告知。',
  },
  {
    key: '3.2',
    title: '内容与版权',
    text: '你对发布的内容负责并保留权利；发布即授权平台在社区范围内展示与分发。引用他人内容请注明出处，禁止整篇搬运。',
  },
  {
    key: '3.3',
    title: 'AI 与语音数据',
    text: '口语对话、跟唱评分、发音评测会调用 AI 能力。录音仅用于当次评分与薄弱项分析；语音与文本的存储、使用范围见「设置与隐私 → 数据与隐私」。',
  },
  {
    key: '3.4',
    title: '隐私与安全',
    text: '不要发布他人的姓名、联系方式、住址、照片等个人信息；不要索要他人的隐私信息。发现泄露请举报。',
  },
  {
    key: '3.5',
    title: '未成年人保护',
    text: '未成年用户请在监护人指导下使用；平台对未成年人相关内容从严处理（涉及 R3/R4 一律顶格处置）。',
  },
  {
    key: '3.6',
    title: '商业推广',
    text: '商业内容需事先取得平台书面同意；学习打卡、经验分享中的个人联系方式与引流话术按 R6 处理。',
  },
]
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="社区规范与使用条例" back @back="router.push('/m/home')" />

    <div class="u-set">
      <p class="u-set__hint">生效日期 2026-09-22 · 适用范围：声语界全部用户与内容</p>

      <section class="u-set__card">
        <div class="u-set__sub">一、总则</div>
        <p class="u-set__p">
          声语界是一个英语学习社区：练口语、读英文、唱英文歌、跑团聊天。请把这里当作一间自习室——热闹，但不打扰别人。
        </p>
        <p class="u-set__p">
          发布内容或与他人互动，即视为已阅读并同意本规范与条例；不同意请停止使用社区功能。违规内容会被处理并留下处置记录，处置理由按固定条款号下发。
        </p>
      </section>

      <section class="u-set__card">
        <div class="u-set__sub">二、内容准则（违反任一条会被送审处理）</div>
        <div v-for="c in CLAUSES" :key="c.code" class="u-gl__clause">
          <span class="u-gl__code">{{ c.code }}</span>
          <div class="u-gl__body">
            <strong class="u-gl__title">{{ c.title }}</strong>
            <p class="u-gl__text">{{ c.text }}</p>
          </div>
        </div>
      </section>

      <section class="u-set__card">
        <div class="u-set__sub">三、使用条例</div>
        <div v-for="t in TERMS" :key="t.key" class="u-gl__term">
          <strong class="u-gl__title">{{ t.key }} {{ t.title }}</strong>
          <p class="u-gl__text">{{ t.text }}</p>
        </div>
      </section>

      <section class="u-set__card">
        <div class="u-set__sub">四、违规处理与申诉</div>
        <p class="u-set__p">
          处理方式（按情节轻重）：提醒（不公开）→ 隐藏内容（对所有人不可见，可恢复）→ 删除（软删除，留档可追溯）→ 升级人工复核（涉法涉险内容）。
        </p>
        <p class="u-set__p">
          平台使用「AI 辅助筛选 + 人工复核」：AI 只负责把疑似违规内容送进人工审核队列，最终处置由审核员决定；审核员看到的是条款号与内容快照，不是你的完整数据。
        </p>
        <p class="u-set__p">
          对处置有异议，请通过「设置与隐私 → 帮助与反馈」提交工单，注明内容与时间，我们会在 3 个工作日内复核。
        </p>
      </section>

      <section class="u-set__card">
        <div class="u-set__sub">五、生效与更新</div>
        <p class="u-set__p">
          本版自生效日期起施行；重大修订会在 App 内公告并顺延生效。
        </p>
        <p class="u-set__p">
          条款号（R1~R9）用于机器审核与人工复核的对账，不会随文案润色而变更；新增类别使用新编号。
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.u-gl__clause,
.u-gl__term {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.u-gl__term {
  display: block;
}
.u-gl__code {
  flex: 0 0 auto;
  height: 20px;
  padding: 0 6px;
  border-radius: var(--u-r-chip);
  /* 与 .u-chip--accent 同色（既有实值；token 层没有 accent-soft，不自造） */
  background: #e8edff;
  color: var(--u-accent);
  font-size: 12px;
  line-height: 20px;
  font-weight: 700;
}
.u-gl__body {
  min-width: 0;
}
.u-gl__title {
  font-size: 14px;
  color: var(--u-ink);
}
.u-gl__text {
  margin: 2px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--u-sub);
}
</style>
