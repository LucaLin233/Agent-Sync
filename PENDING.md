# 活动未完成登记

本文件只记当前未完成的事项，每项写明对象、触发条件和责任人。已决、已关闭的事项，以及只能等真实场景出现的被动观察，不在这里续期。更早的历史在共享档案和旧私有仓库 `LucaLin233/Agent` 的 Git 历史里（本仓库是无历史快照）。

- **待条件｜OnlyBoxes 版本基线与工具依赖重核**。触发条件：console、worker 或镜像的 `0.14.1` 不再是现役版本；出现与已登记基线冲突的现场证据；或下一次 Minis 执行环境选址、OnlyBoxes 操作需要依赖历史限额或镜像能力。命中时由主助理重核，按证据更新 `skills/luno-ops/references/execution-environment.md` 和 `skills/luno-ops/references/onlyboxes-baseline.md`，不沿用旧数值。责任人：主助理。

- **待条件｜OnlyBoxes worker 宿主风险取舍**。原有的 host 网络和 Docker socket 两项没有按加固方案实施，MCP 登记退役并不关闭这两项；取证和前提见 `skills/luno-ops/references/onlyboxes-baseline.md`〈宿主风险（未解除）〉，尚未现场复验。触发条件：用户决定保留现状或另行批准加固方案和授权，或者 worker-sys、执行路由、socket、网络、版本发生变化。责任人：主助理。
