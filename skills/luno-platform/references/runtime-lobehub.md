# LobeHub 端运行适配

本资源是 `luno-platform` 入口〈运行端〉在 LobeHub 端（已部署 LobeHub 2.x CE 中的助理）的槽位取值。中立规则按〈槽位名〉引用这里；义务、授权和停止条件以引用处为准，本资源只给本端的机制和取值，不新增或放宽权限。未列出的槽位即本端未规定，按引用处的中立规则执行。

## 通用兜底

LobeHub 只能匿名执行或取证，否则报告不可用，不静默换助理。

## 执行环境

本端执行环境经 Debian 设备。

## 远端工作目录

LobeHub 端的执行目录由平台的工作目录设置决定，不套用 Minis 的路径；LobeHub 端自己已有的工作目录不动。

来源与许可：自编本端适配。自 `luno-core` 迁入的句子沿用原文件的 MIT 精选改写性质（Copyright (c) 2026 Matt Pocock；Copyright (c) 2026 OpenMinis），完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。
