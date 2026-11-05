#!/bin/sh
# test-check-rules-driver.sh —— 回归测试**驱动自身**的自检（P3，2026-09-18）
#
# 用途：`tests/test-check-rules.sh` 会打印 PASS/FAIL 汇总，但「打印 FAIL、退出码却是 0」
#       是脚本类门禁的经典失效形态（LENS 审查项 1）。本脚本验证失败确实传播为整体非零。
#
# 用法：sh tests/test-check-rules-driver.sh   # 自检通过退出 0
#
# 做法：①取一次完整跑的输出与退出码，要求退出 0、含最终汇总、汇总位于末行；
#       ②注入 SELFTEST_UNIT_FAIL=1（让脚本末尾追加一条注定失败的断言），要求整体退出非 0
#       且输出含 FAIL。两次都不改工作区。
#
# 成本（2026-09-18 首轮）：②用 SELFTEST_LIMIT=3 **只跑前 3 个用例组**——传播点（注入失败 →
#   汇总 → 失败退出）与完整跑是同一段代码，故无需整套跑第二遍（原实现白花约 164 s）。
#   为防止「截断被静默忽略」掩盖成本问题，另加反空转断言：截断后 PASS 数必须小于完整跑。
#
# 成本（2026-10-04 二轮，本文件）：①也不再自己整跑一遍 `tests/test-check-rules.sh`。
#   由 `tests/run-tests.sh` 在同一轮里**已经跑过**的那次完整跑，把它的输出与退出码经
#   `RT_CHECK_RULES_FULL_LOG`／`RT_CHECK_RULES_FULL_RC` 传进来复用——是**同一次真实执行**
#   的数据，判据（rc=0／含汇总／汇总在末行）一条不减、不放宽，只是不再重复执行。
#   独立运行（没有这两个变量，例如直接 `sh tests/test-check-rules-driver.sh`，或
#   `sh tests/run-tests.sh case test-check-rules-driver.sh`）时回退为自己整跑一次，
#   语义与旧实现完全相同——**不得**把「拿不到复用输出」当成跳过断言的理由。
#   判据（①的退出码传播、②的注入失败传播、③的截断未空转）与用例数均不变。
#   2026-10-15：截断分支亦跳过后置辅助专项；完整跑仍执行全部专项，
#   本驱动只复用该完整跑的实际输出，注入仍走原失败传播和收尾。
#
# 本批记录（候选 pr-migration-c6240521，2026-10-12）：本文件**未改动**——
#   ① 的直接对象 `tests/test-check-rules.sh` 本批修好（扫描面变体锚点随 `check-rules.py`
#   的 `SCAN_TOP` 新增 `AGENTS.md` 同步；最小树夹具同步删 `AGENTS.md`），该套件由 rc=1
#   恢复为 rc=0 后，本文件 7 项断言随之全绿。**无删除、无新增判据**，无活动能力损失：
#   本文件只证「失败是否传播为整体非零」，与锚点取值无关。
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
pass=0; fail=0

chk() {   # chk <用例名> <期望条件> <实得值> <期望值>
    if [ "$3" = "$4" ]; then
        echo "PASS  $1（实得 $3）"; pass=$((pass+1))
    else
        echo "FAIL  $1（期望 $4，实得 $3）"; fail=$((fail+1))
    fi
}

# ① 完整跑：优先复用本轮 run-tests.sh 已跑过的同一份输出；否则自己跑一次。
if [ -n "${RT_CHECK_RULES_FULL_LOG:-}" ] && [ -f "$RT_CHECK_RULES_FULL_LOG" ] \
        && [ -n "${RT_CHECK_RULES_FULL_RC:-}" ]; then
    out=$(cat "$RT_CHECK_RULES_FULL_LOG"); rc=$RT_CHECK_RULES_FULL_RC
    echo "（复用本轮 test-check-rules.sh 的完整跑：$RT_CHECK_RULES_FULL_LOG，rc=$rc）"
else
    out=$(cd "$ROOT" && sh tests/test-check-rules.sh 2>&1); rc=$?
    echo "（独立运行：本脚本自行整跑 tests/test-check-rules.sh，rc=$rc）"
fi
chk "正常跑：整体退出码" "" "$rc" "0"
if printf '%s' "$out" | grep -qF -- "---- R-1 反例回归："; then
    echo "PASS  正常跑：输出含最终汇总"; pass=$((pass+1))
else
    echo "FAIL  正常跑：缺少最终汇总行"; fail=$((fail+1))
fi
# 汇总行必须位于**全部**用例之后：用末行判定，避免中途汇总的假绿
last=$(printf '%s' "$out" | tail -1)
case "$last" in
    *"R-1 反例回归"*) echo "PASS  汇总位于全部用例之后"; pass=$((pass+1)) ;;
    *) echo "FAIL  汇总不在末行（末行：$last）"; fail=$((fail+1)) ;;
esac

out2=$(cd "$ROOT" && SELFTEST_UNIT_FAIL=1 SELFTEST_LIMIT=3 sh tests/test-check-rules.sh 2>&1); rc2=$?
chk "注入失败：整体退出码非 0" "" "$rc2" "1"
if printf '%s' "$out2" | grep -qF "驱动自检（故意失败"; then
    echo "PASS  注入失败：命中自检用例"; pass=$((pass+1))
else
    echo "FAIL  注入失败：未命中自检用例"; fail=$((fail+1))
fi
if printf '%s' "$out2" | grep -qF "SELFTEST_LIMIT=3"; then
    echo "PASS  截断生效：输出含截断标记"; pass=$((pass+1))
else
    echo "FAIL  截断生效：未见到截断标记（SELFTEST_LIMIT 可能被忽略）"; fail=$((fail+1))
fi
# 反空转：截断后 PASS 数必须**严格小于**完整跑，否则说明仍在跑满整套（成本回落且本用例失去意义）
n_full=$(printf '%s' "$out"  | sed -n 's/.*PASS \([0-9][0-9]*\) \/ FAIL [0-9][0-9]*.*/\1/p' | tail -1)
n_lim=$(printf '%s' "$out2" | sed -n 's/.*PASS \([0-9][0-9]*\) \/ FAIL [0-9][0-9]*.*/\1/p' | tail -1)
if [ -n "$n_full" ] && [ -n "$n_lim" ] && [ "$n_lim" -lt "$n_full" ]; then
    echo "PASS  截断未空转（截断跑 PASS=$n_lim < 完整跑 PASS=$n_full）"; pass=$((pass+1))
else
    echo "FAIL  截断未空转（完整 PASS=${n_full:-?}，截断 PASS=${n_lim:-?}）"; fail=$((fail+1))
fi

echo "---- 驱动自检：PASS $pass / FAIL $fail ----"
[ "$fail" = 0 ]
