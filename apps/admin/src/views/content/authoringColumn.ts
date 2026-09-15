/**
 * 内容列表的**内容维护列**（新建 / 编辑入口），四个内容域共用。
 *
 * 为什么与上下架列分开：两列是**不同的权限与不同的风险**——上下架是 `content:{domain}:publish`
 * （状态机动作，必填原因、留审计），编辑是 `content:{domain}:write`（改内容字段）。
 * 合成一列会让"这个按钮要不要填原因"变成看着按钮猜。
 *
 * 为什么抽成共用实现：四个域的这列本来只差权限码与按钮文案；各写一份必然出现
 * "某个域忘了套 `PermissionGate`"（那就成了越权入口）。
 */
import { h } from 'vue'
import { NButton } from 'naive-ui'
import type { TableBaseColumn } from 'naive-ui/es/data-table/src/interface'

import type { ContentRowBase } from '@/api'
import PermissionGate from '@/components/common/PermissionGate.vue'

export interface AuthoringAction<T> {
  label: string
  onClick: (row: T) => void
}

/**
 * @param permission 该域的写权限码（`content:song:write` 等）；**所有**按钮共用它
 * @param actions 按钮列表（如歌曲域是「编辑 / 歌词」）
 */
export function authoringColumn<T extends ContentRowBase>(
  permission: string,
  actions: AuthoringAction<T>[],
): TableBaseColumn<T> {
  return {
    title: '内容维护',
    key: 'authoring',
    width: 60 + actions.length * 60,
    render: (row) =>
      h(PermissionGate, { code: permission }, () =>
        actions.map((action) =>
          h(
            NButton,
            { size: 'small', quaternary: true, onClick: () => action.onClick(row) },
            () => action.label,
          ),
        ),
      ),
  }
}
