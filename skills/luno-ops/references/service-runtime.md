# 共读资源（按原分支合并）

指针中的“分支”以 branch 锚点及 BEGIN/END 注释定界。沿用各分支原有触发和共同前置：完整读取命中的分支；原规则指定分节时，读取指定完整分节及共同前置，不加载未命中分支。同一文件的命中并集优先一次取齐，返回受限时分块补齐，不以截断内容作已加载。

分支内的“本文件”“本文”“本资源”均只指该分支，不把其他分支的接口事实、版本、能力或权限并入；“本技能”仍指原技能。主体、条件、例外、停止、恢复和许可边界保持原文，不因合并授予额外权限。跨技能先读目标技能入口及产品/业务入口；候选不改变现役规则。

分支：service-runtime、remote-files-backup、ssh。

<a id="branch-service-runtime"></a>
<!-- BEGIN service-runtime -->
# 服务运行与排障

## 服务排障

- **先认托管方式**：确认服务由 systemd、PM2 还是 Compose 托管，再按症状归类：配置错误、依赖缺失、权限拒绝、端口占用、上游不可达、DNS 不匹配。各类取不同的证据，不混在一起试。
- **取证有界**：状态一次取全；日志用 `-n`、`--tail` 或 `--since` 限定窗口，**默认不跟随输出（不用 `-f`）**；端口归属用 `ss -ltnp`；路径权限用 `namei -l` 逐级看，分清属主、组和其他人的执行位。
- **Web 请求逐跳核对**：应用是否在监听 → Nginx 是否反代到这个监听 → DNS 是否指向这台主机 → TLS 是否由预期的证书提供，每一跳记下结论。末端 502 不等于 `proxy_pass` 写错了，不能据此直接改配置。
- **校验和生效分开**：配置先通过 `nginx -t` 才 reload；`restart` 和 `reload` 语义不同，不能互相代替。凡是让改动生效的命令都算变更，按本技能〈安全与测试〉确认后执行。
- **最小闭环**：最小改动 → 分项验证 → 通过就收口。只有验证失败或命中事先约定的回滚判据时才回滚，并且限在既有授权内（需要用改前备份时，先读 `references/service-runtime.md`〔分支 remote-files-backup〕 的〈备份〉）。同一现象两次没有新进展、需要扩权或越界、证据不足时停下报告缺口；「没有进展」指的是**这条路径**取不到新证据，授权允许时可以换另一条有依据的路径。
- **读环境和配置只取声明的键**：只核声明的指定键是否存在和长度，不取全量再脱敏。
  - 容器或主机环境：按声明的指定键，在容器内只输出键名、长度和是否已设值，如 `docker exec <容器> sh -c 'for k in "$@"; do eval "v=\${$k}"; printf "%s len=%s state=%s\n" "$k" "${#v}" "$([ -n "$v" ] && echo set || echo unset)"; done' sh API_KEY DB_PASSWORD`
  - 普通的非凭据配置文件或 env 文件，只列键名 `awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $1}' <文件>`，或只取声明的指定键的长度 `awk -F= '$1=="KEY"{print $1, length(substr($0,index($0,"=")+1))}' <文件>`（按第一个 `=` 之后的整段计长，值里含 `=` 也不会算错）。
  - **已确认不含凭据的 JSON 配置**，用目标上已有的工具（新安装另行确认）按逐个声明的字段路径投影：`jq '{port: .server.port, log_level: .logging.level}' <文件>`。
  - 凭据 env 文件不由助手解析取值，只通过配置持有方已有的投影接口核验（如 `docker compose config --quiet` 只校验可解析，`docker compose config --services` 只列服务名）；没有这类接口就停止依赖它的部分并报告缺口。
  - 不用 `env`、`printenv`，不取 `docker inspect` 的 `.Config.Env` 全量，不整文件 `cat`。

## Compose 与网络暴露

- 支持 Compose 就用 `docker compose`，不擅自迁移到 systemd（系统服务除外）。Compose 服务优先走内网：不发布端口或只绑 `127.0.0.1`（指请求发起端所在的命名空间），容器之间用服务名互通，管理端口不对外。
- **带一次性迁移服务（one-shot migrate）的 Compose 项目**：watchtower 这类单容器更新器只重建镜像变了的那个容器，不会重跑一次性服务。所以要先确认应用容器自己会先跑迁移（例如 entrypoint 先 migrate 再 exec 主进程；watchtower 克隆的是容器自身的 Entrypoint/Cmd，这种写法能覆盖自动更新）。否则改用 `docker compose pull` → `docker compose stop <app>` → `docker compose up -d`，并用应用自带的状态命令核对 schema 版本和健康检查。
<!-- END service-runtime -->

<a id="branch-remote-files-backup"></a>
<!-- BEGIN remote-files-backup -->
# 远端文件落位与备份

## 工作目录（远端）

- **Minis 端登录的所有主机**：过程产物（脚本草稿和被测副本、夹具、日志、克隆副本、样本、临时快照）统一放在 `/root/workdir/minis/<项目>/`，根目录不存在就 `install -d -m 700 /root/workdir/minis`。**项目目录按任务对象命名，同一对象始终复用，不在 `/root` 顶层散落文件。**目录 700、文件 600；保留结论性产物，临时文件的收尾清理按总控的写入安全规则。
- **例外**：交付件和生产文件本身放在它服务的正式路径（如 `/root/<脚本>.sh`、`/usr/local/bin/`、`/etc/**`）；备份放在 `/root/backup/`（见下节）；设备和实例已有的路径（`/root/env/`、`/root/connect-device.sh`、`/root/lobehub/` 等）不动。开发中的草稿在工作目录，交付和装机的版本放正式路径。
- **LobeHub 端**：执行目录由平台的工作目录设置决定，不套用 Minis 的路径；同一主机上由 Minis 端整理或产出的 LobeHub 过程产物放 `/root/workdir/lobehub/`，LobeHub 端自己已有的工作目录不动。
- 历史遗留的文件和备份不追溯、不清理；用户明确要求整理时才合并，原路径保留到用户确认删除。

## 备份

- **唯一的备份根**：远端备份统一放 `/root/backup/`，顶层只允许这一个目录（不要再出现 `/root/backups`、`/root/luno-backups` 这类平行目录）；不存在就 `install -d -m 700 /root/backup`，目录 700、文件 600。
- **目录和命名**：按对象或用途分目录（如 `db/`、`config/`、`platform/`；一次性批次用 `<批次名>-<日期>/`），最多两层，优先复用已有目录。文件名 `<对象>.<用途>.<YYYYMMDD-HHMM>`（如 `db/lobehub.dump.20260915-0930`）。改配置前的就地 `.bak` 临时快照也放这里，任务结束前删除，不留在配置文件旁边。
- **有限滚动**：备份前和最新一份比对，一样就不重复备份。同一对象保留最近 1 份，数据库和整机 dump 保留 2 份。淘汰旧份前，新份必须非空、大小合理，并在目标主机上按类型只读校验可恢复性：
  - dump：工具成功结束、格式可列举、全部数据可解码，并与完成时的可信校验和一致（PostgreSQL custom/directory/tar 格式可以用 `pg_restore --list`，再不带 `--dbname` 把完整恢复脚本输出到空设备）；
  - 归档：列表可解析、压缩和成员校验通过（如 `gzip -t`、`unzip -t`），并核对完成时的可信校验和；
  - 普通副本：只由备份工具核对源和备份的校验和，不展示或解析凭据文件。

  只看列表或事后自算的校验和不能单独证明可恢复；plain SQL、快照等缺少充分只读判据的，保留旧份，真正的恢复演练放在授权的隔离环境里做。校验输出和错误原文不回传，只记路径、时间、大小、校验值和状态。未通过、没执行或证据不足都不能淘汰旧份，保留并报告；只删 `/root/backup/` 下自己产生的备份。
- **容量**：不设容量阈值，不因容量另设暂停或确认；每次备份后用 `du -sb /root/backup` 统计总大小（表观字节）并在交付中报告。
- **秘密**：诊断投影和完整恢复备份按 `luno-core/references/execution.md`〔分支 safety〕〈授权与安全〉的〈秘密面〉。完整备份文件权限 600 也不代表不含秘密；不能用脱敏导出冒充可恢复的备份。
- 流程要求备份必须放在原目录才能生效的，要在对应技能里写明原因，不作为默认例外。
<!-- END remote-files-backup -->

<a id="branch-ssh"></a>
<!-- BEGIN ssh -->
# SSH 连接与非交互探测

凭据、落点、临时文件和授权规则不因本资源放宽。

- **命令定位**：非交互 SSH 的 `PATH` 常缺 `/usr/local/bin` 和 mise 路径，所以 `command -v` 没命中不能说明没安装。用 `bash -lc '…'` 或直接读候选路径（如 `/root/.local/share/mise/installs/node/*/bin/lh`）；登录 shell 仍没命中时还要补核路径。fish 主机上的远端命令要显式用 `sh -c` 或 `bash -lc` 包裹，不在命令位置用 `$( )`。
- **批量与串行**：同一主机、同一授权范围、同一阶段的只读步骤尽量合并执行，分别捕获各步的退出码和 stderr，只输出必要的安全错误；依赖前一步结果的步骤不提前执行。同一主机的写操作串行；读取并发仍受生产取证限制。
- **连接参数**：非交互连接显式设置 `BatchMode=yes` 和 `StrictHostKeyChecking=yes`；主机密钥未知或变更就停下，按可信来源核对指纹，不用 `no` 或 `accept-new` 绕过。自动化连接用 `-F none` 隔离本机的 SSH 配置（用前确认客户端支持），所需的主机和跳板参数在授权内显式给出；身份显式指定本次获准的私钥，并设 `IdentitiesOnly=yes`、`IdentityAgent=none`，不回退到默认私钥或 agent。
- **超时与结果**：`ConnectTimeout` 只限制建连握手，`ServerAlive*` 不能当命令截止时间；总时限按任务另设，并给清理留余量。退出码 255 或本地超时不足以判定远端没执行，要结合必要的安全 stderr 和实际状态判断；重试按总控的失败处置。
<!-- END ssh -->

