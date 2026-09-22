/**
 * 酒馆 · 示例剧本种子（开局引导「示例剧本」路径）：HP/场景/行囊/任务/线索一次写齐。
 * 从 useTavernSession 拆出（fe-08 行数约束），纯请求序列、无状态。
 */
import { createClue, createTask, editFact } from '@/api/trpg'

export async function seedDemoCampaign(campaignId: number, scene: string): Promise<void> {
  await editFact(campaignId, 'pc.主角.hp', '12')
  await editFact(campaignId, 'pc.主角.location', '吧台')
  await editFact(campaignId, 'pc.主角.inventory', '短剑')
  await createTask(campaignId, '打听镇上的怪谈')
  await createClue(campaignId, '地下室里的暗门', '酒保提到过地下室的门', scene)
}
