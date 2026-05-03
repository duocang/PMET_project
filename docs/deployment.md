# Deployment guide — deep dive

**[English](#en) · [汉文](#cn)**

A companion to [main README §8](../README.md#en-8) for the parts that don't fit there: SSL, horizontal worker scaling, backup, health checks, and recipes for the most common operational issues. **Read main README §8 first** for the basic bring-up — that covers prerequisites, ports, the `make up` lifecycle, bind mounts, and admin auth.

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Stack at a glance](#en-1) | [5. SSL / TLS in front of nginx](#en-5) |
| [2. Health checks](#en-2) | [6. Backups](#en-6) |
| [3. Logs (filtered by service)](#en-3) | [7. Maintenance](#en-7) |
| [4. Scaling workers](#en-4) | [8. Operational troubleshooting](#en-8) |

<a id="en-1"></a>

## 1. Stack at a glance

```
                browser :5960
                     │
                ┌────▼────┐
                │  nginx  │  reverse proxy
                └────┬────┘
        ┌───────────┼───────────────┐
        │           │               │
   ┌────▼───┐  ┌────▼─────┐    ┌────▼────┐
   │frontend│  │   api    │    │  redis  │
   │ Next.js│  │ FastAPI  │    │ broker+ │
   │  :3000 │  │  :8000   │    │ backend │
   └────────┘  └────┬─────┘    │  :6379  │
                    │          └────┬────┘
                    │               │
              ┌─────▼─────┐    ┌────▼─────────────┐
              │  worker   │    │liveness-watchdog │
              │  Celery   │    │ kills idle tasks │
              │  + binar. │    │       > 15 min   │
              └───────────┘    └──────────────────┘
```

Six services. Only `nginx` is published to the host (`5960`). The others are reachable only on the docker network. Build and lifecycle commands live in [`deploy/Makefile`](../deploy/Makefile); the top-level `Makefile` proxies the common ones.

<a id="en-2"></a>

## 2. Health checks

```bash
# Test the full nginx → API round-trip (the path users actually take).
curl -sf http://localhost:5960/api/health && echo OK

# All the rest run from deploy/ to use docker compose exec.
cd deploy

# Redis liveness — should print PONG.
docker compose exec redis redis-cli ping

# API liveness from inside the docker network.
docker compose exec api curl -sf http://localhost:8000/health && echo OK

# Frontend liveness (just checks the dev/prod server returns the home page).
docker compose exec frontend curl -sf http://localhost:3000 >/dev/null && echo OK
```

**Needs** — `make up` already done; `docker compose` plugin (not standalone `docker-compose`) on `$PATH`.

**Produces** — exit 0 if the service responds. The api `/health` returns a tiny JSON sanity blob; the frontend just returns the home page.

**How to read it** — any non-zero exit → that service either isn't up (`make ps` should show one container missing) or is wedged. Tail its log (§3) for the actual error.

<a id="en-3"></a>

## 3. Logs (filtered by service)

```bash
cd deploy

# Tail all services live (Ctrl-C to detach).
docker compose logs -f

# Same but only api + worker.
docker compose logs -f api worker

# Last 200 lines from worker, then exit.
docker compose logs --tail=200 worker

# Last 10 minutes from nginx, then exit.
docker compose logs --since=10m nginx
```

Common patterns to grep for:

| What you saw | What to grep |
|---|---|
| Task stuck in "running" | `docker compose logs liveness-watchdog \| grep <task_id>` |
| Worker SIGKILL'd by OOM | `docker compose logs worker \| grep -i 'killed\|oom'` |
| 5xx from the UI | `docker compose logs api \| grep -E ' 5[0-9]{2} '` |
| Email send failure | `docker compose logs worker \| grep -i 'smtp\|sendmail'` |

<a id="en-4"></a>

## 4. Scaling workers

Two knobs:

```bash
# Knob A — raise per-worker concurrency (single container, more parallel
# tasks). Default is 2.
PMET_WORKERS=4 make up

# Knob B — horizontal scale (N worker containers, each its own process tree).
cd deploy && docker compose up -d --scale worker=3
```

**Needs** — enough host CPU and RAM to not thrash. PMET tasks are CPU-heavy during pairing (motif × motif inner loop), I/O-heavy during indexing (FIMO + small-file write).

**Produces** — multiple worker containers; tasks fan out across them via the redis broker. `make ps` shows them as `worker_1`, `worker_2`, etc.

**How to read it** — knob A is simpler and usually enough; reach for knob B only if you're hitting CPU but Celery's per-worker concurrency is already saturated. With multiple worker containers, the `liveness-watchdog` still kills stale tasks regardless of which container they're on (it shares the worker's PID namespace via `pid: service:worker`, so for multi-container scaling you may want to run one watchdog per worker — currently the watchdog only sees the first worker's tree).

<a id="en-5"></a>

## 5. SSL / TLS in front of nginx

The default `make up` exposes `5960` over plain HTTP. For a public deploy:

1. Get certificates (Let's Encrypt via certbot is easiest). Place `cert.pem` and `key.pem` somewhere docker can mount, e.g. `deploy/nginx/ssl/`.
2. Edit [`deploy/nginx/nginx.conf`](../deploy/nginx/) to add an HTTPS `server { listen 443 ssl; ... }` block alongside (or replacing) the HTTP one.
3. Update `deploy/docker-compose.yml`'s nginx service to publish 443 (and optionally 80 for redirect) and to mount the SSL dir.
4. `cd deploy && make restart-nginx` (no rebuild needed; the nginx config is bind-mounted).

Verify: `curl -vfsSL https://your.domain.example/api/health`. If you serve HTTP on 80 only for the certbot ACME challenge, be sure the `/.well-known/acme-challenge/` location stays plain HTTP.

<a id="en-6"></a>

## 6. Backups

Three things matter for disaster recovery:

```bash
# 1. Per-task results (the user-facing artifacts)
tar -czf pmet_results_$(date +%Y%m%d).tar.gz results/app/

# 2. Backend SQLite metadata (task records, statuses)
cp apps/pmet_backend/pmet.db pmet_db_$(date +%Y%m%d).db

# 3. Configure dir (admin token, email creds, etc. — be careful with this one)
tar -czf pmet_config_$(date +%Y%m%d).tar.gz deploy/configure/
```

`results/app/` and `apps/pmet_backend/pmet.db` are bind-mounted from the host, so backing up the host paths is sufficient — no need to `docker compose exec` into anything. The `deploy/configure/` tarball contains secrets; store it encrypted.

Restore is the reverse: stop the stack (`make down`), untar / cp back, `make up`.

<a id="en-7"></a>

## 7. Maintenance

```bash
# Pull image updates and restart
cd deploy && docker compose pull && docker compose up -d

# Trim old per-task results (older than 7 days)
find results/app/ -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;

# Disk usage at a glance
du -sh results/app/ data/precomputed_indexes/

# Wipe everything (careful — destroys task history)
make clean-results-app
```

Periodic tasks worth scripting via cron or your scheduler:

- Trim old results (above) — daily.
- Prune unused docker images and volumes — weekly: `docker system prune -f`.
- Snapshot SQLite + configure dir — daily; keep last N.

<a id="en-8"></a>

## 8. Operational troubleshooting

For first-run / "does it work at all" issues see [main README §10](../README.md#en-10). The list here is for "it was working and now it isn't":

### Worker stops processing tasks

```bash
cd deploy && docker compose logs worker | tail -50
```

Most common: an OOM kill (one task ran the host out of RAM, took the worker with it). Restart and lower `PMET_WORKERS` or scale horizontally instead. Less common: redis lost connection — `docker compose logs redis` for the cause.

```bash
cd deploy && make restart-worker
```

### File upload fails with "413 Request Entity Too Large"

nginx limit. Edit [`deploy/nginx/nginx.conf`](../deploy/nginx/), bump `client_max_body_size`, then `make restart-nginx`.

### Email not sending

```bash
# Eyeball the credentials file: it must be exactly 5 lines, no leading/trailing whitespace.
cat deploy/configure/email_credential.txt

# Move into deploy/ so docker compose can find compose.yml.
cd deploy

# Test the SMTP path from inside the worker container — same network the
# worker uses, so any host firewall / DNS shenanigans show up here.
docker compose exec worker python -c "
import smtplib
s = smtplib.SMTP('smtp.gmail.com', 587)
s.starttls()
s.login('your_email@gmail.com', 'your_app_password')
print('OK')
"
```

For Gmail, you need an **app password**, not your account password.

### Stack rebuilds slowly

`make rebuild` from the repo root rebuilds everything. To rebuild only the changed piece:

```bash
cd deploy

# Rebuild ONLY the frontend image — pick this if you only edited
# anything under apps/pmet_frontend/.
make rebuild-frontend

# Rebuild ONLY the backend image — pick this if you only edited
# Dockerfile or requirements.txt.
make rebuild-backend

# No rebuild, just restart the worker — pick this if you only edited
# Python under apps/pmet_backend/worker/ (bind-mounted into the image).
make restart-worker
```

The frontend image is the slow one (full Next.js build). Backend code changes don't require a rebuild — only Dockerfile/requirements changes do.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 栈结构一览](#cn-1) | [5. nginx 前面挂 SSL/TLS](#cn-5) |
| [2. 健康检查](#cn-2) | [6. 备份](#cn-6) |
| [3. 日志（按服务过滤）](#cn-3) | [7. 维护](#cn-7) |
| [4. worker 扩容](#cn-4) | [8. 运行期排错](#cn-8) |

<a id="cn-1"></a>

## 1. 栈结构一览

```
                浏览器 :5960
                     │
                ┌────▼────┐
                │  nginx  │  反向代理
                └────┬────┘
        ┌───────────┼───────────────┐
        │           │               │
   ┌────▼───┐  ┌────▼─────┐    ┌────▼────┐
   │frontend│  │   api    │    │  redis  │
   │ Next.js│  │ FastAPI  │    │ broker+ │
   │  :3000 │  │  :8000   │    │ backend │
   └────────┘  └────┬─────┘    │  :6379  │
                    │          └────┬────┘
                    │               │
              ┌─────▼─────┐    ┌────▼──────────────┐
              │  worker   │    │liveness-watchdog  │
              │  Celery   │    │ 杀掉 > 15 min 闲置 │
              │  + 二进制 │    │      的任务        │
              └───────────┘    └───────────────────┘
```

6 个服务。只有 `nginx` 暴露给 host（`5960`）。其它仅在 docker 网络内可达。构建和生命周期命令在 [`deploy/Makefile`](../deploy/Makefile)，顶层 `Makefile` 只代理常用的几条。

<a id="cn-2"></a>

## 2. 健康检查

```bash
# 测完整的 nginx → API 回路（用户实际走的路径）。
curl -sf http://localhost:5960/api/health && echo OK

# 剩下的从 deploy/ 跑，因为要 docker compose exec。
cd deploy

# Redis 存活 —— 应该打 PONG。
docker compose exec redis redis-cli ping

# 从 docker 网络内部测 API 存活。
docker compose exec api curl -sf http://localhost:8000/health && echo OK

# 前端存活（仅检查 dev/prod 服务返回首页）。
docker compose exec frontend curl -sf http://localhost:3000 >/dev/null && echo OK
```

**需要** —— `make up` 已经跑过；`$PATH` 上有 `docker compose` 插件（不是独立的 `docker-compose`）。

**产出** —— 服务有响应 exit 0。api `/health` 返回小段 JSON；frontend 直接给首页。

**怎么解读** —— 任何非 0 退出 → 该服务要么没起（`make ps` 应该看到少一个容器），要么卡死。看 §3 该服务的日志找真正错误。

<a id="cn-3"></a>

## 3. 日志（按服务过滤）

```bash
cd deploy

# 实时跟所有服务的日志（Ctrl-C 退出）。
docker compose logs -f

# 同样但只跟 api + worker。
docker compose logs -f api worker

# worker 末 200 行，然后退出。
docker compose logs --tail=200 worker

# nginx 最近 10 分钟，然后退出。
docker compose logs --since=10m nginx
```

常见 grep 模式：

| 你看到的 | grep 什么 |
|---|---|
| 任务卡在 running | `docker compose logs liveness-watchdog \| grep <task_id>` |
| worker 被 OOM SIGKILL | `docker compose logs worker \| grep -i 'killed\|oom'` |
| UI 报 5xx | `docker compose logs api \| grep -E ' 5[0-9]{2} '` |
| 邮件发不出 | `docker compose logs worker \| grep -i 'smtp\|sendmail'` |

<a id="cn-4"></a>

## 4. worker 扩容

两个旋钮：

```bash
# 旋钮 A —— 提高单 worker 的并发（一个容器，更多并行任务）。默认 2。
PMET_WORKERS=4 make up

# 旋钮 B —— 横向扩（N 个 worker 容器，每个一个独立进程树）。
cd deploy && docker compose up -d --scale worker=3
```

**需要** —— host 有足够 CPU 和 RAM 不打架。PMET 任务在 pairing 时 CPU 重（motif × motif 内循环），indexing 时 I/O 重（FIMO + 小文件写）。

**产出** —— 多个 worker 容器；任务通过 redis broker 在它们之间分发。`make ps` 看到 `worker_1`、`worker_2` 等。

**怎么解读** —— 旋钮 A 更简单，通常够用；CPU 已经打满 + Celery 单 worker 并发也满了，再考虑 B。多容器场景下 `liveness-watchdog` 仍然杀僵死任务（它通过 `pid: service:worker` 共享 worker 的 PID namespace），但目前只看得到第一个 worker 的进程树 —— 多容器扩容时可能要每个 worker 一个 watchdog。

<a id="cn-5"></a>

## 5. nginx 前面挂 SSL/TLS

默认 `make up` 在 `5960` 上裸 HTTP 暴露。公网部署时：

1. 拿证书（Let's Encrypt + certbot 最容易）。把 `cert.pem` 和 `key.pem` 放到 docker 能 mount 的地方，比如 `deploy/nginx/ssl/`。
2. 编辑 [`deploy/nginx/nginx.conf`](../deploy/nginx/) 加一个 HTTPS `server { listen 443 ssl; ... }` 块，与 HTTP 并存或替换。
3. 改 `deploy/docker-compose.yml` 的 nginx 服务，发布 443（可选发布 80 做跳转），mount SSL 目录。
4. `cd deploy && make restart-nginx`（不用 rebuild；nginx config 是 bind-mount）。

验证：`curl -vfsSL https://your.domain.example/api/health`。如果你只在 80 上跑 certbot ACME challenge，记得 `/.well-known/acme-challenge/` 这个 location 要保留 plain HTTP。

<a id="cn-6"></a>

## 6. 备份

灾恢三件事：

```bash
# 1. per-task 结果（用户面 artifact）
tar -czf pmet_results_$(date +%Y%m%d).tar.gz results/app/

# 2. 后端 SQLite 元数据（任务记录、状态）
cp apps/pmet_backend/pmet.db pmet_db_$(date +%Y%m%d).db

# 3. configure 目录（admin token、email 凭据等 —— 这个要小心）
tar -czf pmet_config_$(date +%Y%m%d).tar.gz deploy/configure/
```

`results/app/` 和 `apps/pmet_backend/pmet.db` 都是从 host bind-mount 进去的，所以备份 host 路径就够了，不用 `docker compose exec`。`deploy/configure/` tarball 含密钥；加密存。

恢复反过来：停栈（`make down`）、untar / cp 回去、`make up`。

<a id="cn-7"></a>

## 7. 维护

```bash
# 拉镜像更新并重启
cd deploy && docker compose pull && docker compose up -d

# 清旧 per-task 结果（7 天前的）
find results/app/ -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;

# 看磁盘占用
du -sh results/app/ data/precomputed_indexes/

# 全清（小心 —— 会清掉任务历史）
make clean-results-app
```

值得用 cron 或调度器跑的周期任务：

- 清旧结果（上面）—— 每天。
- prune 没用的 docker 镜像和 volume —— 每周：`docker system prune -f`。
- SQLite + configure 目录快照 —— 每天，留最近 N 份。

<a id="cn-8"></a>

## 8. 运行期排错

首跑 / "到底能不能用" 类问题看 [主 README §10](../README.md#cn-10)。这里列的是"原本能跑、现在不能"：

### Worker 不再处理任务

```bash
cd deploy && docker compose logs worker | tail -50
```

最常见：OOM kill（某个任务把 host 内存吃光，把 worker 也带挂）。重启后调低 `PMET_WORKERS` 或改成横向扩。次常见：redis 掉连接 —— `docker compose logs redis` 找原因。

```bash
cd deploy && make restart-worker
```

### 文件上传报 "413 Request Entity Too Large"

nginx 限制。编辑 [`deploy/nginx/nginx.conf`](../deploy/nginx/) 调大 `client_max_body_size`，`make restart-nginx`。

### 邮件发不出

```bash
# 看一眼凭据文件：必须正好 5 行，前后无空白。
cat deploy/configure/email_credential.txt

# 进 deploy/ 让 docker compose 找得到 compose.yml。
cd deploy

# 从 worker 容器内部测 SMTP 路径 —— 跟 worker 同一份网络，
# host 防火墙 / DNS 问题在这里都会暴露出来。
docker compose exec worker python -c "
import smtplib
s = smtplib.SMTP('smtp.gmail.com', 587)
s.starttls()
s.login('your_email@gmail.com', 'your_app_password')
print('OK')
"
```

Gmail 要的是 **app password**，不是你账号密码。

### 栈重建很慢

仓库根 `make rebuild` 把所有都重建。只重建变了的那块：

```bash
cd deploy

# 只重建前端镜像 —— 适用于只改了 apps/pmet_frontend/ 下的内容。
make rebuild-frontend

# 只重建后端镜像 —— 适用于只改了 Dockerfile 或 requirements.txt。
make rebuild-backend

# 不重建，只重启 worker —— 适用于只改了 apps/pmet_backend/worker/
# 下的 Python（bind-mount 进镜像了）。
make restart-worker
```

前端镜像是慢的那个（完整 Next.js build）。后端 Python 改了不用 rebuild —— 只有 Dockerfile / requirements 改了才要。
