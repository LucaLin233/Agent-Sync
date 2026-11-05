先取得本包入口必需规则。

<!-- 服务排障节：依据官方文档 systemd（systemctl／journalctl）、PM2、Docker Compose CLI、nginx 运行控制与配置测试，自有表述，2026-11-06 重写；授权、确认与秘密投影条款为本技能自有规则。 -->

## 服务排障
- 先认承载：确认服务由 systemd、PM2 还是 Compose 托管，再按症状归类——配置错误、依赖缺失、权限拒绝、端口占用、上游不可达、DNS 不匹配——各类取不同证据，不混着试。取证一律有界：状态一次性取全，日志用 `-n`／`--tail`／`--since` 限定窗口，**默认不跟随输出（不用 `-f` 等）**；端口归属用 `ss -ltnp`；路径权限用 `namei -l` 逐级看，分清属主、组与其他人的执行位。
- Web 请求按证据链逐跳核对：应用是否在监听 → Nginx 是否反代到该监听 → DNS 是否指向该主机 → TLS 是否由预期证书提供；每跳记下结论。末端 502 不等于 `proxy_pass` 写错，不得据此直改配置。
- 校验与生效分开：配置先 `nginx -t` 通过才 reload；`restart` 与 `reload` 语义不同，不得互替；凡让改动生效的命令都属变更，按本技能入口〈安全与测试〉确认后执行。
- 修复走最小闭环：最小改动 → 分项验证 → 通过即收口交付。只在验证失败或命中事先约定的回滚判据时才回滚，且限在既有授权内（要动改前备份时，先读 `references/remote-files-backup.md` 的〈备份（远端通用）〉）。停止条件：同一现象两次无新进展、需扩权或越边界、证据不足即停在报缺口；「无进展」指**该路径**没取到新证据——授权允许时可换另一条有依据的路径，越界与证据不足仍停并报缺口。
- 环境与配置的读取同按投影形态：**只核声明的指定键**的存在性与长度，不取全量后再脱敏。容器/主机环境在容器内对**声明的指定键**取值长度（输出仅键名、长度与是否已设值）：`docker exec <容器> sh -c 'for k in "$@"; do eval "v=\${$k}"; printf "%s len=%s state=%s\n" "$k" "${#v}" "$([ -n "$v" ] && echo set || echo unset)"; done' sh API_KEY DB_PASSWORD`。普通非凭据配置文件／env 文件只取键名清单或声明的指定键：`awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $1}' <文件>`（只列键名）、`awk -F= '$1=="KEY"{print $1, length(substr($0,index($0,"=")+1))}' <文件>`（只给指定键的长度；值内含 `=` 时按第一个 `=` 之后整段计长，避开 `$2` 只数到第二段的偏差）、**已确认非凭据的 JSON 配置**（沿用目标侧既有工具，新增安装另行确认）只按声明的字段路径投影：`jq '{port: .server.port, log_level: .logging.level}' <文件>`（路径逐个声明后才输出）。凭据 env 文件不由助手解析取值，只经配置持有端已有的投影接口核验（如 Compose 侧 `docker compose config --quiet` 只校验可解析、`docker compose config --services` 只列服务名），缺接口即停依赖并报缺口。不用 `env`／`printenv`、不取 `docker inspect` 的 `.Config.Env` 全量、不整文件 `cat`。

## Compose 与网络暴露
- 支持 Compose 就用 `docker compose`，不擅自迁移到 systemd（系统服务除外）。Compose 服务优先内网：不发布端口或仅绑 `[IP地址]`，容器间以服务名互通，管理端口不对外（`[IP地址]` 指请求发起端命名空间）。
- 带一次性迁移服务（one-shot migrate）的 Compose 项目：watchtower 一类单容器更新器只重建镜像变了的那个容器、不会重跑一次性服务，故须先确认应用容器自身会先跑迁移（如 entrypoint 前置 migrate 再 exec 主进程——watchtower 克隆的是容器自身 Entrypoint/Cmd，因此该写法能覆盖自动更新），否则改走 `docker compose pull` → `docker compose stop <app>` → `docker compose up -d`，并以应用自带的状态命令核对 schema 版本与健康检查。
