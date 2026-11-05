#!/bin/sh
# B+ 档运行器：smoke=规则文本守卫；full=smoke+六个登记测试入口；group/case 为定向回归。
# 用法：sh tests/run-tests.sh [smoke|full|group deploy,surge,privacy,gate,pack,identity|case NAME|list]
# select-paths：stdin 为 NUL 分隔变更路径，stdout 为 selector JSON；select：读取该 JSON 去重执行。
# 规则正文机械守卫保留；纯正文只跑 smoke，测试不能替代独立语义审查及逐端回读。
# 变更路径→必跑套件的唯一机器表为 tests/test_paths.py；同表渲染：
# >>> PATHS_RULES 渲染块（勿手改；改机器表后重跑 render-paths）
#   结构守卫或边登记 → gate
#   部署、正文契约、资源、打包与对象登记 → deploy
#   Surge 包或测试 → surge
#   脱敏实现与读取模板 → privacy
#   打包器与专项测试 → pack
#   署名机械检查器、其测试与署名规则 → identity
#   运行器与聚合入口 → full
# <<<
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1

# ── 白名单环境执行（F2 环境隔离的唯一实现）──────────────────────────────────
# 所有**测试代码入口**一律经此执行（含 `select-paths`／`render-paths` 这类只读 Python 入口与
#   `select` 的 selector 解析）：`env -i` 起一个**核定白名单**环境，只给 PATH／HOME／TMPDIR／
#   locale／Python 输出编码——调用方环境整体不继承。故 `SELFTEST_LIMIT`／`SELFTEST_UNIT_FAIL`
#   （控制变量）、`RT_CHECK_RULES_FULL_LOG`／`RT_CHECK_RULES_FULL_RC`（伪造复用日志）、
#   `PYTHONPATH`、`HOME` 下配置与调用方 `TMPDIR` 都不能进入测试进程。PATH 固定为可信系统路径，
#   HOME／TMPDIR 由调用点给定：执行循环用本轮临时目录下的独占子目录，只读出口用不可作为目录的
#   `/dev/null`（不建目录，故不依赖调用方 TMPDIR 是否可用）。
#   **边界**：这是执行环境隔离与防假绿，**不是**秘密过滤——用例仍按离线白名单夹具编写。
rt_env() {  # rt_env <命令…>：白名单环境直接执行（不经 shell 拼串；stdin 原样透传）
    env -i PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin \
        HOME="$RT_HOME" TMPDIR="$RT_TMP" LANG=C.UTF-8 LC_ALL=C.UTF-8 \
        PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 TZ=UTC "$@"
}

# 只读出口：**不创建任何临时目录**（生产入口每次调用都走这里）：调用方 `TMPDIR` 不存在或
#   不能作为目录时，只读选路原本可直接成功，不得因为要建夹具沙箱而变成 `exit 1`（F2 兼容性）。
#   但**仍走白名单环境**：入口选路与 render 也是测试代码，调用方 `PYTHONPATH`（可影子标准库）等
#   不得进入。故 HOME／TMPDIR 固定为 `/dev/null`（不可作为目录，核实际可用）：被测进程无从写入，
#   等价于「无可用 HOME／TMPDIR」，无需创建、无残留；stdin 原样透传（select-paths 读 stdin），
#   退出码原样传递。
case ${1:-} in
    select-paths|render-paths)
        RT_HOME=/dev/null
        RT_TMP=/dev/null
        _paths_mode=render
        [ "$1" = select-paths ] && _paths_mode=select-paths
        rt_env python3 "$ROOT/tests/test_paths.py" "$_paths_mode"
        exit $?
        ;;
esac

# 夹具与日志使用唯一临时目录；尊重调用方 TMPDIR，不碰共享 /tmp/rt-*。
WORK=$(mktemp -d "${TMPDIR:-/tmp}/run-tests.XXXXXXXX") || exit 1
trap 'rm -rf -- "$WORK"' EXIT

# RT_KEEP_LOGS（失败日志留存）：只接受**调用方给出的已存在绝对路径目录**——本脚本不创建、
#   不推断该目录（授权落点由调用方决定）。子目录按轮**懒建一次**并用 mktemp 取唯一名，
#   因此重复运行不会覆盖上一轮日志，也不会因文件名固定而互相踩踏。相对路径一律拒绝：
#   脚本会 cd 到仓库根，相对路径在 cd 前后含义不同（旧实现按原样拼接，实际落点与预期不符）。
#   定位是**尽力留存**，不是可靠归档：不校验复制完整性、不保证持久性/容量、复制失败只报告；
#   需要可靠留证时由调用方自行在受控目录做归档与校验。
RT_KEEP_BASE=""
RT_KEEP_DIR=""
if [ -n "${RT_KEEP_LOGS:-}" ]; then
    case $RT_KEEP_LOGS in
        /*) if [ -d "$RT_KEEP_LOGS" ] && [ ! -L "$RT_KEEP_LOGS" ]; then
                RT_KEEP_BASE=$RT_KEEP_LOGS
            else
                echo "RT_KEEP_LOGS=$RT_KEEP_LOGS：不是已存在的目录（须为已存在的绝对路径目录），本次不保留失败日志" >&2
            fi ;;
        *) echo "RT_KEEP_LOGS=$RT_KEEP_LOGS：拒绝相对路径（脚本会 cd 到仓库根，含义会变）；请给绝对路径，本次不保留失败日志" >&2 ;;
    esac
fi
trap 'exit 130' INT
trap 'exit 143' TERM

# ── 子进程环境（F2 环境隔离）────────────────────────────────────────────────
# 所有测试代码入口（含 RT_LINT 直跑的 check-rules.py）一律经 `rt_run` 执行：`env -i` 起一个
#   **核定白名单**环境，只给下列变量——调用方环境整体不继承，故：
#     · `SELFTEST_LIMIT`／`SELFTEST_UNIT_FAIL` 无法从外部注入（注入开关只能由用例命令行自带）；
#     · `RT_CHECK_RULES_FULL_LOG`／`RT_CHECK_RULES_FULL_RC` 外部同名无效：只由本调度器用
#       **本轮自产**的 `$WORK/rt-*.log`／`.rc` 设定（见执行循环复用块），不读调用方值；
#     · 合成秘密变量、`PYTHONPATH`、`HOME` 下配置、调用方 `TMPDIR` 均不进入测试进程。
#   PATH 固定为可信系统路径（不取调用方 PATH）；HOME／TMPDIR 是本轮临时目录下的独占子目录，
#   被测进程写 HOME 或临时文件不互相踩踏，也不落到调用方或共享目录。
#   **边界**：这是执行环境隔离与防假绿，**不是**秘密过滤——用例仍按离线白名单夹具编写，
#   不得把该包装当作可以承载生产凭据的通道。
RT_HOME="$WORK/home"
RT_TMP="$WORK/tmp"
mkdir -p "$RT_HOME" "$RT_TMP" || exit 1
RT_CHILD_LOG=""
RT_CHILD_RC=""
rt_run() {  # rt_run <shell 命令>：白名单环境执行；复用日志变量仅由本调度器设定
    if [ -n "$RT_CHILD_LOG" ]; then
        env -i PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin \
            HOME="$RT_HOME" TMPDIR="$RT_TMP" LANG=C.UTF-8 LC_ALL=C.UTF-8 \
            PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 TZ=UTC \
            RT_CHECK_RULES_FULL_LOG="$RT_CHILD_LOG" RT_CHECK_RULES_FULL_RC="$RT_CHILD_RC" \
            sh -c "$1"
    else
        env -i PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin \
            HOME="$RT_HOME" TMPDIR="$RT_TMP" LANG=C.UTF-8 LC_ALL=C.UTF-8 \
            PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 TZ=UTC \
            sh -c "$1"
    fi
}

# 调用方环境里的自检注入开关**一律不生效**（见执行循环的环境隔离注释）：显式告知，
#   避免调用方误以为已注入／已被截断（尤其别把「截断跑」当成 gate 已覆盖全部用例）。
if [ -n "${SELFTEST_LIMIT:-}" ] || [ -n "${SELFTEST_UNIT_FAIL:-}" ]; then
    echo "注意：调用方环境设置了 SELFTEST_LIMIT／SELFTEST_UNIT_FAIL，本运行器不向用例传递（防假绿）" >&2
fi

# 用例表：<名称>|<分组>|<命令>|<smoke?>|<常跑?>
#   慢项各自成组，不与常用组混装：`gate`＝R-1 反例＋驱动自检（组级耗时随环境波动，不设固定值）；
#   `meta` 只留正文口径／当前态契约等快项。
#   第 5 列「常跑」＝是否进 `full`。0 表示**退出常跑**，留作对应实现变更时的定向回归，
#   用 `group <组名>` 或 `case <名称>` 按需运行（2026-10-06 缩减：常跑只留同步链必需项）。
# 入口形态（2026-10-06「标准运行器拥有测试入口」批）：**unittest 用例一律以标准模块加载执行**
#   `(cd tests && python3 -B -m unittest -v <模块名>)`。标准运行器因此拥有入口——模块先被完整
#   导入，`if __name__ == '__main__'` 入口块**之后**定义的测试类、继承类与动态附加方法在加载时
#   已存在，从执行路径上消除「入口提前终止 → 后面的测试类还没定义 → 套件仍报 OK（假绿）」。
#   **不用 `discover`**：标准库发现规则按模块名（标识符）匹配，会跳过仓库里带连字符的文件名，
#   故必须显式给出模块名。自制 Python 检查脚本与 shell 用例保持**直接执行**（本就不是 unittest 模块）。
CASES='
test-surge-scripts.py|surge|(cd tests && python3 -B -m unittest -v test-surge-scripts)|0|1
test-redact.py|privacy|(cd tests && python3 -B -m unittest -v test-redact)|0|1
test-check-rules.sh|gate|sh tests/test-check-rules.sh|0|1
test-check-rules-driver.sh|gate|sh tests/test-check-rules-driver.sh|0|1
test-deploy-skill.py|deploy|(cd tests && python3 -B -m unittest -v test-deploy-skill)|0|1
test-pack-skill-zip.py|pack|(cd tests && python3 -B -m unittest -v test-pack-skill-zip)|0|1
test-commit-identities.py|identity|(cd tests && python3 -B -m unittest -v test-commit-identities)|0|0
'

# 变更路径→必跑套件：**唯一机器表在 `tests/test_paths.py`**（`PATHS_RULES`，唯一持有者与实现）。
#   本调度器暴露 `select-paths`（stdin＝NUL 分隔路径，输出选择器 JSON）和
#   `render-paths`（输出表的说明行）；其它消费者经此接口取表，不自持第二份映射。

mode=${1:-smoke}
sel=${2:-}
pass=0; fail=0; ran=0; skip=0
t_all=$(date +%s)

usage() {
    sed -n '2,60p' "$0" | sed 's/^# \{0,1\}//'
}

case "$mode" in
    list)
        printf '%-32s %-8s %-8s %s\n' "用例" "分组" "在 smoke" "常跑（进 full）"
        printf '%s\n' "$CASES" | while IFS='|' read -r n g c s f; do
            [ -z "$n" ] && continue
            printf '%-32s %-8s %-8s %s\n' "$n" "$g" "$([ "$s" = 1 ] && echo 是 || echo 否)" \
                "$([ "$f" = 1 ] && echo 是 || echo 否)"
        done
        exit 0 ;;
    smoke)
        sel="" ;;
    full)
        sel="*" ;;
    group)
        [ -z "$sel" ] && { echo "group 需要分组名，如 group gate" >&2; usage; exit 2; } ;;
    case)
        [ -z "$sel" ] && { echo "case 需要用例名" >&2; usage; exit 2; } ;;
    select)
        : ;;                            # 第 2 参数（可选）＝ argv JSON 文件；缺省读 stdin
    -h|--help|help)
        usage; exit 0 ;;
    *)
        echo "未知模式：$mode" >&2; usage; exit 2 ;;
esac

# ── select 模式：selector → argv JSON 归一（`<raw selector JSON>|<扁平 kind|arg>`）─────
#   账本口径：每个 selector **原样保留**，其成员逐条记录；同一入口只真跑一次（首次出现优先）。
SELECT_MODE=0
if [ "$mode" = select ]; then
    SELECT_MODE=1
    # selector 解析同样是**测试代码**（Python），经 `rt_env` 白名单环境执行（F2）：
    #   调用方 `PYTHONPATH` 可影子标准库模块，`SELFTEST_*`／伪造复用日志变量等都不得进入。
    #   stdin 仍是选集输入（经管道原样透传），与执行循环里的 `< /dev/null` 互不影响。
    RT_SELECT_PY='
import json, sys
doc = json.load(sys.stdin)
if not isinstance(doc, list) or not all(isinstance(a, list) and a for a in doc):
    sys.stderr.write("select：argv JSON 形态不合法（须为 [["<kind>","<arg>"...]]）\n")
    sys.exit(2)
for a in doc:
    raw = json.dumps(a, ensure_ascii=False)
    if "|" in raw:
        sys.stderr.write("select：selector 含保留分隔符「|」：%s\n" % raw)
        sys.exit(2)
    sys.stdout.write(raw + "|" + "|".join(str(x) for x in a) + "\n")
'
    if [ -n "$sel" ]; then cat "$sel"; else cat; fi \
        | rt_env python3 -c "$RT_SELECT_PY" > "$WORK"/rt-selectors || exit 2
    [ -s "$WORK"/rt-selectors ] || { echo "select：没有 selector（空 argv）" >&2; exit 2; }
    : > "$WORK"/rt-ledger
fi

# lint 前置：check-rules 直跑（所有模式的公共底线；select 模式下由 full／smoke selector 触发）
RT_LINT=0
case "$mode" in smoke|full) RT_LINT=1 ;; esac
if [ "$SELECT_MODE" = 1 ] && grep -Eq '^\["(full|smoke)"' "$WORK"/rt-selectors; then RT_LINT=1; fi
: > "$WORK"/rt-selected
if [ "$RT_LINT" = 1 ]; then
    printf '%s\n' 'check-rules.py' >> "$WORK"/rt-selected
    printf '%-34s ' "check-rules.py（直跑）"
    if rt_run 'python3 tools/check-rules.py' > "$WORK"/rt-lint.log 2>&1; then
        echo "PASS  $(tail -1 "$WORK"/rt-lint.log | cut -c1-40)"; pass=$((pass+1))
    else
        echo "FAIL  $(tail -2 "$WORK"/rt-lint.log | head -1 | cut -c1-60)"; fail=$((fail+1))
    fi
    ran=$((ran+1))
    printf '%s' 'completed' > "$WORK/rt-check-rules.py.rc"
fi

# 选择用例："$WORK"/rt-cases 存表，"$WORK"/rt-run 存本轮要跑的命令
printf '%s\n' "$CASES" | grep -v '^$' > "$WORK"/rt-cases
: > "$WORK"/rt-run
if [ "$SELECT_MODE" = 1 ]; then
    # 展开去重：同一入口在本轮只入队一次（`rt-selected` 兼作去重键），并逐 selector 记账本。
    rt_add() {   # rt_add <入口名> <命令> <selector 原样 JSON>
        if [ -f "$WORK/rt-$1.rc" ] || grep -Fqx "$1" "$WORK"/rt-selected; then
            printf '%s|%s\n' "$1" "$3" >> "$WORK"/rt-ledger
            return 0
        fi
        printf '%s|%s\n' "$1" "$2" >> "$WORK"/rt-run
        printf '%s\n' "$1" >> "$WORK"/rt-selected
        printf '%s|%s\n' "$1" "$3" >> "$WORK"/rt-ledger
        ran=$((ran+1))
    }
    while IFS='|' read -r raw flat; do
        kind=${flat%%|*}
        arg=${flat#*|}
        [ "$arg" = "$flat" ] && arg=""
        case "$kind" in
            full)
                rt_add "check-rules.py" "" "$raw"
                while IFS='|' read -r n g c s f; do
                    [ -z "$n" ] && continue
                    [ "$f" = 1 ] && rt_add "$n" "$c" "$raw"
                done < "$WORK"/rt-cases ;;
            smoke) rt_add "check-rules.py" "" "$raw" ;;
            group)
                while IFS='|' read -r n g c s f; do
                    [ -z "$n" ] && continue
                    case ",$arg," in *",$g,"*) rt_add "$n" "$c" "$raw" ;; esac
                done < "$WORK"/rt-cases ;;
            case)
                while IFS='|' read -r n g c s f; do
                    [ "$n" = "$arg" ] && rt_add "$n" "$c" "$raw"
                done < "$WORK"/rt-cases ;;
            *) echo "select：不认识的 selector：$raw" >&2; exit 2 ;;
        esac
    done < "$WORK"/rt-selectors
else
while IFS='|' read -r name grp cmd smoke_ok full_ok; do
    want=0
    case "$mode" in
        full)  [ "$full_ok" = 1 ] && want=1 ;;
        smoke) [ "$smoke_ok" = 1 ] && want=1 ;;
        case)  [ "$name" = "$sel" ] && want=1 ;;
        group) case ",$sel," in *",$grp,"*) want=1 ;; esac ;;
    esac
    if [ "$want" = 1 ]; then
        echo "$name|$cmd" >> "$WORK"/rt-run
        printf '%s\n' "$name" >> "$WORK"/rt-selected
        ran=$((ran+1))
    else
        skip=$((skip+1))
    fi
done < "$WORK"/rt-cases
fi

if [ "$ran" = 0 ]; then
    echo "没有选中任何用例（mode=$mode sel=${sel:-}）" >&2; exit 2
fi

echo "---- 运行 $ran 个用例（模式 $mode${sel:+：$sel}；跳过 $skip）----"
while IFS='|' read -r name cmd; do
    printf '%-34s ' "$name"
    t0=$(date +%s)
    # 用例间复用（2026-10-04）：驱动自检不再自己整跑一遍 test-check-rules.sh，改为复用**本轮**
    # 已跑过的同一次完整输出（输出与退出码经白名单环境变量传入；用例顺序上它排在前面）。
    # F2：来源只由本调度器从 `$WORK` 下**本轮自产**的 `rt-*.log`／`.rc` 取，调用方同名变量经
    #   `env -i` 已被丢弃；拿不到时驱动自检自行回退整跑一次，判据不变（见 tests/test-check-rules-driver.sh）。
    RT_CHILD_LOG=""
    RT_CHILD_RC=""
    if [ "$name" = test-check-rules-driver.sh ] \
            && [ -f "$WORK/rt-test-check-rules.sh.log" ] \
            && [ -f "$WORK/rt-test-check-rules.sh.rc" ]; then
        RT_CHILD_LOG="$WORK/rt-test-check-rules.sh.log"
        RT_CHILD_RC=$(cat "$WORK/rt-test-check-rules.sh.rc")
    fi
    # 子进程 stdin 固定 /dev/null：与「选集输入」彻底分离。否则被测进程读到循环的余下调度行，
    #   会把后续入口整段吃掉（2026-10-12 实跑复现：选 2／跑 1／rc0，后一个入口根本没跑）。
    # 环境（F2）：经 `rt_run` 的白名单环境执行，**不继承调用方环境**。
    #   实测复现（修前）：`SELFTEST_LIMIT=2 sh -c "sh tests/test-check-rules.sh"` 只跑 2 个用例组却退出 0
    #   （完整跑 PASS 44），继承后 gate 会打印 PASS ⇒ 假绿；`SELFTEST_UNIT_FAIL` 同理会凭空注入失败；
    #   外部 `RT_CHECK_RULES_FULL_LOG` 指向伪造日志时，驱动自检会把伪造结果当本轮结果。
    rt_run "$cmd" < /dev/null > "$WORK/rt-$name.log" 2>&1
    rc=$?
    printf '%s' "$rc" > "$WORK/rt-$name.rc"
    if [ "$rc" = 0 ]; then
        echo "PASS  $(( $(date +%s)-t0 ))s rc=$rc  $(tail -1 "$WORK/rt-$name.log" | cut -c1-34)"
        pass=$((pass+1))
    elif [ "$rc" = 77 ]; then
        echo "未测  $(( $(date +%s)-t0 ))s rc=77（不计 PASS）"
        fail=$((fail+1))
    else
        echo "FAIL  $(( $(date +%s)-t0 ))s rc=$rc  $(grep -m1 -E 'FAIL' "$WORK/rt-$name.log" | cut -c1-60)"
        # 失败时给**有界**的错误尾段：夹具随 EXIT 清理，只看 FAIL 行会丢掉堆栈。
        # 取日志**末端** 5 行——Python 的 Traceback 末端就是最终异常类型与消息；不再取
        # Traceback 起前 8 行（那通常只有调用帧，看不到最终异常）。
        # 行宽按**字符**截断：仅在本轮实测的实现／locale（BusyBox sed 1.37.0 + UTF-8
        # locale，`.` 按字符匹配）下成立；**不保证**其他 sed 实现或 C/POSIX locale（彼时
        # 按字节，多字节字符会被切成半个）。不用 BusyBox `cut -c`／awk substr（实测按字节）。
        # 注意：「有界」只是可读性上限，**不等于秘密过滤**；此处日志来自白名单、无凭据的
        # 离线用例，不得据此认为该函数可用于承载含秘密的日志。
        tail -n 5 "$WORK/rt-$name.log" | sed 's/^\(.\{0,120\}\).*/      | \1/'
        if [ -n "$RT_KEEP_BASE" ]; then
            if [ -z "$RT_KEEP_DIR" ]; then
                RT_KEEP_DIR=$(mktemp -d "$RT_KEEP_BASE/rt-logs.XXXXXXXX") || RT_KEEP_DIR=""
                if [ -z "$RT_KEEP_DIR" ]; then
                    echo "      | 失败日志**未保留**：无法在 $RT_KEEP_BASE 下创建唯一子目录"
                fi
            fi
            if [ -n "$RT_KEEP_DIR" ]; then
                if cp -- "$WORK/rt-$name.log" "$RT_KEEP_DIR/rt-$name.log"; then
                    echo "      | 失败日志已保留：$RT_KEEP_DIR/rt-$name.log（尽力留存，未校验完整性，非可靠归档）"
                else
                    echo "      | 失败日志**未保留**：复制到 $RT_KEEP_DIR 失败（原件随临时目录在 EXIT 时删除）"
                fi
            fi
        fi
        fail=$((fail+1))
    fi
done < "$WORK"/rt-run

# 选中集 vs 实跑集：逐条核每个被选中的入口都留下了 rc 记录。子进程吞掉选集输入、入口提前
#   退出或调度中断，都会让后面的入口根本没跑——只数 PASS 会把它判成绿。任一缺失即非零。
#   记录写在 $WORK/rt-selected 与 $WORK/rt-executed（本轮实际执行的 ID 集合）。
: > "$WORK"/rt-executed
missing=""
while IFS= read -r name; do
    if [ -f "$WORK/rt-$name.rc" ]; then
        printf '%s\n' "$name" >> "$WORK"/rt-executed
    else
        missing="$missing $name"
    fi
done < "$WORK"/rt-selected
executed=$(grep -c . "$WORK"/rt-executed)
echo "---- 选中 $ran · 实跑 $executed ----"
if [ -n "$missing" ]; then
    echo "选中但未执行：$missing —— 调度器 stdin 未隔离或入口提前退出，判失败（不得只数 PASS）" >&2
    fail=$((fail+1))
fi

# selector 账本：逐 selector 证明「其全部成员都已执行且结果齐备」（selector 原样保留）。
if [ "$SELECT_MODE" = 1 ]; then
    echo "---- selector 账本（selector · 成员 · 实跑）----"
    : > "$WORK"/rt-receipt
    while IFS='|' read -r raw flat; do
        _tot=0; _ok=0; _miss=""; _seen=""
        while IFS='|' read -r _m _s; do
            [ "$_s" = "$raw" ] || continue
            case " $_seen " in *" $_m "*) continue ;; esac     # 同一 selector 内成员按名去重
            _seen="$_seen $_m"
            _tot=$((_tot+1))
            if [ -f "$WORK/rt-$_m.rc" ]; then _ok=$((_ok+1)); else _miss="$_miss $_m"; fi
        done < "$WORK"/rt-ledger
        if [ "$_tot" = 0 ]; then
            echo "  $raw → 成员 0（空 selector，不得当已执行）"
            fail=$((fail+1))
        else
            echo "  $raw → 成员 $_tot · 实跑 $_ok${_miss:+ · 缺：$_miss}"
            [ -n "$_miss" ] && fail=$((fail+1))
        fi
        printf '%s|%s|%s\n' "$raw" "$_tot" "$_ok$_miss" >> "$WORK"/rt-receipt
    done < "$WORK"/rt-selectors
    if [ -n "${RT_RECEIPT:-}" ]; then
        case $RT_RECEIPT in
            /*) if cat "$WORK"/rt-receipt > "$RT_RECEIPT" 2>/dev/null; then
                    echo "      | 回执已写：$RT_RECEIPT（逐 selector 成员/实跑，竖线分隔）"
                else
                    echo "      | 回执**未写**：$RT_RECEIPT 不可写（回执非可靠归档，仍以账本为准）"
                    fail=$((fail+1))
                fi ;;
            *) echo "      | 回执**未写**：RT_RECEIPT=$RT_RECEIPT 须为绝对路径" >&2
               fail=$((fail+1)) ;;
        esac
    fi
fi

echo "---- 分层测试（$mode）：PASS $pass / FAIL $fail ｜ 总耗时 $(( $(date +%s)-t_all ))s ----"
[ "$fail" = 0 ]
