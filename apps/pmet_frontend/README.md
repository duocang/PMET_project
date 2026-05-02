# PMET Frontend

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. What this is](#en-1) | [4. Pages](#en-4) |
| [2. Quick start](#en-2) | [5. Docker](#en-5) |
| [3. Tech stack](#en-3) | [6. Environment variables](#en-6) |

<a id="en-1"></a>

## 1. What this is

The web UI users see at PMET's URL — submit form, task list, result
visualisation, admin console. Built with Next.js + React + Tailwind;
heavy charts use Plotly; submit-form state lives in Zustand so it
survives in-app navigation.

The production stack runs in docker behind nginx (`make up` from the
repo root). This README is for the two cases where you bypass docker:

- iterate on `app/` or `components/` with hot reload (`npm run dev`)
- know what env vars and pages the app exposes

<a id="en-2"></a>

## 2. Quick start

```bash
npm install        # install deps
npm run dev        # dev server, http://localhost:3000
npm run build      # production bundle
npm start          # serve the production bundle
npm run test:unit  # Zustand store unit tests via tsx
```

**Needs** — Node 18+ (Next.js 14 requirement) and `npm` on `$PATH`.
For `npm run dev` to talk to a real backend you also need either
the docker stack up (`make up` from repo root) or a local backend on
port 8000 (`uvicorn api.main:app` from `apps/pmet_backend/`).

**Produces**

- `npm run dev` — long-running dev server on `http://localhost:3000`,
  hot-reloads on edits to `app/` / `components/` / `lib/`. No files
  written.
- `npm run build` — production bundle under `.next/` (~50 MB,
  gitignored). `npm start` then serves it on port 3000.
- `npm run test:unit` — stdout PASS/FAIL per Zustand store action;
  exit 0 if all pass.

**How to read it**

- Dev server should print `▲ Next.js 14.x.x · Local: http://localhost:3000`
  within ~2 s, then `compiled / in NN ms` on every save. A red
  TypeScript-error overlay in the browser means there's a type error;
  the file + line are both in the overlay and in the terminal.
- `test:unit` prints one `ok` line per case and a final
  `[settings_store] N passed, 0 failed`:

  ```
  [settings_store] running settings-store form-state actions
    ok   updateFilesForMode patches only the target mode
    ok   updateFilesForMode merges patch (does not overwrite siblings)
    …
  [settings_store] 8 passed, 0 failed
  ```

For end-to-end behaviour against the real backend, use the composed
stack: `make up` from the repo root. See [deploy/](../../deploy/).

<a id="en-3"></a>

## 3. Tech stack

- Next.js 14 (App Router)
- React 18 + TypeScript
- Tailwind CSS
- Plotly.js (heatmaps, histograms)
- Zustand (state — submit form is store-backed; only `mode` is persisted to localStorage)
- React Dropzone (file uploads)
- tsx (TypeScript test runner — devDep)

<a id="en-4"></a>

## 4. Pages

| Route | Purpose |
|---|---|
| `/` | Home: hero figure + the four entry-point cards |
| `/submit` | Submit a new analysis (mode-aware form) |
| `/tasks` | List user tasks (search by email or task ID) |
| `/tasks/[id]` | Task detail: status, stages, partial-result link |
| `/tasks/[id]/visualize` | Result visualisation (heatmap + histogram + ranked table) |
| `/visualize` | Open and explore an existing PMET output file |
| `/data` | Pre-computed dataset directory |
| `/about` | Project info |
| `/admin/login` | Admin token entry |
| `/admin/settings` | Admin: notify-on-submit toggle + sign out |

<a id="en-5"></a>

## 5. Docker

```bash
docker build -t pmet-frontend .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://api:8000 pmet-frontend
```

In the composed stack the image is built by `cd deploy && make build-images`.
Edit anything under this directory and you have to rebuild — the frontend
is baked into its image, there's no bind mount. The shortcut is
`cd deploy && make rebuild-frontend`.

<a id="en-6"></a>

## 6. Environment variables

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Where the browser sends `/api/...` calls. In the composed stack this is overridden to a relative path so nginx fronts both `/` and `/api/...` from the same origin. |

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 这是什么](#cn-1) | [4. 页面](#cn-4) |
| [2. Quick start](#cn-2) | [5. Docker](#cn-5) |
| [3. 技术栈](#cn-3) | [6. 环境变量](#cn-6) |

<a id="cn-1"></a>

## 1. 这是什么

用户访问 PMET URL 时看到的 web 界面 —— 提交表单、任务列表、结果
可视化、管理员控制台。技术栈是 Next.js + React + Tailwind；重一点
的图用 Plotly；提交表单的状态放在 Zustand 里，所以应用内跳转不会丢。

生产环境是 docker 栈、nginx 在前面挡着（仓库根 `make up`）。这份
README 是给绕开 docker 的两种场景看的：

- 边改 `app/` 或 `components/` 边热加载预览（`npm run dev`）
- 查应用暴露了哪些 env var 和哪些页面

<a id="cn-2"></a>

## 2. Quick start

```bash
npm install        # 装依赖
npm run dev        # 开发服务器，http://localhost:3000
npm run build      # 生产包
npm start          # 跑生产包
npm run test:unit  # Zustand store 单元测试（用 tsx）
```

**需要** —— Node 18+（Next.js 14 要求）和 `$PATH` 上的 `npm`。
`npm run dev` 想跟真后端说话还需要：要么 docker 栈起着（仓库根
`make up`），要么本地后端在 8000 端口（在 `apps/pmet_backend/` 里
跑 `uvicorn api.main:app`）。

**产出**

- `npm run dev` —— 常驻开发服务器，跑在 `http://localhost:3000`，
  改 `app/` / `components/` / `lib/` 自动热加载。不写文件。
- `npm run build` —— 生产 bundle 落在 `.next/`（~50 MB，gitignored）。
  之后 `npm start` 把它伺服到 3000 端口。
- `npm run test:unit` —— stdout 逐 case PASS/FAIL；全过 exit 0。

**怎么解读**

- 开发服务器 ~2 秒内应该打 `▲ Next.js 14.x.x · Local: http://localhost:3000`，
  然后每次保存打 `compiled / in NN ms`。浏览器里弹红色 TypeScript
  错误浮层意味着有类型错；文件 + 行号 浮层和终端都有。
- `test:unit` 每个 case 一行 `ok`，最后 `[settings_store] N passed, 0 failed`：

  ```
  [settings_store] running settings-store form-state actions
    ok   updateFilesForMode patches only the target mode
    ok   updateFilesForMode merges patch (does not overwrite siblings)
    …
  [settings_store] 8 passed, 0 failed
  ```

要对真实后端做端到端测试，用合成栈：仓库根 `make up`。见
[deploy/](../../deploy/)。

<a id="cn-3"></a>

## 3. 技术栈

- Next.js 14（App Router）
- React 18 + TypeScript
- Tailwind CSS
- Plotly.js（heatmap、直方图）
- Zustand（state —— submit 表单走 store；只有 `mode` 持久化到 localStorage）
- React Dropzone（文件上传）
- tsx（TypeScript 测试 runner，devDep）

<a id="cn-4"></a>

## 4. 页面

| 路由 | 用途 |
|---|---|
| `/` | 首页：hero 图 + 四个入口卡片 |
| `/submit` | 提交新分析（按 mode 动态变形的表单） |
| `/tasks` | 用户任务列表（按邮箱或 task ID 搜） |
| `/tasks/[id]` | 任务详情：状态、stage、partial-result 链接 |
| `/tasks/[id]/visualize` | 结果可视化（heatmap + 直方图 + 排名表） |
| `/visualize` | 打开已有的 PMET 输出文件做可视化 |
| `/data` | 预计算数据集目录 |
| `/about` | 项目信息 |
| `/admin/login` | 管理员 token 登录 |
| `/admin/settings` | 管理员：notify-on-submit 开关 + sign out |

<a id="cn-5"></a>

## 5. Docker

```bash
docker build -t pmet-frontend .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://api:8000 pmet-frontend
```

合成栈里镜像由 `cd deploy && make build-images` 构建。本目录下任何
文件改了都得重建 —— 前端被 baked 进镜像，没 bind mount。快捷方式
是 `cd deploy && make rebuild-frontend`。

<a id="cn-6"></a>

## 6. 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | 浏览器把 `/api/...` 请求发到哪。合成栈里被覆写成相对路径，让 nginx 把 `/` 和 `/api/...` 都从同源代理。 |
