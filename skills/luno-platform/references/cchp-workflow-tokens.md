# CCHP LLM token

先完整读 `references/cchp-workflows.md`，按其触发与共同前置使用本资源。涉及写入的解释、方案、审查或执行，还须完整读 `references/cchp-workflow-writes.md`；实际调用或展示结果先完整读 `references/cchp-interfaces.md`。

## LLM token

只在用户本次明确要求新建 LLM token、并指定了可写的受控路径时执行，否则只讨论方案。一次性密钥只出现在 `--secret-out` 文件里（mode 600，拒绝覆盖已有文件），stdout 只有占位；回报文件路径和字段名，不回显值，也不把文件内容读进会话。令牌只在创建时可以取得，之后只能轮换或撤销；轮换不可逆，按用户的明确指令执行。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。
