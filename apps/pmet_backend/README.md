# PMET Backend Service

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. What this is](#en-1) | [4. Smoke test](#en-4) |
| [2. Quick start](#en-2) | [5. Environment variables](#en-5) |
| [3. API endpoints](#en-3) | [6. Architecture](#en-6) |

<a id="en-1"></a>

## 1. What this is

The server-side of the PMET web app: a FastAPI HTTP layer plus a Celery worker that does the actual heavy lifting. The HTTP layer takes task submissions from the UI, drops them on a Redis queue; the worker picks them up, runs the corresponding workflow script (under `scripts/workflows/`), tracks progress, mails the user when done. A side process (`liveness-watchdog`) kills any task that goes silent for more than 15 minutes.

Production runs in docker (`make up` from the repo root). This README covers the case where you want to bypass docker — iterate on Python code with auto-reload, run the smoke test, or just look up an env var or endpoint.

<a id="en-2"></a>

## 2. Quick start

The docker stack at [../../deploy/](../../deploy/) is the canonical entrypoint. Use the local bring-up below when you want fast feedback on Python edits without rebuilding the image.

```bash
# 1. Redis (Celery broker + result backend)
docker run -d -p 6379:6379 redis:7-alpine

# 2. Backend deps
pip install -r requirements.txt

# 3. API server (auto-reloads on edits to api/)
uvicorn api.main:app --reload --port 8000

# 4. Celery worker, separate terminal (no auto-reload — restart to pick up changes)
celery -A worker.celery_app worker --loglevel=info
```

<a id="en-3"></a>

## 3. API endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET  | `/`                                | API info |
| GET  | `/health`                          | Health check |
| GET  | `/docs`                            | Swagger UI |
| POST | `/api/tasks`                       | Create a new PMET task |
| GET  | `/api/tasks`                       | List tasks (server-side filtered + paginated) |
| GET  | `/api/tasks/{id}`                  | Task detail (status, stages, partial-result link if any) |
| GET  | `/api/tasks/{id}/result`           | Download the success-case zip |
| GET  | `/api/tasks/{id}/partial-result`   | Stream `motif_output.txt` for failed-but-have-output tasks |
| POST | `/api/tasks/{id}/cancel`           | Admin-only: terminate a running task |
| POST | `/api/files/upload`                | Upload a file referenced by a task |
| GET  | `/api/admin/login`                 | Admin token entry |
| GET  | `/api/admin/settings`              | Admin: notify-on-submit toggle |

<a id="en-4"></a>

## 4. Smoke test

A 5-stage import-and-load check that catches the obvious "did I break something" cases without needing docker. Hits each of the five top-level pieces (config, Pydantic models, storage service, executor, FastAPI app object) and reports per-stage PASS/FAIL.

```bash
python test_api.py                     # on the host
cd deploy && make test                 # inside the backend image
```

**Needs** — `python3` plus the backend deps (`pip install -r requirements.txt`), since each stage actually imports the production module. Doesn't need Redis or a running Celery worker.

**Produces** — stdout only. Exits 0 if all 5 stages pass, non-zero otherwise.

**How to read it**

```
============================================================
PMET Backend Verification
============================================================

1. Testing imports...
   - config loaded, NCPU=2
   - TaskCreate model OK
   - StorageService OK
   - PMETExecutor OK
   - MailService OK
   - Celery app OK, broker=redis://localhost:6379/0
   ✓ All imports successful

2. Testing TaskCreate model...
   - Created task for user@example.com
   - Mode: promoters_pre
   - IC threshold: 4.0
   ✓ Model validation OK

…

============================================================
RESULTS: 5/5 passed
============================================================
```

A `✗` in any stage means that stage failed; the line right after it is the actual exception. The most common host failure is `ModuleNotFoundError: No module named 'pydantic'` — install backend deps and retry.

<a id="en-5"></a>

## 5. Environment variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL`               | `redis://localhost:6379/0`        | Redis connection URL |
| `PMET_WORKERS`            | `2`                               | Number of Celery worker processes |
| `PMET_RESULT_DIR_REL`     | `results/app`                     | Per-task output dir (relative to the backend's `RESULT_DIR` root) |
| `PMET_LIVENESS_TIMEOUT_SEC` | `900`                           | watchdog kills tasks idle longer than this |
| `PMET_WATCHDOG_POLL_SEC`  | `60`                              | watchdog scan period |
| `PMET_MINHASH_MIN`        | unset                             | force MinHash prefilter K (opt-in; off by default — see [docs/perf/minhash_calibration.md](../../docs/perf/minhash_calibration.md)) |
| `PMET_MINHASH_THRESHOLD`  | `500`                             | motif-count threshold for auto-enabling MinHash |
| `PMET_MINHASH_DEFAULT`    | `0`                               | K used when auto-enabled (0 disables) |
| `NGINX_LINK`              | unset                             | base URL written into per-task email bodies (e.g. `https://pmet.example.org`) |

<a id="en-6"></a>

## 6. Architecture

```
pmet_backend/
├── api/
│   ├── main.py              FastAPI application
│   ├── routes/
│   │   ├── tasks.py         task endpoints (list / detail / partial-result / cancel)
│   │   ├── demo.py          demo data endpoints
│   │   ├── files.py         file upload endpoints
│   │   └── admin.py         admin endpoints (login / settings)
│   └── models/
│       └── task.py          Pydantic models
├── worker/
│   ├── celery_app.py        Celery configuration
│   ├── liveness_watchdog.py side process — kills stale tasks
│   └── tasks/
│       └── pmet.py          PMET task implementation
├── services/
│   ├── executor.py          PMET shell/binary execution
│   ├── mail.py              email notifications (success / partial / failed)
│   ├── storage.py           file storage management
│   ├── stage_status.py      filesystem-derived per-stage view
│   └── database.py          SQLite metadata store
├── config.py                configuration
├── requirements.txt
├── Dockerfile
└── test_api.py              5-stage smoke (run with `python test_api.py`)
```

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 这是什么](#cn-1) | [4. Smoke 测试](#cn-4) |
| [2. Quick start](#cn-2) | [5. 环境变量](#cn-5) |
| [3. API 端点](#cn-3) | [6. 目录结构](#cn-6) |

<a id="cn-1"></a>

## 1. 这是什么

PMET web 应用的服务端：FastAPI 这层 HTTP 接口加一个 Celery worker 干重活。HTTP 接收前端提交的任务、扔到 Redis 队列；worker 把它捡起来、跑对应的 workflow 脚本（在 `scripts/workflows/` 下）、跟进进度、跑完给用户发邮件。一个守护进程（`liveness-watchdog`）会杀掉任何超过 15 分钟没动静的任务。

生产环境是 docker 栈（仓库根 `make up`）。这份 README 是给想绕开 docker 的场景看的 —— 改 Python 代码要热加载、跑 smoke、或只是查一下某个 env var、某个端点。

<a id="cn-2"></a>

## 2. Quick start

[../../deploy/](../../deploy/) 下的 docker 栈是首选入口。下面这种本地起法适合只想对 Python 改动拿到快速反馈、不想重建镜像的场景。

```bash
# 1. Redis（Celery broker + result backend）
docker run -d -p 6379:6379 redis:7-alpine

# 2. 后端依赖
pip install -r requirements.txt

# 3. API 服务（改 api/ 自动 reload）
uvicorn api.main:app --reload --port 8000

# 4. Celery worker，另开一个终端（不自动 reload，改完要 restart）
celery -A worker.celery_app worker --loglevel=info
```

<a id="cn-3"></a>

## 3. API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/`                                | API 信息 |
| GET  | `/health`                          | 健康检查 |
| GET  | `/docs`                            | Swagger UI |
| POST | `/api/tasks`                       | 创建新 PMET 任务 |
| GET  | `/api/tasks`                       | 列任务（服务端过滤 + 分页） |
| GET  | `/api/tasks/{id}`                  | 任务详情（status、stages、若有 partial-result link） |
| GET  | `/api/tasks/{id}/result`           | 下载成功 case 的 zip |
| GET  | `/api/tasks/{id}/partial-result`   | 流式下载 `motif_output.txt`（失败但有产物的任务） |
| POST | `/api/tasks/{id}/cancel`           | Admin 专用：终止运行中任务 |
| POST | `/api/files/upload`                | 上传任务引用的文件 |
| GET  | `/api/admin/login`                 | 管理员 token 登录 |
| GET  | `/api/admin/settings`              | 管理员：notify-on-submit 开关 |

<a id="cn-4"></a>

## 4. Smoke 测试

5 stage 的 import + load 检查，不用 docker 就能逮住"我是不是把什么弄坏了"这类常见问题。逐个戳后端的 5 大件（config、Pydantic 模型、存储服务、executor、FastAPI app 对象），逐 stage 报 PASS/FAIL。

```bash
python test_api.py                     # host 上跑
cd deploy && make test                 # 在后端镜像里跑
```

**需要** —— `python3` 加后端依赖（`pip install -r requirements.txt`），因为每个 stage 都真的 import 生产模块。不需要 Redis、不需要 Celery worker 在跑。

**产出** —— 仅 stdout。5 stage 全过 exit 0，否则非 0。

**怎么解读**

```
============================================================
PMET Backend Verification
============================================================

1. Testing imports...
   - config loaded, NCPU=2
   - TaskCreate model OK
   - StorageService OK
   - PMETExecutor OK
   - MailService OK
   - Celery app OK, broker=redis://localhost:6379/0
   ✓ All imports successful

2. Testing TaskCreate model...
   - Created task for user@example.com
   - Mode: promoters_pre
   - IC threshold: 4.0
   ✓ Model validation OK

…

============================================================
RESULTS: 5/5 passed
============================================================
```

任一 stage 出现 `✗` 就是那个 stage 挂了；紧跟着那行就是真正的异常。host 上最常见的失败是 `ModuleNotFoundError: No module named 'pydantic'` —— 先装后端依赖再重试。

<a id="cn-5"></a>

## 5. 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `REDIS_URL`                 | `redis://localhost:6379/0` | Redis 连接 URL |
| `PMET_WORKERS`              | `2`                        | Celery worker 进程数 |
| `PMET_RESULT_DIR_REL`       | `results/app`              | 单任务输出目录（相对于后端 `RESULT_DIR` 根） |
| `PMET_LIVENESS_TIMEOUT_SEC` | `900`                      | watchdog 杀超过此秒数无 progress 的任务 |
| `PMET_WATCHDOG_POLL_SEC`    | `60`                       | watchdog 扫描周期 |
| `PMET_MINHASH_MIN`          | 未设                       | 强制启用 MinHash 粗筛 K（opt-in；默认关闭，详见 [docs/perf/minhash_calibration.md](../../docs/perf/minhash_calibration.md)） |
| `PMET_MINHASH_THRESHOLD`    | `500`                      | 自动启用 MinHash 的 motif 数门槛 |
| `PMET_MINHASH_DEFAULT`      | `0`                        | 自动启用时使用的 K（0 即不启用） |
| `NGINX_LINK`                | 未设                       | 写进任务邮件正文的 base URL（例如 `https://pmet.example.org`） |

<a id="cn-6"></a>

## 6. 目录结构

```
pmet_backend/
├── api/
│   ├── main.py              FastAPI 主入口
│   ├── routes/
│   │   ├── tasks.py         任务端点（list / detail / partial-result / cancel）
│   │   ├── demo.py          demo 数据端点
│   │   ├── files.py         文件上传端点
│   │   └── admin.py         管理员端点（login / settings）
│   └── models/
│       └── task.py          Pydantic 模型
├── worker/
│   ├── celery_app.py        Celery 配置
│   ├── liveness_watchdog.py 守护进程 —— 杀僵任务
│   └── tasks/
│       └── pmet.py          PMET 任务实现
├── services/
│   ├── executor.py          PMET shell/二进制执行
│   ├── mail.py              邮件通知（success / partial / failed）
│   ├── storage.py           文件存储
│   ├── stage_status.py      文件系统派生的 per-stage 视图
│   └── database.py          SQLite 元数据
├── config.py                配置
├── requirements.txt
├── Dockerfile
└── test_api.py              5 stage smoke（`python test_api.py`）
```
