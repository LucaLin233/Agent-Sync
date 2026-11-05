# 活动未完成登记

本文件只记当前未完成项；每项写对象、条件与责任人。`待条件`／`待他批`之外的已决、已关闭与只能等真实场景的被动观察不在此续期。历史记录见共享档案与旧私有 `LucaLin233/Agent` 的 git 历史（本仓库为无历史快照，不含该历史）。

- **待条件｜OnlyBoxes 版本基线与工具依赖重核**。条件：console／worker／镜像的 `0.14.1` 不再为现役，出现与已登记基线冲突的现场证据，或下一次涉及 Minis 执行环境选址或 OnlyBoxes 操作时需要依赖历史限额或镜像能力；命中条件时由主助理重核，并按证据更新 `skills/luno-ops/references/execution-environment.md` 与 `skills/luno-ops/references/onlyboxes-baseline.md`，不得沿用旧数值。责任人：主助理。

- **待条件｜OnlyBoxes worker 宿主风险取舍**。原有 host 网络与 Docker socket 两项未按加固方案实施；MCP 登记退役不关闭这两项。历史取证和前提迁至 `skills/luno-ops/references/onlyboxes-baseline.md`〈历史宿主风险与未决选择〉；本轮未现场复验。条件：用户确定保留现状或另批加固方案及授权，或 worker-sys、执行路由、socket、网络、版本发生变化；责任人：主助理。
