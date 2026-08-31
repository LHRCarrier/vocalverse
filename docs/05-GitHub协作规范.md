# 05 · GitHub 协作规范

## 仓库信息

- 地址：https://github.com/LHRCarrier/vocalverse
- 可见性：**公开**（选题阶段为开启分支保护选择公开；代码中严禁出现任何密钥/隐私数据）
- 成员：LHRCarrier（owner/admin）、xiaoqing-one、Faust-sudo（write）
- 默认分支：`main`

## 分支保护规则（已生效）

| 规则 | 设置 |
|---|---|
| 直接 push main | ❌ 禁止 |
| 合并方式 | 必须 Pull Request |
| 评审 | 至少 **1 人** 通过 |
| 新 commit 后旧评审 | 自动失效（dismiss stale reviews） |
| force push | ❌ 禁止 |
| 删除分支 | ❌ 禁止 |
| 管理员 | 不受保护限制（enforce_admins 关闭，仅组长可用） |

## 工作流程

```
1. git pull origin main                      # 先同步
2. git checkout -b feat/xxx                  # 功能分支: feat/fix/docs/chore
3. 开发 + 自测
4. git push origin feat/xxx
5. gh pr create --fill（或网页创建 PR，描述问题/改动/自测）
6. 待 1 位队友 Review 通过
7. Merge（squash 合并，自动删除分支）
```

- 每位成员负责的 PR，**由另一名成员评审**（不要自审自合）
- 组长如需紧急直推 main（管理员特权），须在群里说明

## Commit 规范（Conventional Commits）

```
feat(agent): 增加场景扮演多轮对话状态管理
fix(asr): 修复流式录音分帧边界丢帧
docs: 更新功能规划（M3 砍掉 3D 数字人）
chore: 升级 vue 依赖
```

## 其他约定

- **Issue**：里程碑任务全部开 Issue，用标签 `m1/m2/m3/m4`，PR 关联 `Closes #1`
- **密钥**：`.env` 不入库（已在 .gitignore）；示例用 `.env.example`
- **公开仓库红线**：不提交 API Key、数据库密码、用户真实数据、训练数据集的原始文件
- 仓库状态变更（如转私有）须全员知晓：转私有后免费版分支保护将失效
