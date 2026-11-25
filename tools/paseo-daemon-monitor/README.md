# 宿主机资源（Paseo 插件）

在 Paseo 侧栏底部常驻一行 CPU、内存、系统盘使用率，点击打开详情；宽版显示短条，紧凑版只保留图标与百分比。

## 安装

在插件目录内直接安装，manifest 的 `id` 为 `daemon-monitor`，无需另设运行 ID：

```sh
paseo plugin install "$PWD"
```

源码更新后在同目录重载：

```sh
paseo plugin reload daemon-monitor
```

已有安装沿用其实际运行 ID。安装与重载都会写入该 daemon，须另行确认目标与授权。

## 取数口径

- 服务端插件代码运行在 daemon 进程旁，直接读 daemon 所在主机的数据，不需要路径、命令或凭据，也不向外传主机地址。
- CPU：Linux 取 `/proc/stat` 汇总行相邻两次计数，100% 代表全部逻辑核心满载；其他平台用 `os.cpus()` 同源计数。首次采样在同一请求内取两次，避免显示伪造的 0%。
- 内存：Linux 已用 = 总量 − `/proc/meminfo` `MemAvailable`；其他平台退到 `os.totalmem()`/`os.freemem()`，并在详情标明该平台没有 MemAvailable。
- 系统盘：`fs.statfs` 读系统根所在文件系统（`/`，Windows 为 `C:\`），只算这一个挂载点；已用按 `blocks - bfree`，可用按 `bavail`。
- daemon 主进程（仅 Linux，可选）：进程 CPU、RSS、PID 读自插件父进程 `/proc`。启动时固定 ppid，IPC 断开或 ppid 变化即停止上报，绝不用插件子进程冒充。
- 轮询 5 秒一次，仅组件挂载且应用在前台时进行；服务端另有 1 秒缓存，避免同一时刻的重复读取。

## 状态

正常时 footer 不带徽标；采样失败或主机断线时保留旧值并标注「旧样本／读取失败」。详情错误使用固定文案，不回显原始错误。

## 自验

```sh
npm install --ignore-scripts
npm run typecheck
npm test
```

开发依赖固定 `@getpaseo/* 0.17.3`；本版另以官方 0.17.4 编译入口实编译通过。未安装、未在真实客户端验收。
