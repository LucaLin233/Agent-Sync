分支：agent-document-writing、skill-authoring。读法见 luno-core 入口〈加载〉。

<a id="branch-agent-document-writing"></a>
<!-- BEGIN agent-document-writing -->
# 规则正文书写

本资源是**书写启发式**：常驻提示词、技能正文与 `description`、包内资源和子代理指令该怎么写、哪些该删、指针怎么措辞。它不是硬约束，与授权、安全、角色、派发、同步和语义保真的成文规则冲突时，以后者为准。

## 写法

- **流程类规则写成完整句**：写清主语、条件、例外，并用半句话交代原因。模型知道规则为什么存在，才能在规则没覆盖到的边界情况下推断正确。避免内部代号、省略主语的否定排比和「随单」「依core」这类缩写。
- **硬禁令保留禁令式**：秘密、凭据、不可逆操作和生产安全相关的禁止事项直接写「不得」「禁止」，不为了顺口而软化。
- **一件事只写一处**：一个意思只留一处权威写法，改行为时只改一处。加载规则、「加载不等于授权」和秘密规则都以 `luno-core` 为准，各技能不再复述，只写本领域特有的事实和限制。常驻提示词和子代理指令例外：它们在 core 加载前就生效，子代理也不注入常驻提示词，所以各自保留秘密底线和「先完整加载 core」的句子。
- **常驻规则里不写批次用语**：「本批」「本单」「本轮」这类词在部署后已经没有所指，改成不带时态的陈述。带日期和版本的经验结论保留平台或实例、版本和证据日期（总控要求）。

## 指针与触发

指针是上下文中指向外部材料、并注明读取时机的一行（技能 `description`、加载语句、资源指句）。**读取时机由措辞决定，而不是由目标决定**：必读的材料配上含糊的措辞会导致时读时不读，先把措辞写准，再考虑是否内联。每个真实分支（文档要处理的不同情形）写一个触发，同一分支的同义说法合并；正文里已经写明的身份不必在指针里重复。常驻的指针每轮都要付费，删减标准要比正文更严。

**反引号里的跨技能路径必须带技能名前缀**（如 `luno-surge/references/SOURCE.md`），不能只写 `references/…`：后者会被 `tools/check-rules.py` 按**当前技能根**解析，判为引用断链或资源边未登记。

## 负载与披露

分清每轮常驻、角色启动、任务加载闭包、派发随单和检索索引各自的成本。入口只放所有分支都需要的规则；只有部分任务需要的内容，按真实分支设明确的触发；定义、规则和例外放在一起。新增资源必须能减少实际任务的加载闭包，不能只是搬位置；文件数减少不等于减负，不同分支的内容也不要合成一个大包。移动后的文本仍然计入总量，内容仍在上下文里时，不要宣称后续可以免费。

## 完成判据

每个步骤都以完成判据收尾，也就是「怎样算做完」。好的完成判据有两个性质：**可分辨**，能分清做完和没做完，边界模糊会诱发提前收尾；**有深度**，措辞里要带上工作量，「逐个核到」比「产出清单」更有力，平铺的规则也适用。先把边界写清楚；只有边界天然模糊、确实出现抢跑时，才按真实的上下文边界拆分，而且只有跨越真实的交接点时，拆分才能清空上下文。

## 删减判据

- **环境本身就是真源**：复述环境（配置、目录布局、命令输出）的文字只是缓存；只缓存查不到的东西，比如没成文的约定、选择背后的理由、配置里看不出来的坑。
- **相关性**：删掉不承载当前任务的行，以及会随行为和外部世界变化而过时的行。
- **沉积**：只增不减会形成旧层；加规则安全、删规则冒险，时间长了活的规则就要往下翻很久才找得到。
- **no-op 逐句测试**：判断标准是「相对默认行为有没有改变」，靠实际跑一次或对照已有行为来判断，不靠辩论；一句话不过关就整句删掉，不逐字修补。

不采用的做法：按调用拆分技能、router skill、`disable-model-invocation` 之类的调用机制，以及用单个「锚词」代替多句说明。

来源与许可：mattpocock/skills，MIT 精选改写；Copyright (c) 2026 Matt Pocock。完整许可随包见 ../LICENSE.matt-pocock.txt；固定提交、取材路径与日期见仓库 skills-sources.md。
<!-- END agent-document-writing -->

<a id="branch-skill-authoring"></a>
<!-- BEGIN skill-authoring -->
# 技能编写与结构校验

通用写法（自由度、目录与 `scripts/`/`references/`/`assets/` 分工、渐进披露、`description` 写法）按 [Anthropic 技能编写最佳实践](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) 和 [Agent Skills 规范](https://agentskills.io/specification)；效果评测（with/without 对照、近失负例、留出集、多次运行看方差、客观断言与人工判断分开）按 [anthropics/skills 的 skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)。改技能就是改行为，要有对照，不凭印象。效果评测须在运行前写明成功、失败的判据和观察输出；不得在看到结果后选择判据。书写启发式见 `references/agent-document-writing.md`〔分支 agent-document-writing〕；发布、登记刷新和平台安装见 `luno-core/references/sync.md`〔分支 sync〕、`luno-platform/references/minis.md`〔分支 minis〕和 `luno-platform/references/lobehub.md`〔分支 lobehub〕。

- **受管范围**：下列约束只针对受管的自定义技能；平台内置技能不按此判定无效，也不改写、不纳入受管同步。受管技能的目录名必须等于 `name`。
- **结构校验**：本地只用 `luno-core/scripts/quick_validate.py`（唯一实现），按本次变化的技能直接调用。它只查 frontmatter 的字段与限制、目录名与 `name` 相同、正文非空；**通过不等于可用**，正文质量、`description` 的触发、资源引用、链接与代码能否运行、许可是否齐备都不查。运行需要 Python 3 和 PyYAML；依赖或脚本缺失就停，不回退较弱判据，也不自动安装。

来源登记：校验器改写自 openai/skills 的 skill-creator（Apache-2.0，已修改），完整许可见 ../LICENSE.apache-2.0.txt，固定提交与取材路径见仓库 skills-sources.md。
<!-- END skill-authoring -->

