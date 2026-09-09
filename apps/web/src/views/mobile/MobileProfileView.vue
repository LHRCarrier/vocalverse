<script setup lang="ts">
/**
 * 移动端 · 我的资料（社区 S3 · docs/47 §5.1 · /m/me/profile）
 *
 * 头像上传（`kind=avatar`）+ 昵称 / @handle 编辑 → `PATCH /api/v1/users/me`。
 * 读取沿用 `auth.fetchMe()`（GET /auth/me 已扩展 avatarUrl/handle）。
 *
 * 纪律：弹层内错误内联展示（不用 toast，docs/48 B13）；保存中禁用按钮；
 * 头像 URL 只接受本服务媒体地址（后端二次校验，前端先拦一道）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileAvatar from '@/components/mobile/MobileAvatar.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileMediaPicker from '@/components/mobile/MobileMediaPicker.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { patchMe } from '@/api/users'
import { useMobileBack } from '@/composables/useMobileBack'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

import type { MediaAssetView } from '@/api/media'

const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const goBack = useMobileBack('/m/home')

const nickname = ref('')
const handle = ref('')
const avatarUrl = ref<string | null>(null)
const avatarSel = ref<MediaAssetView[]>([])
const pickerOpen = ref(false)
const saving = ref(false)
const errorText = ref('')

const canSave = computed(
  () => nickname.value.trim().length > 0 && !saving.value,
)

onMounted(async () => {
  await auth.fetchMe()
  nickname.value = auth.me?.nickname ?? ''
  handle.value = auth.me?.handle ?? ''
  avatarUrl.value = auth.me?.avatarUrl ?? null
})

function onAvatarSelected(list: MediaAssetView[]) {
  avatarSel.value = list
  const last = list[list.length - 1]
  if (last) avatarUrl.value = last.url
}

async function save() {
  if (!canSave.value) return
  saving.value = true
  errorText.value = ''
  try {
    await patchMe({
      nickname: nickname.value.trim(),
      handle: handle.value.trim() || undefined,
      avatarUrl: avatarUrl.value ?? '',
    })
    await auth.fetchMe()
    ui.showToast('已保存')
  } catch (e) {
    // 40904 = @handle 被占用（docs/api/error-codes.md）
    const code = (e as { code?: number }).code
    errorText.value =
      code === 40904 ? '这个 @handle 已经被占用了，换一个试试' : (e as Error).message || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="u-phone u-pf">
    <MobileTopBar title="我的资料" back @back="goBack" />

    <main class="u-pf__body">
      <!-- 头像 -->
      <section class="u-pf__avatar-row">
        <MobileAvatar
          :src="avatarUrl"
          :name="nickname || auth.me?.nickname"
          :tint="auth.me?.tint"
          size="lg"
        />
        <button class="u-btn u-btn--secondary" type="button" @click="pickerOpen = true">
          <MobileIcon name="plus" :size="16" />更换头像
        </button>
      </section>

      <!-- 昵称 -->
      <label class="u-pf__field">
        <span class="u-pf__label">昵称</span>
        <input v-model="nickname" class="u-pf__input" type="text" maxlength="64" placeholder="你的昵称">
      </label>

      <!-- @handle -->
      <label class="u-pf__field">
        <span class="u-pf__label">@handle</span>
        <input v-model="handle" class="u-pf__input" type="text" maxlength="32" placeholder="英文/数字，社区展示用">
      </label>
      <p class="u-note">@handle 全局唯一（大小写不敏感），改过之后别人看到的就是新名字。</p>

      <p v-if="errorText" class="u-pf__err" role="status" aria-live="polite">{{ errorText }}</p>

      <div class="u-pf__actions">
        <button class="u-btn u-btn--primary u-btn--block" type="button" :disabled="!canSave" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>

      <!-- 我的发帖入口（2026-09-09 组长实测补：发完帖没有「我的」通道回看） -->
      <button class="u-pf__link" type="button" @click="router.push('/m/me/posts')">
        <MobileIcon name="hash" :size="18" />
        <span>我的发帖</span>
        <MobileIcon name="chevron" :size="16" class="u-pf__link-go" />
      </button>
    </main>

    <MobileMediaPicker
      :open="pickerOpen"
      kind="avatar"
      :selected="avatarSel"
      :max="1"
      @update:open="pickerOpen = $event"
      @update:selected="onAvatarSelected"
    />
  </div>
</template>
