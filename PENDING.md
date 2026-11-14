# 活动未完成登记

本文件只记当前未完成的事项，每项写明对象、触发条件和责任人。已决、已关闭的事项，以及只能等真实场景出现的被动观察，不在这里续期。更早的历史在共享档案和旧私有仓库 `LucaLin233/Agent` 的 Git 历史里（本仓库是无历史快照）。

- **待条件｜OnlyBoxes 版本基线与工具依赖重核**。触发条件：console、worker 或镜像的 `0.14.1` 不再是现役版本；出现与已登记基线冲突的现场证据；或下一次 Minis 执行环境选址、OnlyBoxes 操作需要依赖历史限额或镜像能力。命中时由主助理重核，按证据更新 `skills/luno-ops/references/execution-environment.md`〔分支 execution-environment〕第 1、3 步和 `skills/luno-ops/references/execution-environment.md`〔分支 onlyboxes〕，不沿用旧数值。责任人：主助理。

- **待条件｜OnlyBoxes worker 宿主风险取舍**。原有的 host 网络和 Docker socket 两项没有按加固方案实施，MCP 登记退役并不关闭这两项；风险结论见 `skills/luno-ops/references/execution-environment.md`〔分支 execution-environment〕第 1 步；完整取证在 Git `6756b5f` 版同文件的 onlyboxes-baseline 分支〈宿主风险（未解除）〉，尚未现场复验。加固应使用会校验请求体的 Docker 代理；只按方法和路径做 ACL 挡不住 `POST /containers/create` 请求体里的逃逸参数。触发条件：用户决定保留现状或另行批准加固方案和授权，或者 worker-sys、执行路由、socket、网络、版本发生变化。责任人：主助理。

## 暂缓事项（PR #51）

- **Surge 原生 MCP 替代桥接｜暂缓**：用户 Surge iOS 尚未续费；待续费且明确启动评估时，由后续会话负责人核对实例版本、订阅权益、实际 tools schema、认证权限、敏感输出及与自建桥的能力差异，再决定替代范围。本批不接入、不迁移、不退役桥接。承接：[PR #51](https://github.com/LucaLin233/Agent-Sync/pull/51)。
- **Mac 本机优先官方 Skill｜暂缓**：用户目前无 Mac；待具备 Mac、自有官方应用包且明确启动时，由后续会话负责人核对版本、原件可读性及使用与分发边界。本批不安装、不实测，不让 iOS 普通使用依赖 Mac 应用包；luno-surge 仍保留 iOS 及跨端桥接的安全差异。承接：[PR #51](https://github.com/LucaLin233/Agent-Sync/pull/51)。
