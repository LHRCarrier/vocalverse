<script setup lang="ts">
/**
 * 「下架暂无用户侧消费者」常驻提示（docs/50 §6.1 联动回路 + §15.2 G-2）。
 *
 * 存在的理由：`songs` / `listening_materials` 的 `status` 目前**没有任何用户侧读方**
 * （唱歌与听力推荐池尚未实现），下架对学习者不可见。控制台必须把这条缺口写在页面上，
 * 否则运营会以为下架已经对所有用户生效——"不伪造效果"是 §6.1 的明文要求。
 */
defineProps<{ target: string }>()
</script>

<template>
  <p class="gap" role="note">
    <span class="c-badge c-badge--warn">已知缺口</span>
    <span>
      下架后的{{ target }}状态暂无用户侧消费者：App 侧尚未按状态过滤，
      下架目前不会改变用户看到的内容。本页只保证状态被正确写入并留痕，不代表对用户已生效。
    </span>
  </p>
</template>

<style scoped>
.gap {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0 0 14px;
  padding: 10px 12px;
  border-radius: var(--c-ctl-radius);
  background: var(--c-warn-soft);
  color: var(--c-warn);
  font-size: 12.5px;
  line-height: 1.6;
}
</style>
