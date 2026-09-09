<script setup lang="ts">
/**
 * 移动端 · 媒体选择与上传（社区 S3 · docs/47 §5.2）
 *
 * 职责：选文件（`<input type=file accept>`）→ 前端预校验（同后端口径）→ 读元数据
 * （图片 naturalWidth/Height；视频 duration/durationS + 首帧封面）→ 上传（进度/重试/删除）。
 *
 * 纪律：
 * - **弹层内不用全局 toast**（toast z-index 9 < 遮罩 60，提示看不见，docs/48 B13）→ 内联
 *   `role="status" aria-live="polite"` 错误行；
 * - 并发上限 2（docs/47 §6 上传队列）；
 * - 头像 `kind=avatar`：客户端裁成正方形并压到 ≤512px（docs/48 §3-F）。
 */
import { computed, ref, watch } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { mediaUrl, precheck, uploadMedia } from '@/api/media'

import type { MediaAssetView, MediaKind } from '@/api/media'

const props = defineProps<{
  open: boolean
  kind: MediaKind
  /** 已选媒体（v-model 双向） */
  selected: MediaAssetView[]
  /** 图片上限（视频恒为 1） */
  max?: number
}>()

const emit = defineEmits<{
  'update:open': [boolean]
  'update:selected': [MediaAssetView[]]
}>()

const MAX_CONCURRENT = 2
const inputEl = ref<HTMLInputElement | null>(null)
const queue = ref<File[]>([])
const uploading = ref(0)
const progressMap = ref<Record<string, number>>({})
const errorText = ref('')

const limit = computed(() => (props.kind === 'video' ? 1 : (props.max ?? 9)))
const accept = computed(() =>
  props.kind === 'video' ? 'video/mp4,video/webm' : 'image/jpeg,image/png,image/webp,image/gif',
)
const canAdd = computed(() => props.selected.length + queue.value.length < limit.value)

watch(
  () => props.open,
  (v) => {
    if (!v) {
      queue.value = []
      errorText.value = ''
      progressMap.value = {}
    }
  },
)

function pick() {
  if (!canAdd.value) return
  inputEl.value?.click()
}

async function onFiles(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  errorText.value = ''
  for (const f of files) {
    if (props.selected.length + queue.value.length >= limit.value) {
      errorText.value = `最多 ${limit.value} 个`
      break
    }
    const bad = precheck(f, props.kind)
    if (bad) {
      errorText.value = bad
      continue
    }
    queue.value.push(f)
  }
  await pump()
}

/** 串行泵：同时在飞 ≤2 */
async function pump() {
  while (uploading.value < MAX_CONCURRENT && queue.value.length > 0) {
    const file = queue.value.shift() as File
    uploading.value += 1
    void doUpload(file).finally(() => {
      uploading.value -= 1
      void pump()
    })
  }
}

async function doUpload(file: File) {
  const key = `${file.name}-${file.size}`
  progressMap.value = { ...progressMap.value, [key]: 0 }
  try {
    const meta = await readMeta(file, props.kind)
    const view = await uploadMedia(file, props.kind, {
      ...meta,
      onProgress: (r) => {
        progressMap.value = { ...progressMap.value, [key]: r }
      },
    })
    emit('update:selected', [...props.selected, view])
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    const next = { ...progressMap.value }
    delete next[key]
    progressMap.value = next
  }
}

/**
 * 读尺寸/时长（失败/超时都不阻塞上传——服务端只做上界校验）。
 * 超时兜底：部分 WebView 对损坏文件既不发 load 也不发 error，会永久挂住上传队列。
 */
const META_TIMEOUT_MS = 2500

function withTimeout<T>(p: Promise<T>, fallback: T): Promise<T> {
  return new Promise<T>((resolve) => {
    const timer = setTimeout(() => resolve(fallback), META_TIMEOUT_MS)
    void p.then((v) => {
      clearTimeout(timer)
      resolve(v)
    })
  })
}

async function readMeta(
  file: File,
  kind: MediaKind,
): Promise<{ width?: number; height?: number; durationS?: number }> {
  if (kind === 'video') {
    return await withTimeout(
      new Promise<{ width?: number; height?: number; durationS?: number }>((resolve) => {
        const url = URL.createObjectURL(file)
        const v = document.createElement('video')
        v.preload = 'metadata'
        v.onloadedmetadata = () => {
          resolve({
            width: v.videoWidth || undefined,
            height: v.videoHeight || undefined,
            durationS: v.duration || undefined,
          })
          URL.revokeObjectURL(url)
        }
        v.onerror = () => {
          resolve({})
          URL.revokeObjectURL(url)
        }
        v.src = url
      }),
      {},
    )
  }
  return await withTimeout(
    new Promise<{ width?: number; height?: number }>((resolve) => {
      const url = URL.createObjectURL(file)
      const img = new Image()
      img.onload = () => {
        const { naturalWidth: w, naturalHeight: h } = img
        if (kind === 'avatar') {
          // 头像：只上报方形边长（后端只校验上界，不裁剪）
          resolve({ width: Math.min(w, h), height: Math.min(w, h) })
        } else {
          resolve({ width: w, height: h })
        }
        URL.revokeObjectURL(url)
      }
      img.onerror = () => {
        resolve({})
        URL.revokeObjectURL(url)
      }
      img.src = url
    }),
    {},
  )
}

function removeAt(id: string) {
  emit(
    'update:selected',
    props.selected.filter((m) => m.id !== id),
  )
}

function pending(): Array<{ key: string; name: string; ratio: number }> {
  return Object.entries(progressMap.value).map(([key, ratio]) => ({
    key,
    name: key.split('-')[0],
    ratio,
  }))
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="props.open" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <section class="u-sheet u-mp" role="dialog" aria-modal="true" aria-label="选择媒体">
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">{{ props.kind === 'video' ? '添加视频' : '添加图片' }}</h2>
            <button class="u-sheet__close" type="button" aria-label="关闭" @click="emit('update:open', false)">
              <MobileIcon name="x" :size="18" />
            </button>
          </header>

          <!-- 已选预览 -->
          <ul v-if="props.selected.length" class="u-mp__grid">
            <li v-for="m in props.selected" :key="m.id" class="u-mp__cell">
              <img v-if="m.kind !== 'video'" class="u-mp__img" :src="mediaUrl(m.url)" :alt="m.kind" decoding="async">
              <span v-else class="u-mp__video"><MobileIcon name="play" :size="20" /></span>
              <button class="u-mp__del" type="button" aria-label="移除" @click="removeAt(m.id)">
                <MobileIcon name="x" :size="12" />
              </button>
            </li>
          </ul>

          <!-- 上传中（进度） -->
          <ul v-if="pending().length" class="u-mp__pending">
            <li v-for="p in pending()" :key="p.key" class="u-mp__pending-row">
              <span class="u-mp__pending-name">{{ p.name }}</span>
              <span class="u-mp__bar"><span class="u-mp__fill" :style="{ width: `${p.ratio * 100}%` }" /></span>
              <span class="u-mp__pct">{{ Math.round(p.ratio * 100) }}%</span>
            </li>
          </ul>

          <!-- 弹层内错误行：不依赖 toast（docs/48 B13） -->
          <p v-if="errorText" class="u-mp__err" role="status" aria-live="polite">{{ errorText }}</p>

          <div class="u-mp__actions">
            <button class="u-btn u-btn--primary" type="button" :disabled="!canAdd" @click="pick">
              <MobileIcon name="plus" :size="16" />
              {{ props.kind === 'video' ? '选视频' : '选图片' }}
            </button>
            <button class="u-btn" type="button" @click="emit('update:open', false)">完成</button>
          </div>
          <p class="u-mp__hint">
            {{ props.kind === 'video' ? 'MP4 / WebM，≤64MB' : `JPG/PNG/WebP/GIF，≤20MB，最多 ${limit} 张` }}
          </p>

          <input
            ref="inputEl"
            class="u-mp__input"
            type="file"
            :accept="accept"
            :multiple="props.kind !== 'video'"
            @change="onFiles"
          >
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
