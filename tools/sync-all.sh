#!/bin/sh
# 仅结构守卫＋包内校验；不部署、不访问生效端、不写证据回执。
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd) || exit 1
if [ "$#" -ne 0 ]; then
    echo "用法：sh tools/sync-all.sh（无平台巡检或推送参数）" >&2
    exit 2
fi
cd "$ROOT" || exit 1
python3 -B tools/check-rules.py
rc=$?
case "$rc" in 0|2) ;; *) exit "$rc" ;; esac
python3 -B - "$ROOT" <<'PY'
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]); p=root/'skills/luno-core/scripts/quick_validate.py'
spec=importlib.util.spec_from_file_location('quick_validate',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
d=json.loads((root/'tools/sync-targets.json').read_text(encoding='utf-8'))
skills=[o for o in d['objects'] if o.get('type')=='skill']
if not skills: raise SystemExit(3)
failed=False
for o in skills:
    ok,msg=m.validate_skill(str((root/o['source']).parent))
    print('[包内校验] '+o['id']+': '+msg)
    failed=failed or not ok
raise SystemExit(1 if failed else 0)
PY
vrc=$?
[ "$vrc" -eq 0 ] || exit "$vrc"
exit "$rc"
