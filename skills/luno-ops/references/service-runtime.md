# 服务运行与排障

## 服务排障

- **先认托管方式**：确认服务由 systemd、PM2 还是 Compose 托管，再按症状归类：配置错误、依赖缺失、权限拒绝、端口占用、上游不可达、DNS 不匹配。各类取不同的证据，不混在一起试。
- **取证有界**：状态一次取全；日志用 `-n`、`--tail` 或 `--since` 限定窗口，**默认不跟随输出（不用 `-f`）**；端口归属用 `ss -ltnp`；路径权限用 `namei -l` 逐级看，分清属主、组和其他人的执行位。
- **Web 请求逐跳核对**：应用是否在监听 → Nginx 是否反代到这个监听 → DNS 是否指向这台主机 → TLS 是否由预期的证书提供，每一跳记下结论。末端 502 不等于 `proxy_pass` 写错了，不能据此直接改配置。
- **校验和生效分开**：配置先通过 `nginx -t` 才 reload；`restart` 和 `reload` 语义不同，不能互相代替。凡是让改动生效的命令都算变更，按本技能〈安全与测试〉确认后执行。
- **最小闭环**：最小改动 → 分项验证 → 通过就收口。只有验证失败或命中事先约定的回滚判据时才回滚，并且限在既有授权内（需要用改前备份时，先读 `references/remote-files-backup.md` 的〈备份〉）。同一现象两次没有新进展、需要扩权或越界、证据不足时停下报告缺口；「没有进展」指的是**这条路径**取不到新证据，授权允许时可以换另一条有依据的路径。
- **读环境和配置只取声明的键**：只核声明的指定键是否存在和长度，不取全量再脱敏。
  - 容器或主机环境：按声明的指定键，在容器内只输出键名、长度和是否已设值，如 `docker exec <容器> sh -c 'for k in "$@"; do eval "v=\${$k}"; printf "%s len=%s state=%s\n" "$k" "${#v}" "$([ -n "$v" ] && echo set || echo unset)"; done' sh API_KEY DB_PASSWORD`
  - 普通的非凭据配置文件或 env 文件，只列键名 `awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $1}' <文件>`，或只取声明的指定键的长度 `awk -F= '$1=="KEY"{print $1, length(substr($0,index($0,"=")+1))}' <文件>`（按第一个 `=` 之后的整段计长，值里含 `=` 也不会算错）。
  - **已确认不含凭据的 JSON 配置**，用目标上已有的工具（新安装另行确认）按逐个声明的字段路径投影：`jq '{port: .server.port, log_level: .logging.level}' <文件>`。
  - 凭据 env 文件不由助手解析取值，只通过配置持有方已有的投影接口核验（如 `docker compose config --quiet` 只校验可解析，`docker compose config --services` 只列服务名）；没有这类接口就停止依赖它的部分并报告缺口。
  - 不用 `env`、`printenv`，不取 `docker inspect` 的 `.Config.Env` 全量，不整文件 `cat`。

## Compose 与网络暴露

- 支持 Compose 就用 `docker compose`，不擅自迁移到 systemd（系统服务除外）。Compose 服务优先走内网：不发布端口或只绑 `127.0.0.1`（指请求发起端所在的命名空间），容器之间用服务名互通，管理端口不对外。
- **带一次性迁移服务（one-shot migrate）的 Compose 项目**：watchtower 这类单容器更新器只重建镜像变了的那个容器，不会重跑一次性服务。所以要先确认应用容器自己会先跑迁移（例如 entrypoint 先 migrate 再 exec 主进程；watchtower 克隆的是容器自身的 Entrypoint/Cmd，这种写法能覆盖自动更新）。否则改用 `docker compose pull` → `docker compose stop <app>` → `docker compose up -d`，并用应用自带的状态命令核对 schema 版本和健康检查。
