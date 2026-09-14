# 社区列表改完资料不刷新：卡片仍是旧头像/旧昵称（点进详情才更新）

> 归档日期：2026-09-14 · 发现人：组长手机实测（两张截图 + 一句话「这个成年中级是我的账号，我在修改了个人的头像和名称后都没有即时刷新，点进去才能看到」）· 模块：`apps/web` `stores/community.ts` + `views/mobile/MobileProfileView.vue`
> 修复 commit：见本条目所在 PR（`fix(web)`）

## 复现

1. 进 `/m/me/profile`（我的资料）→ 换头像 + 改昵称 → 保存（资料页提示「已保存」，顶栏/抽屉头像立即是新头像）；
2. 返回 `/m/home`（社区）：卡片头**仍是旧昵称「成年中级」+ 无头像时的首字母兜底块**（截图 1）；
3. 点进该帖 `/m/post/:id`：作者变成新昵称「林浩然」+ 新头像（截图 2）——即「点进去才能看到」。

**差异化证据（同一屏）**：截图 1 里顶栏左一头像**已经是新头像**，只有卡片是旧的 → `auth.me`（顶栏/抽屉）通路正常，问题只出在 feed 的作者快照。

## 根因

`stores/community.ts` 的 `load()` 命中**按 domain 的缓存**就 `return`、**不发请求**（2026-09-09 为「切 Tab 免骨架屏」引入，见 `社区S3-手机实测三连-头像与发帖可见性.md`）。而 feed 的 `items` 里存的是服务端随流带回的**作者快照**（`AuthorView`：nickname/handle/tint/level/avatarUrl，一次带回、零额外请求）：

- 回 `/m/home` → `load(null)` 命中缓存 → 渲染改资料前的快照；
- 详情页 `usePostDetail.load()` 自己 `fetchPost(id)` 重拉 → 服务端现拼的作者是真值 → 「点进去才更新」；
- 电脑整页刷新 = store 重建 + 重新拉流 → 看起来「刷新一下就好」。

这不是新缺陷，是 2026-09-09 那条「**跨页写入必须显式同步缓存**」的同类漏改：当时补了发帖路径（`prepend`），漏了改资料路径。

## 修复

1. `stores/community.ts` 新增 `applyMyProfile(me)`：把「我」的 nickname/handle/avatarUrl **就地改写**到
   - `items`（当前列表 → 立即重渲染），以及
   - **所有 domain 缓存条目**里的本人作者快照（判据 `post.author.id === me.userId`；`AuthorView.id` 就是 `users.id`）。

   传**服务端回包**（`GET /auth/me` / `PATCH /api/v1/users/me`）而不是本地输入值：`CommunityService.loadAuthors` 每次请求都从 `users` + `user_profiles` 现拼，回包即服务端真值。`userId` 缺失 → 直接 return（宁可不改，不可改错人）。
2. `MobileProfileView.save()`：`patchMe` 回包后立刻 `community.applyMyProfile(updated)`，再 `auth.fetchMe()`。

**刻意不做 `invalidate()`**：清缓存确实也能修显示，但会让「返回社区」多闪一次骨架屏 + 一次无谓往返，而此刻缓存已被改成正确值。

## 验证

**前端单测（+4，均修复前必失败）**：

- `stores/__tests__/community.test.ts` +3：
  - 改资料后本人作者快照就地更新，**命中缓存也不回退**旧昵称/旧头像（别人的作者快照不受影响）；
  - 其他 domain 的缓存条目同步（切 Tab 不弹回旧昵称）；
  - `me=null` / `userId` 缺失时不动任何作者快照。
- `views/mobile/__tests__/MobileProfileView.test.ts` +1（新文件）：社区首页先拉过流（旧快照进 `items` + 缓存）→ 资料页换头像 + 改昵称/@handle 保存 → `patchMe` 载荷正确、`items` 作者立即是新值、`load(null)` 命中缓存（`fetchFeed` 仍只调过 1 次）也不回退、`auth.me` 同步为新值。

**修复前必失败实证（临时还原修复后重跑，非口头）**：

- 视图接线 + store 函数体都摘掉 → **3 failed**，三处均为 `expected '成年中级' to be '林浩然'`；
- 只留 `apply(items.value)`、摘掉「遍历 cache」那一行 → 跨 domain 那条 **1 failed**（证明缓存遍历是承重的，不是装饰）；还原后 292 passed。

**门禁**：`pnpm lint` / `pnpm typecheck`（真门禁）/ `pnpm test:run` **292 passed (49 files)**（288/48 → +4/+1）/ `pnpm build` 全绿；后端与契约零改动（Java `UserMeApiTest` 早已覆盖「改资料后 feed 作者带新头像」，本次纯前端缓存问题，契约快照零 diff）。

## 踩坑

1. **同一个坑第三次踩：跨页写入 → 必须显式同步 store 缓存。** 该 store「命中缓存即不发请求」是好事（免骨架屏），但任何**在别的页面发生的写操作**都要回来同步：发帖 → `prepend`，改资料 → `applyMyProfile`。下次再有跨页写入（关注/拉黑/删除等影响卡片的操作），先问一句「feed 的哪些字段会因此变旧」。
2. **测试 fixture 返回同一个对象 = 假绿。** 跨 domain 那条用例最初写成 `mockResolvedValue(page([...]))`，两个 domain 的缓存拿到的是**同一个 item 对象** → 即使摘掉缓存遍历也照样绿。真实链路每次响应都是新解析出的实例，必须 `mockImplementation` 每次造新对象；改完之后该用例才在修复前变红。**「测试绿」不等于「测试在测」——每条新断言都要能回答：它在修复前为什么会红？**
3. **别用 `invalidate()` 图省事。** 它也能修好显示，代价是每次回首页闪骨架屏 + 一次额外往返；作者快照的正确值此刻已经在手上，就地改写更准更稳（与 `prepend` 同一处方）。
