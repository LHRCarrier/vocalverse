<script setup lang="ts">
/**
 * 移动端骨架屏（docs/31 硬规则 3：加载 >300ms 才出现）
 *
 * 复用既有 `.u-comm-skel*` 视觉（呼吸只动 opacity，60fps 安全），
 * 把原先在 3 个视图里各抄一份的 markup 收敛成一处。
 * 显示时机由调用方配 `useDelayedLoading` 控制：<300ms 完成的请求不闪骨架。
 *
 * variant：feed=头像+两行+媒体（社区流）/ media=仅媒体块（书架）/ lines=仅两行（词表）
 */
withDefaults(
  defineProps<{
    variant?: 'feed' | 'media' | 'lines'
    count?: number
    label?: string
  }>(),
  { variant: 'feed', count: 0, label: '内容加载中' },
)
</script>

<template>
  <section class="u-comm-skel" :aria-label="label" aria-busy="true">
    <div
      v-for="i in (count || (variant === 'media' ? 4 : 3))"
      :key="i"
      class="u-comm-skel__card"
    >
      <template v-if="variant === 'feed'">
        <span class="u-comm-skel__ava" />
        <span class="u-comm-skel__lines">
          <span class="u-comm-skel__line" style="width: 52%" />
          <span class="u-comm-skel__line" style="width: 78%" />
        </span>
        <span class="u-comm-skel__media" />
      </template>

      <template v-else-if="variant === 'media'">
        <span class="u-comm-skel__media" />
      </template>

      <template v-else>
        <span class="u-comm-skel__lines">
          <span class="u-comm-skel__line" style="width: 62%" />
          <span class="u-comm-skel__line" style="width: 88%" />
        </span>
      </template>
    </div>
  </section>
</template>