# Surge Mac 插件：本端边界

插件只在 Surge Mac 上运行（当前类型 `ap-controller`），iOS 不支持。仅在用户明确要求 macOS 插件工作时使用本文件，并先完整读 `references/command-reference.md`〔分支 platform-compatibility〕。

开发契约（manifest、参数 schema、JavaScript API、事件、限额、打包产物）以官方插件指南为准。它随 Surge Mac 应用包分发，位于 `/Applications/Surge.app/Contents/Resources/Skills/surge/references/plugin-authoring.md`，没有公开网页版；在用户的 Mac 上直接用应用包里的官方 Skill 做插件开发。读不到官方指南就停止相关步骤，不凭记忆补字段或限额。

本端只补这些边界：

- 在线 `plugin` 子命令（protocol ≥24，仅 macOS）可以经本桥 `--remote` 发给用户指定的 Mac；`plugin validate`、`plugin pack` 是官方 Mac CLI 的本地工具，本桥不实现。
- 配置前先用 `plugin parameters` 读 schema。插件参数以明文存储、界面可见，不是秘密保管库；`plugin list`/`info` 返回的 values 可能含秘密，先限制读取。
- 敏感参数不以 `token=…` 之类的 argv 形式配置：只有已核实的安全入口能让秘密不进 argv、日志和输出时才配置，否则暂停这一步。官方示例里的 `insecure: true` 不是本端默认，保持证书和主机名校验。
- `plugin configure` 会运行插件自己的验证代码，可能访问外部网络；重连事件会真实断开设备，不当只读测试；`plugin uninstall` 会删除插件的持久存储，须另获删除授权。构建、上传和发布是三种授权，不联动。
- 验收分别记录格式检查、真实参数验证、面板数据和获准的重连结果；构包成功不代替设备行为。
