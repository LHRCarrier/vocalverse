/**
 * 学习指标 API（docs/53 P2）：控制台只读聚合（Python `/api/v1/console/insight/**`）。
 *
 * 权限码复用 `ops:metric:read`（见 `services/python/app/console/api/routes/insight.py` 头注的决策说明）；
 * 口径与用户端 `/api/v1/stats/*` 同源（`app/insight/service.py`），前端只做展示。
 */
import { opsHttp } from './client'
import type { InsightOverview } from './types'

const P = '/console'

export const insightApi = {
  overview: (days = 30) => opsHttp.get<InsightOverview>(`${P}/insight/overview?days=${days}`),
}
