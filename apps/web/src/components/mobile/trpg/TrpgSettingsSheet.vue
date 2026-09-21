<script setup lang="ts">
/**
 * 酒馆设置（底部抽屉；docs/52 §12.2）：
 * - 语言：中文 / English —— 只切换 **DM 输出语言**（界面文案仍是中文）；
 * - 语音：DM 回复自动朗读开关（关 = 服务端不再逐句 TTS，省配额）；
 * - 音色：**预留展示**（当前音色少，暂不开放选择）。
 * 偏好服务端持久化（跨设备）；保存失败由父级提示并回滚。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'

import type { TrpgPrefs } from '@/api/trpg'

const props = withDefaults(
  defineProps<{
    open: boolean
    prefs: TrpgPrefs
    saving?: boolean
  }>(),
  { saving: false },
)

const emit = defineEmits<{
  close: []
  update: [patch: Partial<TrpgPrefs>]
}>()

function setLang(lang: 'zh' | 'en') {
  if (lang !== props.prefs.lang) emit('update', { lang })
}

function toggleVoice() {
  emit('update', { voice_enabled: !props.prefs.voice_enabled })
}
</script>

<template>
  <div v-if="props.open" class="t-sheet">
    <div class="t-sheet__backdrop" role="presentation" @click="emit('close')" />
    <section class="t-sheet__panel t-sheet__panel--short" role="dialog" aria-label="酒馆设置">
      <header class="t-sheet__head">
        <div>
          <div class="t-sheet__title">酒馆设置</div>
          <div class="t-sheet__sub">偏好会保存到账号，换设备同样生效</div>
        </div>
        <button
          class="t-sheet__close"
          type="button"
          title="关闭"
          aria-label="关闭"
          @click="emit('close')"
        >
          <MobileIcon name="x" :size="18" />
        </button>
      </header>

      <div class="t-sheet__body">
        <div class="t-set">
          <div class="t-set__label">
            语言
            <span class="t-set__hint">DM 叙述与 NPC 台词的语言（界面文案不随之切换）</span>
          </div>
          <div class="t-set__seg" role="radiogroup" aria-label="DM 输出语言">
            <button
              type="button"
              role="radio"
              :aria-checked="prefs.lang === 'zh'"
              :class="{ 'is-on': prefs.lang === 'zh' }"
              @click="setLang('zh')"
            >
              中文
            </button>
            <button
              type="button"
              role="radio"
              :aria-checked="prefs.lang === 'en'"
              :class="{ 'is-on': prefs.lang === 'en' }"
              @click="setLang('en')"
            >
              English
            </button>
          </div>
        </div>

        <div class="t-set">
          <div class="t-set__label">
            语音朗读
            <span class="t-set__hint">DM 回复自动逐句朗读；关掉可省 TTS 配额</span>
          </div>
          <button
            class="t-switch"
            type="button"
            role="switch"
            :aria-checked="prefs.voice_enabled"
            :class="{ 'is-on': prefs.voice_enabled }"
            :disabled="props.saving"
            @click="toggleVoice"
          >
            <span class="t-switch__knob" />
          </button>
        </div>

        <div class="t-set t-set--disabled">
          <div class="t-set__label">
            音色
            <span class="t-set__hint">更多音色后续开放（当前音色较少，暂不可选）</span>
          </div>
          <select class="t-set__select" disabled aria-label="音色（暂不可选）">
            <option>{{ prefs.voice_name || '默认音色' }}</option>
          </select>
        </div>

        <p v-if="props.saving" class="t-set__state" role="status">保存中…</p>
      </div>
    </section>
  </div>
</template>
