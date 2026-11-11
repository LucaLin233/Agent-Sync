# 来源维护

中文精选改写自 CCH-HQ/cchp-cli；MIT，Copyright (c) 2026 the cchp contributors；完整许可随包见 ../LICENSE.upstream.txt。固定提交、取材文件、映射、排除项及许可在仓库 skills-sources.md〈luno-cchp〉；维护前完整读取，缺登记停止依赖判断。普通控制面操作不加载档案，官方凭据回退不适用于本端。

按 `luno-core/references/sync.md`〔分支 sync〕及〔分支 sync-workflow〕核对上游，不自动跟版。以登记基线为旧 ref，锁定新 HEAD，逐个核全部取材文件（含 docs、LICENSE）的哈希及变化 diff；404 区分新增、删除和改名。结合 CHANGELOG/release 与 CLI/spec 实际契约，文件未变不等于契约未变，取不齐标缺证，不判无需更新。

列出 `luno-platform/references/cchp.md` 各分支、业务资源及 `references/cchp-coverage-rules.md` 的受影响章节、旧新语义与适用性；版本号差异不单独构成禁用条件。核对不授权实施，不改未采纳基线；按变化对象更新来源和部署回读哈希，不因上游新增命令扩充无需求流程。
