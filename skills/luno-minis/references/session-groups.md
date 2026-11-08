# 会话归组

只适用于本用户的 Minis。App 的分组没有描述字段，自动归组只看组名；下面的判据供助手归档和必要时改派（`minis-sessions-cli update --group`），不是 App 的归组依据。

- **CCHP**：CCH/CCHP 网关的升级迁移、Bug 排障、供应商与模型、覆写规则、配额、打包。
- **Minis 与技能**：Minis 平台的技能增改与来源登记、MCP、子代理、会话、提示词与 SOUL。
- **Surge 与模块开发**：Surge 配置、模块、脚本、面板；aiapi 也归这组，不单拆。
- **服务器运维**：主机层的内存和 swap、磁盘清理、备份打包、Redis 等常驻服务、权限。
- **容器与部署**：Docker/Compose、镜像与多架构、Nginx、服务上线与迁移。
- **仓库与工具链**：仓库 CI、测试、脚本实测、Node.js 和 onlyboxes 等运行环境。
- **网络与隧道**：Cloudflare Tunnel/cloudflared、测速、链路诊断。
- **LobeHub**：LobeHub 2.x 实例的部署、Agent 与模型、连接器、知识库。
- **创作与素材**：文案、故事、音译、图标、矢量图等非技术产出。
