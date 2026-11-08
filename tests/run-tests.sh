#!/bin/sh
# 用法：sh tests/run-tests.sh [smoke|full|list|group G[,G…]|case NAME|select [FILE]|select-paths|render-paths]
#   smoke＝只跑结构守卫 tools/check-rules.py（任何非零含 rc=2 提示都记 FAIL）；
#   full＝用例表第 4 列为 1 的全部入口（含 smoke）；group/case 定向运行；
#   select-paths：stdin 为 NUL 分隔的变更路径，stdout 为 selector JSON；
#   select：读取该 JSON（文件参数或 stdin），合并去重后运行。
# 变更路径→必跑套件（机器表 tests/test_paths.py；本块与 render-paths 输出须一致）：
# >>> PATHS_RULES
#   结构守卫或边登记 → gate
#   部署、正文契约、资源、打包与对象登记 → deploy
#   Surge 包或测试 → surge
#   脱敏实现与读取模板 → privacy
#   打包器与专项测试 → pack
#   署名机械检查器、其测试与署名规则 → identity
#   运行器与聚合入口 → full
# <<<
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd) || exit 1
cd "$ROOT" || exit 1

case ${1:-} in
    select-paths) exec python3 -I -B tests/test_paths.py select-paths ;;
    render-paths) exec python3 -I -B tests/test_paths.py render ;;
esac

# 名称|分组|命令|进 full
# unittest 以模块名加载：文件名带连字符，discover 找不到；整模块导入后再收集用例。
CASES='
check-rules.py|smoke|python3 -B tools/check-rules.py|1
test-check-rules.sh|gate|sh tests/test-check-rules.sh|1
test-redact.py|privacy|cd tests && python3 -B -m unittest -v test-redact|1
test-pack-skill-zip.py|pack|cd tests && python3 -B -m unittest -v test-pack-skill-zip|1
test-surge-scripts.py|surge|cd tests && python3 -B -m unittest -v test-surge-scripts|1
test-deploy-skill.py|deploy|cd tests && python3 -B -m unittest -v test-deploy-skill|1
test-commit-identities.py|identity|cd tests && python3 -B -m unittest -v test-commit-identities|0
'

mode=${1:-smoke}
arg=${2:-}
usage() { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; }

pick() {  # pick KIND [ARG]：把一个选择器展开为用例名，每行一个
    printf '%s\n' "$CASES" | while IFS='|' read -r n g c f; do
        [ -n "$n" ] || continue
        case $1 in
            smoke) [ "$g" = smoke ] ;;
            full)  [ "$f" = 1 ] ;;
            group) case ",${2:-}," in *",$g,"*) true ;; *) false ;; esac ;;
            case)  [ "$n" = "${2:-}" ] ;;
            *) false ;;
        esac && echo "$n"
    done
}

want=' '
add() {  # 选不到任何入口的选择器按用法错误处理，不当作“已跑”
    hit=$(pick "$@")
    [ -n "$hit" ] || { echo "选择器未选中任何入口：$*" >&2; exit 2; }
    for n in $hit; do
        case $want in *" $n "*) ;; *) want="$want$n " ;; esac
    done
}

case $mode in
    smoke|full) add "$mode" ;;
    group|case) [ -n "$arg" ] || { usage >&2; exit 2; }; add "$mode" "$arg" ;;
    select)
        sels=$( { if [ -n "$arg" ]; then cat -- "$arg"; else cat; fi; } | python3 -I -B -c '
import json, re, sys
try:
    doc = json.load(sys.stdin)
except ValueError:
    doc = None
arity = {"smoke": 1, "full": 1, "group": 2, "case": 2}
ok = isinstance(doc, list) and doc and all(
    isinstance(s, list) and s and s[0] in arity and len(s) == arity[s[0]]
    and all(isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_.,-]+", x) for x in s)
    for s in doc)
if not ok:
    sys.exit("select：selector JSON 不合法（须为 [[\"full\"|\"smoke\"] 或 [\"group\"|\"case\", 名称] …]）")
print("\n".join(" ".join(s) for s in doc))
') || exit 2
        while read -r k a; do add "$k" ${a:+"$a"}; done <<EOF
$sels
EOF
        ;;
    list)
        printf '%s\n' "$CASES" | while IFS='|' read -r n g c f; do
            [ -n "$n" ] && printf '%-28s %-9s %s\n' "$n" "$g" "$([ "$f" = 1 ] && echo full)"
        done
        exit 0 ;;
    -h|--help|help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

WORK=$(mktemp -d "${TMPDIR:-/tmp}/run-tests.XXXXXX") || exit 1
trap 'rm -rf "$WORK"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$WORK/home" "$WORK/tmp" || exit 1

# 子进程只拿白名单环境：独占 HOME/TMPDIR（不读用户 git/gpg 配置、不写调用方目录），
# 调用方其余变量（PYTHONPATH 等）一律不进入；stdin 固定 /dev/null，不吞调度输入。
clean() {
    env -i PATH="$PATH" HOME="$WORK/home" TMPDIR="$WORK/tmp" LANG=C.UTF-8 LC_ALL=C.UTF-8 \
        PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 TZ=UTC sh -c "$1" < /dev/null
}
cut120() { LC_ALL=C.UTF-8 sed 's/^\(.\{0,120\}\).*/    | \1/'; }

pass=0; fail=0; t_all=$(date +%s)
echo "---- 运行：$mode${arg:+ $arg} →$want----"
printf '%s\n' "$CASES" > "$WORK/cases"
while IFS='|' read -r name grp cmd full; do
    case $want in *" $name "*) ;; *) continue ;; esac
    printf '%-28s ' "$name"
    t0=$(date +%s)
    clean "$cmd" > "$WORK/log" 2>&1
    rc=$?
    t=$(( $(date +%s) - t0 ))
    if [ "$rc" = 0 ]; then
        echo "PASS ${t}s  $(tail -n 1 "$WORK/log")"
        pass=$((pass+1))
    else
        echo "FAIL ${t}s rc=$rc"
        { grep -E '^(FAIL|ERROR)[: ]' "$WORK/log" | head -n 10; tail -n 3 "$WORK/log"; } | cut120
        fail=$((fail+1))
    fi
done < "$WORK/cases"

echo "---- ${mode}：PASS $pass / FAIL $fail ｜ $(( $(date +%s) - t_all ))s ----"
[ "$fail" = 0 ] && [ "$pass" -gt 0 ]
