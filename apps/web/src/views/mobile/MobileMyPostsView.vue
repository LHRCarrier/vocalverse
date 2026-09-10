<script setup lang="ts">
/**
 * 移动端 · 我的发帖（社区 S3 · 2026-09-09 组长实测补：发完帖没有「我的」通道回看）
 *
 * 数据源：`GET /api/v1/community/posts?mine=true`（服务端按 actor 过滤 + keyset 游标）。
 * 卡片复用 `MobilePostCard`（整卡可点 → 详情页），删除走详情页（避免列表误触）。
 *
 * 为什么单独一页而不是复用社区首页的 Tab：feed 的 domain 过滤与「作者过滤」是正交维度，
 * 混在一起会让 Tab 语义分裂（docs/48 §5「作者主页」登记项的最小落地）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobilePostCard from '@/components/mobile/MobilePostCard.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { deletePost, fetchFeed } from '@/api/community'
import { useMobileBack } from '@/composables/useMobileBack'
import { useCommunityStore } from '@/stores/community'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

import type { CommunityPostView } from '@/types/community'

const router = useRouter()
const ui = useUiStore()
const community = useCommunityStore()
const goBack = useMobileBack('/m/home')

const items = ref<CommunityPostView[]>([])
const cursor = ref<string | null>(null)
const hasMore = ref(false)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')

const isEmpty = computed(() => !loading.value && !error.value && items.value.length === 0)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await fetchFeed(null, null, 10, undefined, true)
    items.value = page.items
    cursor.value = page.nextCursor
    hasMore.value = page.hasMore
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || !hasMore.value || !cursor.value) return
  loadingMore.value = true
  try {
    const page = await fetchFeed(null, cursor.value, 10, undefined, true)
    items.value = items.value.concat(page.items)
    cursor.value = page.nextCursor
    hasMore.value = page.hasMore
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '加载更多失败')
  } finally {
    loadingMore.value = false
  }
}

/** 列表内删除（详情页也能删；这里给一个不跳页的快捷入口） */
async function remove(item: CommunityPostView) {
  try {
    await deletePost(item.id)
    items.value = items.value.filter((p) => p.id !== item.id)
    community.items = community.items.filter((p) => p.id !== item.id)
    ui.showToast('已删除')
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '删除失败')
  }
}

function tintGradient(tint: string | null | undefined): string {
  if (!tint) return 'linear-gradient(135deg, #37546e, #6e96b4)'
  return `linear-gradient(135deg, ${tint}, #fff3)`
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="u-phone u-myp">
    <MobileTopBar title="我的发帖" back @back="goBack">
      <template #actions>
        <button class="u-topbar__act" type="button" title="发帖" aria-label="发帖" @click="router.push('/m/compose')">
          <MobileIcon name="plus" :size="18" />
        </button>
      </template>
    </MobileTopBar>

    <main class="u-myp__body">
      <p v-if="loading" class="u-comm-empty__sub">加载中…</p>

      <div v-else-if="error" class="u-comm-empty" role="status">
        <span class="u-comm-empty__icon"><MobileIcon name="info" :size="28" /></span>
        <p class="u-comm-empty__title">加载失败</p>
        <p class="u-comm-empty__sub">{{ error }}</p>
        <button class="u-comm-empty__btn" type="button" @click="load">重试</button>
      </div>

      <div v-else-if="isEmpty" class="u-comm-empty" role="status">
        <span class="u-comm-empty__icon"><MobileIcon name="hash" :size="28" /></span>
        <p class="u-comm-empty__title">还没有发过内容</p>
        <p class="u-comm-empty__sub">去发一条，记录你的学习心得～</p>
        <button class="u-comm-empty__btn" type="button" @click="router.push('/m/compose')">去发帖</button>
      </div>

      <template v-else>
        <div v-for="item in items" :key="item.id" class="u-myp__row">
          <MobilePostCard
            :post="item"
            :tint-gradient="tintGradient(item.author.tint)"
            @toggle-like="community.toggleLike(item)"
            @coin="community.coin(item)"
            @share="ui.showToast('分享请到详情页')"
            @open-comments="router.push(`/m/post/${item.id}`)"
          />
          <button class="u-myp__del" type="button" :aria-label="`删除《${item.title ?? item.body ?? ''}》`" @click="remove(item)">
            <MobileIcon name="trash" :size="15" />删除
          </button>
        </div>

        <button
          v-if="hasMore"
          class="u-comm-more"
          type="button"
          :disabled="loadingMore"
          @click="loadMore"
        >
          {{ loadingMore ? '加载中…' : '加载更多' }}
        </button>
      </template>
    </main>
  </div>
</template>
