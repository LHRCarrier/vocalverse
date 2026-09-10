<script setup lang="ts">
/**
 * 图表卡壳 —— lieflat **四件套**（SKILL §2「卡片结构固定四件套」）：
 *   ① 结论式标题（h2，写判断不写图型名）
 *   ② 副标题（图例 + 时间范围 + **口径**，用 `·` 分隔）
 *   ③ 图
 *   ④ 来源行（全大写、加字距）
 *
 * 两条与 UI 卡有意不同的地方（docs/50 §12.1）：
 * 1. **卡底 = Mono 纸底 `#F0EFEB`，不是纯白**。SKILL §2/§3 的契约是
 *    「卡片无边框无阴影，靠留白分卡」，卡底 = 页面底；画在白卡上会把 Mono 的
 *    明度梯压扁（白底上 `#D8D7D1` 与 `#C6C5BF` 几乎分不开）。
 * 2. **圆角 24px**（Mono `SHAPE.cardRadius`），与 UI 控件卡的 16px 有意区分：
 *    图表卡是"插画卡"，这是 Mono 语法的一部分。
 *
 * 第 ⑤ 项是本仓库自加的：**来源行里必须带图型编号与 gallery 卡内标题**，
 * 让每张图都能回溯到 lieflat 模板（对应 SKILL §8 自检第 12 条）。
 */
import { ref } from 'vue'

import { useReveal } from './mono'

withDefaults(
  defineProps<{
    /** 结论式标题：写判断，不写"柱状图" */
    title: string
    /** 副标题：图例 + 时间范围 + 口径说明（读者不看代码只看这一行） */
    sub?: string
    /** 图型编号，如 `F2` */
    chartNo: string
    /** lieflat 卡内标题，如 `Thirty days of sign-ups` —— 回溯用 */
    templateTitle: string
    /** 数据来源（表名 / 接口） */
    source: string
    height?: number
    /** 通栏卡（跨满一整行） */
    wide?: boolean
  }>(),
  { sub: undefined, height: 240, wide: false },
)

const root = ref<HTMLElement | null>(null)
const { revealed } = useReveal(root)
</script>

<template>
  <section ref="root" class="cc" :class="{ 'cc--wide': wide }">
    <h3 class="cc-title">{{ title }}</h3>
    <p v-if="sub" class="cc-sub">{{ sub }}</p>

    <div class="cc-body" :style="{ height: `${height}px` }">
      <slot :revealed="revealed" />
    </div>

    <p class="cc-src">
      {{ chartNo }} · {{ templateTitle }} · {{ source }}
    </p>
  </section>
</template>

<style scoped>
/*
 * 颜色值直接写字面量 = Mono token（`mono-tokens.js` 正本，见 src/styles/tokens.ts 的 `mono`）。
 * 不用 v-bind()：这些是**静态常量**，v-bind 会为每个实例注入一个 CSS 变量，
 * 几十张图就是几十份重复声明，得不偿失。
 */
.cc {
  background: #f0efeb; /* mono.PAPER */
  border-radius: 24px; /* mono.SHAPE.cardRadius */
  padding: 20px 22px 14px;
  min-width: 0;
}
.cc--wide {
  grid-column: 1 / -1;
}
.cc-title {
  margin: 0;
  font-size: 16.5px; /* mono.FONT.title */
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #1c1c1a; /* mono.INK */
}
.cc-sub {
  margin: 3px 0 14px;
  font-size: 11.5px; /* mono.FONT.sub */
  /* mono.MUTED(#8f8e88) 在 PAPER 上只有 2.86:1 —— 副标题是**要读的**文字（口径就写在这里），
     故压深到 #6a6963（4.79:1）。MUTED 仍用于轴刻度等装饰性文字。 */
  color: #6a6963;
  line-height: 1.45;
}
.cc-body {
  position: relative;
  min-width: 0;
}
.cc-src {
  margin: 10px 0 0;
  font-size: 9.5px; /* mono.FONT.src */
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  /* 来源行是**装饰性归属信息**（不是数据），仍按 mono.FAINT；
     它低于 WCAG AA 是 Mono 语法本身的选择，已在 docs/50 §12.4「Mono 偏离清单」登记。 */
  color: #8f8e88; /* mono.MUTED（原 FAINT #c6c5bf 在纸底上仅 ~1.6:1，连"看得见"都做不到） */
}
</style>
