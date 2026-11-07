---
name: luno-coding
description: 代码编写、修复、重构与审查的实施侧核对：最小改动、复现、回归和结果证据。
---

# LUNO｜代码实施纪律

<!-- 来源：mattpocock/skills@4ae2317ddb22b046e26455e4f9c9b3aaaf62212d；路径：skills/engineering/tdd/SKILL.md、skills/engineering/implement/SKILL.md；2026-11-06 核对；MIT，Copyright (c) 2026 Matt Pocock；精选改写，仅吸收〈动手前〉的「沿用领域词表与 ADR 的词汇」「按纵切片而非横向分层推进」与〈改动〉的「不为未出现的用法做投机扩展」、implement 的「收尾时再跑一次完整检查」判据；本批自定判据只有〈动手前〉的「验收落成可判定的结果」与其三步组织（定位约定→定可判定验收→按行为切片推进）；上游原文为英文，改写后按句自查未见与之同形；上游可取；完整许可见 `luno-coding/LICENSE.matt-pocock.txt`；登记见 skills-sources.md。 -->
<!-- 来源：obra/superpowers@22f0b463e7a5e579904dd6211a520321035526f7；路径：skills/verification-before-completion/SKILL.md；2026-11-06 核对（该文件「Core principle: Evidence before claims, always」与〈Common Failures〉「Tests pass 需 test command output，Previous run／"should pass" 不算」）；MIT，Copyright (c) 2025 Jesse Vincent；精选改写，仅吸收〈交付〉的「附结果证据…不以「应该没问题」或文件已存在代替」一句，对应上游「evidence before claims」「Previous run／『should pass』不足以证明」判据；〈改动〉三条 diff 核对判据为自有流程，不取自上游；上游原文为英文，改写后按句自查未见与之同形；上游可取；完整许可见 `luno-coding/LICENSE.obra-superpowers.txt`；登记见 skills-sources.md。 -->
<!-- 来源：mattpocock/skills@5beb35b040e3de97e54fa9e386d7e42d15c295c2；路径：skills/engineering/diagnosing-bugs/SKILL.md、skills/engineering/to-tickets/SKILL.md；2026-10-25 本地核对；MIT，Copyright (c) 2026 Matt Pocock；精选改写；完整许可见 `luno-coding/LICENSE.matt-pocock.txt`；上游在线可取性未复核。来源登记见 skills-sources.md。 -->

## 范围
跨语言的代码编写、修改、重构，以及代码审查时的实施侧核对。目标与产物量级、授权与提问、正式审查与分级、CI 与执行环境、规则仓库的测试准入，分别按 `luno-core`、`luno-review`、`luno-ops`、`luno-sync` 原文，本文不复述。

## 动手前

验收先落为可判结果（命令、预期）；多步设检查点，收尾再跑完整检查，不以中途单点代整体。定位现有构建/测试/lint入口、生成物、目录命名、词表和ADR；沿用约定，缺项如实报，不猜。

行为改动按可独立验收的纵切片贯穿实际各层，做完可演示；不按库/接口/UI横向攒齐。跨大量调用点、无法分片通过的机械重构例外：新旧并存→分批迁移→核旧调用归零→删除旧形态，各批尽量可用；不能中途通过则明确最终集成点，不把中间态报通过。

## 改动

不为未出现用法投机泛化；单次使用通常不抽象，有当前需求、安全/正确性/成文规范依据才按收益与维护成本决定。重写看能否消除重复层，不看行数。

提交前逐处核diff：①能否追溯本次目标，不能则撤回（含格式/注释/重排），必要扩动说明关系；②本次引入的无引用import/变量/函数本批清理，既有死代码只报位置及可确认替代者，另获准且确定无用才删；③沿用周边风格，安全/正确性/成文规范优先。只有证据证明不可能的内部情形才按不可能处理；外部输入、鉴权、边界和故障仍按可达路径。

## 修正与重构

修bug先复现同一症状，优先自动用例修前失败、修后转绿，不以能跑通代替。难复现/反馈慢/链复杂时记诊断命令及一次真实非秘密结果，确认失败来自故障而非初始化/权限/邻近路径；反馈环以可重复、秒级、无人值守为目标，慢/人工说明限制和替代证据，随机故障在预算内记录命中率，不冒称确定。不可复现或无框架则报缺口及最小复现/日志/前后对比，不凭未验证假设直接改代码。

修后回跑原始未缩减场景；回归边界须触发并观察真实故障，多调用方/完整链不能以单调用方或过浅测试代替，无合适接缝报缺口。重构先有通过基线，改后同组检查通过；行为变化另作需求，不混入重构。

## 交付

交实际命令、结果、未验证及原因；文件存在或“应该没问题”不代证据。
