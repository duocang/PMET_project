# TODO

两批待办按时间分层。**最近一批（2026-05-04）**：3 方代码审查（我 + DeepSeek + GPT）+ MCP 浏览器实地验证后筛出来的安全/正确性/性能问题。**老的（2026-04-30）**：矩阵测试 72 个任务暴露的工作流问题，多数已修。

> 本文件聚焦"已知问题与改进路线"。"如何安装/使用"在 [README.md](README.md)，两者不重叠。

---

## 系统审查（2026-05-04）

3 方独立审查（我 / DeepSeek V4 pro / GPT 5.5）+ MCP browser 实地验证。每条都附"已 reproduce 的证据"。

### 当日汇总

| # | 问题 | 严重度 | 状态 / 实证 |
|---|---|---|---|
| [5](#issue-5) | ~~`DELETE /api/files/upload` 无鉴权可删 RESULT_DIR 任意文件~~ | 🔴 critical | ✅ **已修** — 合规 / 旧 exploit / 删 ZIP / 删 task JSON / 幂等 / `../` 穿越 6 案例全 pass |
| [6](#issue-6) | ~~admin login `next` open redirect~~ | 🔴 critical | ✅ **已修** — `//evil` / `https://evil` / `javascript:` / `/tasks` 4 vector 全 pass |
| [7](#issue-7) | ~~TaskQuickLook "Top-N 显著" 字母序非 p 序~~ | 🔴 数据正确性 | ✅ **已修** — 真 top 现在是 HSFA1E/HSFB2B (3.4e-38)，UI 验证 |
| [8](#issue-8) | ~~Use Example 116 MB FASTA 浏览器双向中转~~ | 🟡 公网体验 | ✅ **已修** — 客户端 220 MB → server-side **direct data path**（不 copy、不 symlink） |
| [9](#issue-9) | ~~`parseFloat(...) \|\| 1` 把 p=0 误转 1~~ | 🟡 防御性 | ✅ **已修** — `numOr / intOr` 包装，41760 行热图渲染 OK |
| [10](#issue-10) | ~~`resetSubmitForm` 死代码，提交后表单不清（含 email）~~ | 🟡 UX | ✅ **已修**（含审查后补 email 重置）— 真 SPA 重测 OK，单测 8/8 |
| [11](#issue-11) | ~~admin token 字符串 `==` 比较（计时攻击）~~ | 🟡 安全 | ✅ **已修** — `hmac.compare_digest`，5 case + UI 真 token 流程 |
| [11b](#issue-11b) | docker-compose 默认 `--reload` 进 prod | 🟡 部署决策 | ⏸ **不修默认** — 拆 prod compose 会破开发流；上公网时手动改 |
| [12](#issue-12) | ~~`/api/files/use-example` 无鉴权磁盘放大器（修 #8 引入）~~ | 🟡 公网限流 | ✅ **已修**（pmet.online 上线后）— session_token 闸门 + IP rate limit + direct data path |
| [13](#issue-13) | `/api/results` 默认 sort 把全部匹配行加载内存（修 #7 引入）| 🟡 大文件风险 | ⏳ **未修** — 39 k 行 ~10 MB OK；100 万行需换 `heapq.nsmallest` |
| [14](#issue-14) | ~~DELETE /upload 仍依赖 session_id secrecy（修 #5 后残留）~~ | 🟡 公网严格化 | ✅ **已修** — `X-PMET-Session-Token` header |
| [15](#issue-15) | ~~`use-example` symlink + writable `/app/data` 可被同名上传写穿覆盖原始数据~~ | 🔴 critical | ✅ **已修** — 不再创建 symlink/copy；compose `data` mount 改 `:ro` |
| [16](#issue-16) | ~~`POST /api/tasks` 未绑定 session_token，可伪造 task_id / 跨 session 路径~~ | 🔴 critical | ✅ **已修** — create-task 校验 token + path ownership + duplicate 409 + token 不落盘 |
| [17](#issue-17) | ~~`/upload` 无 token 鉴权 + 无 size cap + gzip 解压无上限~~ | 🔴 critical | ✅ **已修** — 三层闸：raw 200 MB / decompressed 500 MB / X-PMET-Session-Token 必须 |

12 修 + 1 决策不修 + 1 hardening backlog（#13）。下方各问题段落附"复现 / 修法 / 验证"详情。

---

<a id="issue-5"></a>

### ~~问题 5：`DELETE /api/files/upload` 无鉴权可删 RESULT_DIR 下任意文件~~ ✓ 已修

**复现**（2026-05-04）：
```bash
mkdir results/app/security_test/ ; echo data > .../critical.txt
curl -X DELETE "http://localhost:5960/api/files/upload?path=results/security_test/critical.txt"
→ {"deleted":"results/security_test/critical.txt"} HTTP 200
```
**爆炸半径**：任何在 `RESULT_DIR` 下的文件——别人 task 的上传 / 结果 ZIP（`results/<id>.zip`）/ task JSON 元数据（`results/tasks/<id>.json`）。攻击者只要知道 / 猜到路径就能删。

**修法**：[files.py:249-281](apps/pmet_backend/api/routes/files.py#L249-L281) 把 path 校验从"在 RESULT_DIR 下"收紧到精确匹配 `RESULT_DIR/<session_id>/upload/<filename>`：要求 `rel.parts == 3` 且 `parts[1] == "upload"` 且 `UPLOAD_SESSION_RE.match(parts[0])`。同时把 TOCTOU race 改为 idempotent（catch `FileNotFoundError` → 200 noop）。

**MCP browser 验证**（2026-05-04）：
- T1 旧 exploit `path=results/pwn_test/critical.txt` → **400** ✓
- T2 删别人 task ZIP → **400** ✓
- T3 删 task JSON 元数据 → **400** ✓
- T4 合规 `path=results/<session>/upload/genes.txt` → **200 deleted** ✓
- T5 重复删（idempotent）→ **200 noop:true** ✓
- T6 traversal `../../tasks/<id>.json` → **400** ✓
- 真实 UI 流程：`/submit?mode=intervals` → 点"使用示例" 加 motif.meme (8.1 KB) → 点 "移除" → dropzone 回到 idle 态 ✓

<a id="issue-6"></a>

### ~~问题 6：admin login `next` 参数 open-redirect~~ ✓ 已修

**复现**（2026-05-04）：访问 `http://localhost:5960/admin/login?next=//example.com` → 输入真实 admin token → 浏览器**真的跳到 `https://example.com/`**。
**爆炸半径**：钓鱼。攻击者发 `pmet.online/admin/login?next=//phish.example` 给管理员，admin 输完真 token，被引到攻击者控制的 "session expired, please re-login" 页面再钓一次。

**修法**：[admin/login/page.tsx:25-37](apps/pmet_frontend/app/admin/login/page.tsx#L25-L37) `next` 加白名单：必须 `startsWith('/')` 且 `!startsWith('//')` 且 `!startsWith('/\\')`，否则回退默认 `/admin/settings`。

**MCP browser 验证**（2026-05-04）：
| next | 期望落点 | 实测落点 |
|---|---|---|
| `//example.com` | `/admin/settings` | `/admin/settings` ✓ |
| `https://evil.com/x` | `/admin/settings` | `/admin/settings` ✓ |
| `javascript:alert(1)` | `/admin/settings` | `/admin/settings` ✓ |
| `/tasks` (合法) | `/tasks` | `/tasks` ✓ |

<a id="issue-7"></a>

### ~~问题 7：TaskQuickLook "Top-N 显著 pair" 不按 p-value 排序~~ ✓ 已修

**复现**（2026-05-04）：
```
GET /api/results/<task>?limit=10&p_adj_max=0.05
→ ABF1/ABF2 (p=1.05e-09), ABF1/ABF3, ABF1/ABF4, ... ABF1/AGL13 (字母序)
真 top（按 p_adj_bh 升序）应是: HSFA1E/HSFB2B (p=3.4e-38)
```
**爆炸半径**：QuickLook 给用户看的"最显著的 10 对"是文件出现序前 10 行，**不是真 top 10**。最显著 pair 可能埋在数千行后。**误导性产物**。

**修法**：[results.py:80-134](apps/pmet_backend/api/routes/results.py#L80-L134) 加 `sort: bool = True` 默认参数，filter 后 in-memory `sort(key=lambda kv: kv[0])` 再 paginate。memory 上限 ~25 MB（100k pair），可接受；同时新增 `sorted_by_p_adj_bh` 字段返回值，便于前端识别。`sort=false` 保留旧行为给特殊调用方。

**MCP browser 验证**（2026-05-04）：
- API 直查：`/api/results/phase1_.../?limit=10` → top 1 = HSFA1E/HSFB2B 3.41e-38 ✓
- `sort=false` 兼容：返回 ABF1/ABF2 字母序 ✓
- 任务详情页 `/tasks/phase1_0fb1357653a54a0b` "前 10 对显著 pair" 表格：HSFA1E/HSFB2B → HSFA6A/HSFB3 → ... 全部 HSF 家族最显著对 ✓

<a id="issue-8"></a>

### ~~问题 8：Use Example 把 100+ MB 的 demo FASTA / GFF3 通过浏览器中转~~ ✓ 已修（direct data path）

**复现**（2026-05-04）：`time curl -o - /api/demo/promoters/fasta` → 116 MB / 1.3s（本地 docker）。但 Use Example 流程是 `fetch → blob → File → multipart POST 116 MB`，**228 MB 浏览器双向**。公网 1 Mbps 用户：**16 分钟**等"加载示例"。

**修法**：选择性优化——大文件走 server-side direct reference，小文件保留客户端 fetch（小文件占带宽可忽略，且 GeneClusterFilter 需要真 File 解析 cluster）：
- 后端 `POST /api/files/use-example` 不再 copy / symlink 到 `RESULT_DIR/<task_id>/upload/`；它只校验 `session_token`，从 `DEMO_FILES` 表返回原始 `data/...` 路径和真实文件大小。Worker 后续直接读取 `data/reference/TAIR10.fasta` / `data/demos/...`。
- 2026-05-05 安全复查修正：放弃 symlink 方案。原因是 `upload/TAIR10.fasta -> data/reference/TAIR10.fasta` 这种链接如果留在可写 upload 目录里，后续同名普通上传会 follow symlink 写穿到 `/app/data`，有覆盖原始 demo/reference 数据的风险。
- Docker 侧把 API / worker / watchdog 的 `../data:/app/data` bind mount 改成 `../data:/app/data:ro`，把"应用数据只读"变成容器级约束。
- 实际效果：Use Example 没有浏览器中转、没有服务器复制、没有 upload 目录增量；用户看到的 stub File 大小仍取自原始 data 文件，UI 体验不变。
- 前端 [lib/api.ts:248-263](apps/pmet_frontend/lib/api.ts#L248-L263) 加 `fileApi.useExample(taskId, mode, slot)`。
- [FileUpload.tsx](apps/pmet_frontend/components/FileUpload.tsx) 新 prop `onUseExample?: () => Promise<void>` 走 server-side fast path（设 sentinel `__use_example__` 走 loadingUrl 显示 spinner，不 fetchAndUpload）。
- [submit/page.tsx](apps/pmet_frontend/app/submit/page.tsx) 加 `handleUseExample(slot)`：调 API → 构 stub File（`new File([], filename)` + `Object.defineProperty(stub, 'size', {value: response.size})`）→ 同时更新 `paths` + `files` 状态。FASTA / GFF3 / intervals MEME 用 `onUseExample`；genes / peaks / promoters MEME（chip picker）保留旧路径。

**验证**：
- 后端单测：`/use-example` 带真 token 返回 `data/demos/intervals/indexing/motif.meme`，且 `results/<sid>/upload/motif.meme` 不存在 ✓
- 后端单测：历史遗留 upload symlink 遇到同名上传时被替换为普通文件，不 follow 到 target ✓
- 前端 build：`handleUseExample` 仍用返回的 filename/size 构 stub File，`handleFileClear` 对 `data/...` 只清本地状态 ✓
- **节省**：promoters 一次完整 Use Example 流，从 ~440 MB 浏览器中转（FASTA+GFF3 各双向）→ **~0**，且服务器磁盘写入也为 0

<a id="issue-9"></a>

### ~~问题 9：`parseFloat(...) || 1` 把 p=0 误转 1~~ ✓ 已修

**复现**（2026-05-04）：`node -e "parseFloat('0')||1"` → `1`。但 grep 真 PMET 输出 `motif_output.txt`，**所有 p-value 都用科学计数法**（最小见过 `1.5e-43`），裸 `0` 实战不出现。
**爆炸半径**：实战零；如果未来代码改成输出裸 `0` 或用户 visualize 自定义 TSV，最显著行会被静默丢弃。

**修法**：[visualize/page.tsx:76-110](apps/pmet_frontend/app/visualize/page.tsx#L76-L110) 加 `numOr(value, fallback)` 和 `intOr(value, fallback)` 工具函数，`parseRow` 把 6 处 `parseFloat(x) || N` / `parseInt(x) || N` 全部换成 `numOr/intOr`。`Number.isFinite(n)` 把 0 和 1.5e-43 都放过、`abc` / `undefined` 才走 fallback。

**MCP browser 验证**（2026-05-04）：
- `node` sanity：`numOr('0',1)===0` ✓ `numOr('0.0e+00',1)===0` ✓ `numOr('1.5e-43',1)===1.5e-43` ✓ `numOr('abc',1)===1` ✓
- 真实数据：`/visualize` → 加载示例 PMET 结果（41760 行）→ 热图正常渲染 me-G1 / me-G2 cluster ✓ tsc + 生产 build 全 pass

<a id="issue-10"></a>

### ~~问题 10：`resetSubmitForm` 是死代码，提交后表单状态永不重置~~ ✓ 已修

**复现**（2026-05-04）：`grep -rn resetSubmitForm` 只在 `tests/test_settings_store.ts` 出现，生产代码 0 引用。`handleSubmit` 成功后只 `router.push(/tasks/<id>)`，zustand state 保留——回 /submit 看到上次的 species / 文件 / 参数还在。

**修法**：
1. [submit/page.tsx:423-433](apps/pmet_frontend/app/submit/page.tsx#L423-L433) `taskApi.create` 成功、`router.push` 跳转前加一行 `useSettingsStore.getState().resetSubmitForm()`。
2. [store.ts:141-167](apps/pmet_frontend/lib/store.ts#L141-L167) `resetSubmitForm` 把顶层 `email` 也并入清空范围（之前漏了——`email` 在 store 顶层、不在任何 `*ByMode` 里）。

**MCP browser 验证**（2026-05-04，**SPA-only**，无 page.goto 全页面 reload 干扰）：
- 流程：填 `user@example.com` + 三个槽 Use Example（intervals: FASTA 24 MB / MEME 8.1 KB / Peaks）→ 点"提交分析" → SPA `router.push` 到 `/tasks/pmet_ae7a6ec25467` ✓
- 关键：**点 nav 的"分析"链接**（Next.js `<Link>` SPA nav，不是 `browser_navigate=page.goto`）→ 邮箱真空白、3 个 dropzone idle ✓
- 单测 [test_settings_store.ts:116-134](apps/pmet_frontend/tests/test_settings_store.ts#L116-L134) 加 `email` 检查，8/8 pass

**注**：之前的 `browser_navigate` 全页面 reload 杀掉了所有 in-memory state，让 reset 的真实效果被掩盖；本次重测点 nav `<Link>` 走 React Router，纯内存路径，是真正的 SPA-stay 验证。

<a id="issue-11"></a>

### ~~问题 11：admin token 字符串 `==` 比较~~ ✓ 已修

[admin.py](apps/pmet_backend/api/routes/admin.py) `pmet_admin != config.ADMIN_TOKEN` 走 Python `!=`——理论可计时攻击。

**修法**：[admin.py:11-32](apps/pmet_backend/api/routes/admin.py#L11-L32) 加 `import hmac` + `_token_matches(candidate)` helper，内部用 `hmac.compare_digest(candidate, config.ADMIN_TOKEN)` 常量时间比较。`require_admin` / `login` / `me` 三处全部走 `_token_matches`，统一一份 truthy 检查；short-circuit `if not candidate or not config.ADMIN_TOKEN: return False` 防 None / 空配置。

**验证**（2026-05-04）：
- T1 错 token → 401 ✓
- T2 长度不同的错 token → 401（compare_digest 等长比较 + 短路保护）✓
- T3 真 token → 200 cookie 正确发回 ✓
- T4 用 cookie 调 `/api/admin/me` → `is_admin: true` ✓
- T5 空 cookie → `is_admin: false` ✓
- MCP browser：`/admin/login` 真 token → 跳到 `/admin/settings` ✓

<a id="issue-11b"></a>

### 问题 11b：docker-compose 默认带 `--reload` 🟡 部署决策（不修）

[deploy/docker-compose.yml:43](deploy/docker-compose.yml#L43) `uvicorn ... --reload` 是**有意的 dev 行为**，配合 backend bind-mount 让代码改动 5 秒内生效。本地 docker 跑没问题。**公网部署人需手动改这行**为 `gunicorn -k uvicorn.workers.UvicornWorker -w 4` 之类。

**为什么不动默认**：拆 `docker-compose.yml`（prod）+ `docker-compose.override.yml`（dev）会破坏现有 `make up` 一行起服的开发体验，对所有本地用户增加摩擦，仅惠及公网部署一种场景。**留给真上公网时再决定**。
**Workaround**：上线前把那一行改成 `--workers 4 --no-access-log`，或维护一份 `docker-compose.prod.yml`。

### Hardening backlog（已修批次的延伸）

#12 / #13 / #14 是修问题 5 / 7 / 8 时的收紧项。**pmet.online 上线后 #12 + #14 已落地**（共享同一个 session_token 机制），#13 仍是 backlog（39 k 行实战 OK，等真碰到百万行任务再做）。#15 / #16 是 2026-05-05 安全复查新增的问题，分别修掉 symlink 写穿和 create-task 所有权断点。

<a id="issue-12"></a>

#### ~~问题 12：`/api/files/use-example` 无鉴权磁盘放大器~~ ✓ 已修（pmet.online 上线触发）

[files.py:152-191](apps/pmet_backend/api/routes/files.py#L152-L191) 修 #8 时新加的端点。最初实现用 `shutil.copy2` 真复制，所以任何人 POST 一次就让服务器拷一份 116 MB demo FASTA 到新 session 目录。原 `/api/files/upload` 也无鉴权，但攻击者至少要自己出上传带宽；这里**服务器替他出带宽 + 出磁盘**——典型 disk-amplification DoS。
**触发模型**（历史 cp 实现）：1 POST = 服务器 `cp` 116 MB；100 POST/min = 11 GB/min 磁盘消耗。

**修法**：三层闸门 + 一个根本性优化——
1. [files.py:14-87](apps/pmet_backend/api/routes/files.py#L14-L87) 新增 module-level `_SESSIONS` dict + `_SESSIONS_LOCK` + `_SESSION_TTL_SECONDS=3600`，配 `_validate_session(session_id, token)` 用 `hmac.compare_digest`。
2. [files.py:226-263](apps/pmet_backend/api/routes/files.py#L226-L263) 新端点 `POST /api/files/issue-session`：返 `{session_id, session_token, expires_in}`；自带 sliding-window 每 IP rate limit（10/min）。
3. `/use-example` 强制带 `session_token`，错 token / token 过期 / 跨 session 全 401（缺字段由 FastAPI 返回 422）。
4. **根本优化（2026-05-05 修正）**：底层不再 `copy2`，也不再 `symlink`。demo 文件是只读服务器资产，直接返回 `data/...` 原始路径给任务元数据即可。这样磁盘增量为 0，也消除了 symlink 被同名上传写穿覆盖 `/app/data` 的风险。
5. [lib/api.ts:227-268](apps/pmet_frontend/lib/api.ts#L227-L268) 加 `fileApi.issueSession()`；`useExample()` / `deleteUpload()` 接收 token 参数。
6. [submit/page.tsx](apps/pmet_frontend/app/submit/page.tsx) mount 时 `fileApi.issueSession()`，token 存内存（不入 localStorage——重启浏览器就要换 session，token harvest 寿命有限）；`handleSubmit` 加 `if (!uploadSession)` guard 防 race。
7. [deploy/docker-compose.yml](deploy/docker-compose.yml) 把 API / worker / watchdog 的 `/app/data` mount 改成 read-only (`:ro`)。

**验证**：
- T1 错 token call /use-example → **401**（缺少 `session_token` form field 时 FastAPI 先返回 422）
- T2 issue-session → 200 `{session_id, session_token: 64-hex, expires_in: 3600}`
- T3 真 token call /use-example → **200**，返回 `data/demos/intervals/indexing/motif.meme`
- T4 同 session 重复 → **200**，仍返回同一个 `data/...` path（无磁盘写入）
- T5 用 SID-A 的 token 操作 SID-B → **401**
- T6/T7 DELETE /upload 同样 token 闸门 → 401 / 200 各对
- **磁盘实测目标**：Use Example 不再触碰 `results/<sid>/upload/`，磁盘增量为 0；`data` mount 在容器内只读。
- 本次 2026-05-05 已由后端 unittest 锁定 direct data path / no upload symlink；compose `:ro` 需容器重建后生效。

<a id="issue-15"></a>

#### ~~问题 15：`use-example` symlink + writable `/app/data` 可写穿覆盖原始数据~~ ✓ 已修

**复现模型**（2026-05-05 代码审查）：旧方案把示例文件 symlink 到 `results/<sid>/upload/<name>`。如果用户随后上传同名文件，`destination.open("wb")` 会 follow symlink，把内容写到 symlink target，也就是 `/app/data/...` 原始 demo/reference 文件。compose 里 `/app/data` 当时是可写 bind mount，风险成立。

**修法**：
- `/use-example` 不再创建 symlink/copy，只返回 `data/...` 原始路径。
- 上传写入前会移除目标位置的历史遗留 symlink，并用 `O_NOFOLLOW` 兜底，防止旧 session 同名上传继续 follow link。
- 清除按钮遇到 `data/...` path 时只清前端状态，不调用 `DELETE /upload`。
- compose 三个后端相关容器的 `../data:/app/data` 全部改成 `../data:/app/data:ro`。

**残留**：生产机需 `docker compose up -d --force-recreate api worker liveness-watchdog` 或等下一次重建，让 `:ro` mount 真正生效。

<a id="issue-16"></a>

#### ~~问题 16：`POST /api/tasks` 未绑定 session_token，可伪造 task_id / 跨 session 路径~~ ✓ 已修

**复现模型**（2026-05-05 代码审查）：`/api/files/use-example` 和 `DELETE /upload` 已经要求 session token，但最终的 `POST /api/tasks` 仍信任客户端传来的 `task_id` 和 `genes_file/fasta_file/gff3_file/meme_file`。绕过前端直接 POST 时，攻击者可以尝试：
- 用已知/猜到的 `task_id` 覆盖旧 task metadata。
- 让自己的 task 读取别人 `results/<other>/upload/...` 下的输入文件。
- 把 task 输入指向任意 `data/...` 文件，而不是当前槽位允许的 app demo。

**修法**：
- 新增 `api/upload_sessions.py`，把 session store 从 `files.py` 抽成共享模块；`files.py` 和 `tasks.py` 共用同一份 token 校验。
- `TaskCreate` 增加 `session_token`；前端提交 task 时随 `task_id` 一起发送，但后端 `model_dump(exclude={"session_token"})`，不把 token 写入 task JSON。
- `POST /api/tasks` 现在要求：`task_id` 存在且符合 session id regex、`session_token` 匹配、`tasks/<task_id>.json` 不存在（否则 409）。
- 创建前逐项校验输入路径：用户上传文件必须 resolve 到 `RESULT_DIR/<task_id>/upload/`；app demo 必须是 `DEMO_FILES` 中同 slot 白名单路径；`premade_index` 必须在 `data/precomputed_indexes/` 下。
- 校验通过后 consume session，防止同一个 token 重复创建 task。

**验证**：
- 后端单测新增 `test_task_creation_security.py`，覆盖成功提交不落盘 token、坏 token 401、跨 session 上传路径 400、错误 slot demo path 400、重复 task id 409。
- `test_upload_routes.py + test_task_creation_security.py` 共 19 case 全 pass。

<a id="issue-13"></a>

#### 问题 13：`/api/results` 默认 sort 收集全部匹配行进内存 🟡 大文件风险

[results.py:80-134](apps/pmet_backend/api/routes/results.py#L80-L134) 修 #7 时改成"先 filter+collect 后 sort+slice"。一个 39047 row 的 task 大概 ~10 MB Python 对象——OK；100 万 row → ~250 MB。`p_adj_max=1` + `sort=true` 默认的请求会把整个文件 + 所有行加载到内存。
**修法**：换成 `heapq.nsmallest(limit, generator, key=lambda r: r.p_adj_bh)`——内存恒定 `O(limit)`，I/O 仍是单次扫描。同时保留 `sort=false` 走原 streaming-pagination 路径供大数据全量分页用。

<a id="issue-14"></a>

#### ~~问题 14：DELETE /upload 仍依赖 `<session_id>` secrecy~~ ✓ 已修

修 #5 后已收紧到 `RESULT_DIR/<session_id>/upload/<filename>`。但任何拿到 `<session_id>`（48-bit 随机 hex）的人仍可未经鉴权地删除该 session 的 upload 文件。

**修法**：跟 #12 共享同一个 session_token 机制——`DELETE /upload` 通过 `X-PMET-Session-Token` header 接收 token，`validate_upload_session(parts[0], session_token)` 校验失败 401。前端 `fileApi.deleteUpload(path, sessionToken)` 同步加 header。
**公网部署后实际行为**：知道 path 的攻击者还需要同时知道**配套的 64-hex token**，而 token 只在原页面 mount 那一次返回（HTTP body 不入 localStorage、不进 cookie），跨浏览器/跨 tab 不可获取。

**验证**：
- 无 header → **401 invalid token**
- 旧 query 参数 `?session_token=...` → **401**（不再接受，避免 token 进 URL / access log）
- `X-PMET-Session-Token` header 真 token → **200 deleted**

**前端行为**：用户上传文件仍调用 token 化 DELETE；Use Example 的 `data/...` path 只清本地状态，不再走 DELETE。

<a id="issue-17"></a>

#### ~~问题 17：`/upload` 无 token 鉴权 + 无 size cap + gzip 解压无上限~~ ✓ 已修

**复现**（2026-05-05）：
- nginx `client_max_body_size 500M`，应用层零 size cap
- `_store_upload` 的 gzip 路径用 `shutil.copyfileobj(gzipped, buffer)` 流式解压**无累计上限**
- 实测：`dd if=/dev/zero bs=1024 count=102400 | gzip -9` → 100 KB 输入 / **100 MB 输出**（1024× 放大）。1 KB 全零 gzip 更夸张
- `/upload` 端点无任何 token 鉴权——匿名 IP 可直接 POST 任意 task_id 到 `temp_<ms>` 临时目录

**攻击模型**：
- 匿名 anon raw POST 500 MB → 1 个请求耗 500 MB 磁盘
- 匿名 anon gzip bomb 100 KB → 100+ MB 解压；1 个 fd 耗资源不对等
- 100 个并发匿名请求 → 50 GB / 几分钟内打满磁盘

**修法**：三层闸门——
1. [files.py:42-49](apps/pmet_backend/api/routes/files.py#L42-L49) 加常量：`_UPLOAD_MAX_BYTES = 200 MB`（覆盖最大合法输入 TAIR 116 MB + 余量）和 `_DECOMPRESSED_MAX_BYTES = 500 MB`，1 MiB chunk 流式 copy。
2. [files.py:_copy_capped](apps/pmet_backend/api/routes/files.py) 新 helper：流式 read + 累计字节计数，超 cap 立刻 raise `_UploadTooLarge` 中止；caller catch 后 `unlink(missing_ok=True)` partial dest。替代 `shutil.copyfileobj`（后者无 cap）。
3. [files.py:upload_file](apps/pmet_backend/api/routes/files.py) 端点签名加 `task_id: str = Form(...)` 必需 + `session_token: Header(alias="X-PMET-Session-Token")`，`validate_upload_session` 失败 401。`/upload-multiple` 同样 gate。
4. 前端 [lib/api.ts:fileApi.upload](apps/pmet_frontend/lib/api.ts) 接收 `sessionToken` 必传参数，发到 `X-PMET-Session-Token` header；[submit/page.tsx](apps/pmet_frontend/app/submit/page.tsx) 6 处 `fileApi.upload` 调用全部传入 `uploadSessionToken`。

**curl 攻击验证**（2026-05-05）：
- 匿名 `POST /upload`（无 token）→ **401 Invalid or expired session token** ✓
- 597 KB gzip → 期望解压 600 MB → **413 "decompressed-size cap"** + partial dest unlinked ✓
- 200 MB+1 raw bytes → **413 "size cap"** ✓

**单测**：
- `test_upload_requires_session_token_header`（无 header / 错 token / 跨 session token / 真 token 四态）
- `test_upload_rejects_oversize_raw`（>200 MB → 413）
- `test_upload_rejects_gzip_bomb`（1 KB gzip → 600 MB 期望 → 413）
- 旧 fixtures 全部更新通过 token gate；23/23 单测全 pass

**MCP browser**：peaks.txt（339 B）走 client fetch+upload 路径，`X-PMET-Session-Token` header 正确发出，POST 200。

---

### 已验证为伪问题（不修）

| Agent 报警 | 实测发现 |
|---|---|
| Plotly chunk 4.5MB 压垮 /visualize 首屏 | **lazy-loaded**——只在用户加载示例后才拉，初始访问只 ~150 KB |
| `_load_*` 配置每次重读使 estimate 慢 | 实测 25-30 ms/次，submit 一次会话累积 ~500 ms，**被 debounce 覆盖、用户无感** |
| `/admin/settings` 未登录闪现 UI | **页面有 `if(loading) return <Loading/>` 守卫，不闪现** |
| Watchdog kill race | 已做 status 检查 + 重读 JSON 守卫 |

---

## 矩阵测试（2026-04-30）

> 4-30 矩阵测试（72 个任务横扫 heat / salt / cell-type 多组基因列表）暴露的工作流问题，多数已修。保留作历史记录 + 后续 backlog 跟踪。**下方所有同级章节（目录 / 问题 1-4 / 优先级建议 / 其它 backlog）均属于这一批。**

## 目录

- ~~[问题 1：基因列表 cluster 多时，画图把整个任务拖死](#问题-1已修)~~
- ~~[问题 2：CIS-BP2 这种大库，正常用户也会撞超时](#问题-2已修)~~
- ~~[问题 3：明知挂了还要机械重试 10 分钟](#问题-3)~~
- ~~[问题 4（meta）：`task.status` 是个骗子](#问题-4-meta)~~ — 短期 + 长期都已修
- [优先级建议](#优先级建议)
- [其它 backlog（节奏未到）](#其它-backlog节奏未到)

---

## ~~问题 1（已修）~~

### ~~基因列表 cluster 多时，画图把整个任务拖死~~

> ~~已在 commit `4fd9aa2` 修复（fix(heatmap): cap motifs, size figures dynamically）。下面整段保留作回顾。~~

~~**问题在哪产生**~~

~~`scripts/r/heatmap.R:146` 写死："每 2 个 cluster 就给图加 10 inch 高度"。~~`hei <- 10 * ceiling(length(clusters)/2)`~~。所以 25 个 cluster → 图尺寸 130 inch。`ggsave` 内置 50 inch 的安全闸（防止误手生成 GB 级 PNG），超过直接 abort。~~

~~**实际影响**~~

~~- 用户提交"分了很多组"的基因列表（如 `random_genes_topN.txt` 含 25+ cluster）~~
~~- 后端 fimo + pair 富集都跑完了，`motif_output.txt` 已经写到磁盘上了~~
~~- R 准备画 heatmap → 触发 50 inch 限制 → R 异常退出 → bash 工作流退出码非零 → celery 标记任务"失败"~~
~~- 用户在网页看到红色 Failed、下载按钮 404，以为分析挂了——其实数据早就完整了，只是图没画出来~~

~~**怎么修的**~~

~~比一行 `limitsize = FALSE` 更彻底的三层方案，避免"绕过 50 inch 限"换来"几 GB 不可读 PNG"的次生问题：~~

~~1. **R 端 motif 自适应选择**（`scripts/r/process_pmet_result.R`）：每个 cluster 按 `sum(-log10(p_adj))` 给 motif 打分，配额 = `max(3, floor(cap / n_clusters))`，并集超 cap 时按"出现 cluster 数 + 全局分数"二次裁剪。最终 motif 总数受 `max_motifs_in_plot`（默认 30）限制。~~
~~2. **R 端动态尺寸**（`scripts/r/heatmap.R`）：图宽高从实际 motif 数 + panel 布局推算（约 0.18 inch / cell + 边距），硬上限 `max_fig_inches`（默认 40 inch），`limitsize = FALSE` 兜底。~~
~~3. **bash 端 try-catch**（`scripts/workflows/{pair_only,promoter,intervals}.sh`）：`Rscript` 失败仅打 `print_orange` 警告，pairing 数据是核心产物，画图是锦上添花，不让锦上添花拖死任务。~~

~~**残留**~~：~~`max_motifs_in_plot` 默认 30 的合理性、scoring 用 `sum` 还是 `max`，等真实使用反馈后再调。~~

---

## ~~问题 2（已修）~~

### ~~CIS-BP2 这种大库，正常用户也会撞超时~~

> ~~已修。修法比 TODO 原方案 (拉 celery hard time limit) 更聪明：用"心跳判活"代替"硬墙时长"，配合前端 runtime estimate + progress 反馈。残留：长阶段内细粒度 progress emit 仍待加，见下方"其它 backlog"。~~

~~**问题在哪产生**~~

~~CIS-BP2 motif 库 ~2330 个 motif，pair 检验是 motif 两两组合 → 约 270 万 pair 要算。在 2 CPU 的 docker 容器里单任务跑 8–10 分钟。celery 默认 soft time limit 不够用，运行时 watchdog 也撞墙。~~

~~**实际影响**~~

~~- 用户在 dropdown 里完全合法地选了 Arabidopsis + CIS-BP2（这是 web 提供的选项）~~
~~- 起码 1/3 概率撞超时~~
~~- 用户看到 Failed 不知道为什么——他没做错任何事，是系统配额没给够~~

~~**实际怎么修的**~~

~~两层组合，避免了简单"拉高 time limit"带来的"分不清正常长跑和卡死"问题：~~

~~1. **Liveness watchdog（独立容器）** —— `apps/pmet_backend/worker/watchdog.py` + `deploy/docker-compose.yml` 新增 `liveness-watchdog` service：~~
   ~~- 不靠 wall-clock cap，靠扫 `results/app/<id>/progress.json` 的 mtime 判活；任务在持续 emit progress 就一直活着，跑 30 分钟也不被杀~~
   ~~- 真正"卡死"超过 `LIVENESS_TIMEOUT_SEC`（默认 900s，env: `PMET_LIVENESS_TIMEOUT_SEC`）才 process-tree-kill 整个 bash 子进程树并 mark failed~~
   ~~- 跟 worker 同 PID namespace（`pid: service:worker`），psutil 能看见并 SIGTERM/SIGKILL 整个进程树~~
   ~~- 跑在独立容器，即使 celery worker slot 全被卡死任务占满，watchdog 仍能动手解锁~~
   ~~- 配置：`apps/pmet_backend/config.py` 加 `LIVENESS_TIMEOUT_SEC` 字段~~
~~2. **Runtime estimate + progress 反馈（commit `5c64e63`）** —— 前端 submit 页面在估算超阈值时给"这个库较大"友好提示；任务详情页基于 `progress.json` 实时显示阶段进度；`scripts/lib/progress.sh` + 三个 workflow sh 在 stage 边界 emit 心跳；`data/configure/runtime_calibration.json` 给 estimate 模型校准。~~

~~**残留**~~：~~progress 当前只在 stage 边界（indexing→heterotypic→heatmaps）emit，单 stage 内部（如 CIS-BP2 一次 pair test）就要 ~10 分钟，所以 watchdog 阈值不得不保守地设 900s。等内层循环（FIMO 每 N 个 motif、pair test 每 N% 进度、heatmap 渲染前）也加心跳后，阈值可降到 ~300s 不会误杀。详见"其它 backlog → Liveness watchdog 细粒度心跳"。pair 算法层粗筛（10× 速度）仍是 P3 长期项。~~

---

## 问题 3

### ~~明知挂了还要机械重试 10 分钟~~ ✓ 已修

**问题在哪产生**

celery 默认：任务抛异常 → 60 秒后自动重试。但有些异常注定永远不会成功（典型：`No genes match the universe`，gene list 跟物种 universe 完全不交集），worker 仍机械重试好几轮才认输。

**实际影响**

- 一个 worker slot 被一个注定失败的任务占着 ~3 分钟（实际是 `max_retries=3 × default_retry_delay=60`，而非标题写的 10 分钟）
- API 那边其实立刻返回 failed 状态——前端显示是对的——但 worker 资源被白白占用
- 多个用户同时撞这种错时，正常任务排队

**已落地** ✓

`apps/pmet_backend/worker/tasks/pmet.py` 的 `NON_RETRYABLE_ERROR_SNIPPETS` 从 6 条扩到 13 条，**真实错误字面值**全部落点到源码里 grep 出来，不靠记忆：

| 来源 | 子串 | 触发场景 |
|---|---|---|
| `scripts/workflows/{pair_only,promoter,intervals}.sh` | `the input list match` | 基因/区间列表跟物种 universe 不交集（公共子串覆盖三种 workflow 变体） |
| 同上 helper `check_file` | `missing or empty` | 用户上传的 gene/FASTA 文件不存在或空 |
| `pair_only.sh` | `Index dir not found` / `Index fimohits/ directory missing` | 选错物种 → precomputed 索引找不到 |
| `promoter.sh:213` | `Chromosome name mismatch` | 上传的 FASTA + GFF3 染色体命名不一致 |
| `core/pairing/src/utils.cpp` | `not found in promoter lengths file` / `No gene clusters found` | C++ pairing 引擎报基因 ID 不在 universe / 空簇 |

实现细节：保留 substring 匹配机制不动（已经在用、改成正则会大动），只扩列表 + 加分组注释 + 加维护提醒（修改这些源码 message 时要同步本列表）。

单测 `tests/unit/test_error_classification.py`：
- `PERMANENT_FIXTURES` 9 条（用户输入类）+ 4 条（已有的环境类）= 13 条 → 全部应分类为不重试
- `TRANSIENT_FIXTURES` 8 条（network reset / disk I/O / redis unavailable / OOM / segfault / 空字符串等）→ 全部应分类为重试
- wrapped 形式（`Command failed: ...` 前缀，executor.py 实际包装格式）也要正确识别
- 列表去重保护

每条 fixture 的 key 是「场景标签」，value 是从源码 grep 出来的真实错误字面值——以后哪天有人改了 bash / cpp 里的 message，本测试**第一时间** fail 提醒同步更新 snippet。

**用户侧体感**：失败邮件从 ~3 分钟后到达提前到 ~几秒后；UI 不再来回闪 running/failed。**运维侧**：worker slot 不再被注定失败的任务占着，队列吞吐显著改善（N 个错任务 3N 分钟 → ~N×10 秒）。

---

## 问题 4 (meta)

### `task.status` 是个骗子

**问题在哪产生**

任务在数据库里只有一个 `status: failed | completed | running` 字段，但实际 pipeline 有 fimo 扫描、pair 富集、写结果文件、画图等好几个阶段。任意阶段挂了都算 failed——但前面阶段的产物已经在磁盘上了。

**实际影响**

- 从 web 上看不出"产物有没有部分生成"
- 矩阵测试和 manifest 重建脚本都被骗——把一批"假 fail"记成"完全失败"，但里面相当一部分只是 heatmap 失败、`motif_output.txt` 完整可用
- 信任 API status 字段的所有 caller（poller、监控、外部脚本）都被坑

**短期方案** ✓ 已修

- ~~一次性 backfill 脚本：扫 `results/app/<id>/pairing/motif_output.txt` 是否存在，重建 manifest（已写在 `tmp_cli/fix_manifest.sh`）~~ — 矩阵测试当时用过，把假 fail 的 23+9 个任务正确翻成 success
- ~~**生产 API**~~ ✓ 已落地：
  - ~~`apps/pmet_backend/api/routes/tasks.py` 加 `_locate_motif_output(task_id)` helper 和 `partial_result_link` 字段~~
  - ~~`GET /api/tasks/{id}`：当 `status==failed` 且 `<task>/pairing/motif_output.txt` 非空时，返回 `partial_result_link = /api/tasks/{id}/partial-result`（status 仍是 failed，失败本身依然可见）~~
  - ~~新端点 `GET /api/tasks/{id}/partial-result`：直接 stream `motif_output.txt`，filename 写成 `<task_id>_motif_output.txt`，MIME 用 `application/octet-stream` 强制下载（避免 Chrome 对 `text/tab-separated-values` 内联渲染）~~
  - ~~前端任务详情页（`apps/pmet_frontend/app/tasks/[id]/page.tsx`）在红色 Error 块**上方**单独显示一块 amber/琥珀色 banner（"Partial result available" 标题 + 解释文 + 下载链接），`<a download="…txt">` 属性强制走文件下载流而不是页面跳转~~
  - ~~单测在 `tests/unit/test_partial_result_link.py`（10 case，覆盖 helper + 路由 + 边界）~~
- **遗留（独立问题，不属于"task.status 是个骗子"）**：实测 `phase2_2f50fd9abbdc4c17/pairing/motif_output.txt` 是 **993 MB / 640 万行**。`curl` 能完整拉到，但浏览器超大文件下载体验差。**这是独立的"超大文件 UX"问题**，挪到 [其它 backlog → partial_result_link：GB 级文件下载体验](#partial_result_link-gb-级文件下载体验)。

**长期方案** ✓ 已修

把 status 拆开。**没改持久化字段**（避免 enum 迁移），而是在 `GET /api/tasks/{id}` 里附加一个**文件系统派生**的 `stages` 数组 + `warnings` + `effective_status`：

```jsonc
{
  "status": "failed",                          // 持久化字段，保留原值
  "effective_status": "failed",                // UI 用，可能是 completed_with_warnings
  "stages": [
    { "name": "indexing", "state": "skipped", "note": "uses precomputed index" },
    { "name": "pairing",  "state": "completed" },
    { "name": "heatmap",  "state": "skipped", "note": "rendering failed; motif_output.txt is complete" },
    { "name": "zip",      "state": "skipped", "note": "late-stage failure; partial result still available" }
  ],
  "warnings": [
    "heatmap: rendering failed; motif_output.txt is complete",
    "zip: late-stage failure; partial result still available"
  ]
}
```

实现：

- `apps/pmet_backend/services/stage_status.py`：`infer_stages(task_meta, task_dir)` 通过扫 `<task>/indexing/universe.txt`、`<task>/pairing/motif_output.txt`、`<task>/pairing/plot/heatmap*.png`、`<task>.zip` 等 FS 证据派生每个阶段的状态。state ∈ `{pending, running, completed, failed, skipped}`。`derive_warnings` / `derive_effective_status` 派生 UI 用字段。**纯函数，I/O 限于 stat / glob，每次 GET 都跑也很便宜。**
- `apps/pmet_backend/api/routes/tasks.py`：`GET /tasks/{id}` 附加 `stages / warnings / effective_status`，**`status` 字段不动**——worker 仍是它的权威。
- `apps/pmet_backend/api/models/task.py`：`TaskResponse` 加 `stages: list[dict]`、`warnings: list[str]`、`effective_status: str`。
- 前端 `apps/pmet_frontend/app/tasks/[id]/page.tsx`：在 task header 卡片**最上方**（status badge 之下、partial-result banner 之上）渲染流水线 timeline —— 4 个胶囊（建索引 → 配对 → 绘图 → 打包），按 state 着色（绿✓/红✕/琥珀⊘/灰○/蓝◔/灰↻）。`warnings` 列在下方作要点说明。translations 中英两版。**位置故意放最上方**：错误时第一眼看到的不是红色 traceback，而是结构化的"哪步崩了 + 是否还有东西能拿"。
- **`precomputed` 是独立的 state**（不和 `skipped` 复用）—— promoters_pre 的 indexing 阶段是设计上跳过（用预计算索引），不应该被涂成"warning"色。后端 `infer_stages` 直接返回 `state="precomputed"`，前端用中性灰色 + ↻ 图标渲染，和 amber 的 `skipped`（绘图/打包失败）视觉上区分。`derive_warnings` 不把 `precomputed` 当 warning。
- **`partial_success` 是 `effective_status` 的另一个合成值** —— 当 `persisted_status==failed` 但 pairing 阶段产出了 `motif_output.txt`（heatmap 或 zip 崩了但数据还在），`derive_effective_status` 返回 `partial_success`。前端 badge 改用 `effective_status` 渲染：`partial_success` 走琥珀色 / `completed_with_warnings` 走绿底+琥珀 ring，区别于硬红的 `failed`。**这避免 user 在搜索任务进来时第一眼看到红 badge 把"配对其实成功"的真相盖过。**
- **错误块默认折叠** —— 前端 `<details>` + `summarizeError` 启发式抽取首条 `Error` 行，灰底 / xs 字号 / 单 ⚠ 图标。展开后 traceback 在 `max-h-60 overflow-auto` 滚动框里。视觉上从"红色铺满"降级为"一行灰色注释 + 可展开"，把 banner 高度让给真正有用的 stages timeline 和 partial-result download。
- 单测 `tests/unit/test_stage_status.py`：13 个 case，覆盖 happy path、promoters_pre 索引 `precomputed`、partial-result 路径、universe mismatch、index-side fail、running mid-pipeline、cancelled mid-run、`completed_with_warnings` 派生、`partial_success` 派生（pairing OK + persisted=failed）、`pairing` 真失败仍是 `failed`、running 透传。

这同时也是问题 1 的根本治法——status 拆细后，画图失败再也不会让人误以为任务挂了。

**邮件分发改造（status-aware mail dispatch）** ✓ 已修

光在 UI 上把 `partial_success` 露出来不够——很多用户根本不开页面，只看完成邮件。worker 那一侧的邮件模板原本只有「成功 / 完全沉默」两条路径，硬失败连邮件都不发。改造完成后：

- `apps/pmet_backend/services/mail.py`：
  - `send_result_notification` 接受可选 `warnings` 参数；非空时主题加 `(with notes)` 后缀，badge 渲染 `Completed (with notes)`，body 多一个 amber `Notes:` 块。`completed_with_warnings` **不再单独走分支**，而是合并到 `completed` 邮件，避免噪音翻倍（用户的 a 决议）。
  - 新增 `send_partial_result_notification(email, partial_link, error_summary, warnings, task_meta)`：主题 `PMET partial result available: <id>`，badge `Partial success`，按钮指向 `/api/tasks/<id>/partial-result`（直接 stream `motif_output.txt`，不走 zip），同时列错误摘要 + warnings 清单。`partial_link` 为空时降级成「未配置」提示而不是发空按钮。
  - 新增 `send_failed_notification(email, error_summary, task_meta)`：主题 `PMET task failed: <id>`，badge `Failed`，body 含错误摘要框 + Common-causes 排查清单（基因 ID / FASTA / 索引 / 物种）。**填补了硬失败完全沉默的洞**（用户的 b 决议）。
- `apps/pmet_backend/worker/tasks/pmet.py`：
  - 成功路径：跑 `infer_stages` + `derive_warnings`，把 warnings 传给 `send_result_notification`。
  - 失败路径（重试用尽后）：跑 `derive_effective_status("failed", stages)`。`partial_success` → `send_partial_result_notification`（带 `_build_partial_result_link` 派生的下载 URL + `_summarize_error` 抽出来的首条错误行）；其它 → `send_failed_notification`。**邮件失败本身不能再掩盖原异常**——整段包在 try/except 里只 print。
  - `_build_partial_result_link`：`urlparse(NGINX_LINK)` 取 scheme+netloc，拼 `/api/tasks/<id>/partial-result`；NGINX_LINK 空或不可解析则返回空串。
  - `_summarize_error`：和前端 `summarizeError` 同款启发式（`Error...` / `! ...` / `Command failed...` / 首行），最多 200 字符。
- 单测 `tests/unit/test_mail_dispatch.py`：9 个 case。`patch.object(MailService, "_send_email")` 截获 `(to, subject, body)` 三元组，断言主题文案 / 下载链接 / `motif_output.txt` 字样 / Notes 块 / Common-causes 检查表 / 不可解析 NGINX_LINK 兜底。**SMTP 完全 stub，跑在 tests/unit/run.sh 里 < 1 秒**。

至此持久化 status 不变，UI 看到的 `effective_status` 一致，邮件内容也按相同分类落到用户邮箱——三条路径对齐。

---

## 优先级建议

| 优先级 | 修什么 | 工作量 | 影响 |
|---|---|---|---|
| ~~P0~~ | ~~问题 1：R 端动态尺寸 + bash try-catch~~ | ~~半小时~~ | ~~~25% 假 failed 立刻翻为 success~~ ✓ commit `4fd9aa2` |
| ~~P0~~ | ~~问题 2：celery time limit 调高 + 前端预警~~ | ~~1–2 小时~~ | ~~CIS-BP2 用户不再无故失败~~ ✓ liveness-watchdog 容器 + commit `5c64e63`（runtime estimate / progress） |
| ~~P1~~ | ~~问题 4 短期：`partial_result_link` API + 前端按钮~~ | ~~2–3 小时~~ | ~~历史 task 的部分产物可下载~~ ✓ 已修 + 单测 (`tests/unit/test_partial_result_link.py` 10 case) |
| ~~P1~~ | ~~问题 3：permanent vs transient 异常分类~~ | ~~1–2 小时~~ | ~~worker 资源利用率~~ ✓ 扩了 NON_RETRYABLE_ERROR_SNIPPETS（6→13 条）+ 单测 (`test_error_classification.py` 4 case / 17 fixture) |
| ~~P2~~ | ~~问题 4 长期：status 字段拆分 + 前端配套~~ | ~~半天~~ | ~~长期 UX、监控可信度~~ ✓ FS 派生 stages + warnings + 前端 timeline + 单测 (`test_stage_status.py` 11 case) |
| ~~P3~~ | ~~问题 2 算法：pair 粗筛（MinHash prefilter）~~ | ~~0.5–1 天~~ | ~~大库 runtime~~ ✓ 算法 + 集成 + 校准全部落地，但 **CIS-BP2 上没找到安全默认值**，最终 ship 成 opt-in 开关。校准结论 + 数据见 [docs/perf/minhash_calibration.md](docs/perf/minhash_calibration.md) |

> ~~一次性 manifest 重建脚本（`tmp_cli/fix_manifest.sh`）已写，矩阵测试时用过；问题 4 短期 API 修完后即可丢弃。~~

---

## 其它 backlog（节奏未到）

源自原 TODO.md，按主题归并、保留要点：

### partial_result_link：GB 级文件下载体验

短期 `/api/tasks/<id>/partial-result` 直链对常规任务（motif_output 在 KB-MB 级）够用；当 random_genes_topN 这类多 cluster + 大 motif 库时，文件能涨到 **~1 GB**。直接 `<a href>` 在浏览器里：

- Chrome 默认认 `text/tab-separated-values` 当文件下载（OK），但 1 GB 流式下载耗时几分钟，过程中没有进度反馈
- 如果 nginx `proxy_read_timeout` 走了 60s 默认值，长流可能被切断（需要核对 `deploy/nginx/nginx.conf`）
- 浏览器 OOM 风险：某些版本会试图 buffer 整个响应

**接下来要做的几件事（按价值降序）**：

1. ~~**UI 标出文件大小** —— 后端在 `partial_result_link` 旁加 `partial_result_size_bytes` 字段，前端把"Download partial result（~993 MB）"这样写出来，用户知情同意~~ ✓ 已落地：API 加 `partial_result_size_bytes`，前端 [page.tsx](apps/pmet_frontend/app/tasks/[id]/page.tsx) 用 `formatBytes` helper 渲染 `Download partial result (993 MB)`；单测 [test_partial_result_link.py](tests/unit/test_partial_result_link.py) 扩到 size 字段全状态分支
2. **按需 gzip** —— `Content-Encoding: gzip` 流式压缩，~1 GB 的 TSV 通常压到 ~50-100 MB（重复字段名 + adj.p 重复值压得很好）。**暂缓**——先让 (1) 收集生产任务真实文件大小分布数据，再判断 gzip CPU 开销值不值得
3. **预览/截断端点** —— `/partial-result?head=10000` 只返回前 N 行，给"看一眼能不能用"的场景，配上"完整 N MB 在这里"的二级按钮。**暂不做**——`motif_output.txt` 是按 motif1/motif2 字典序排，不是按 p-value，head N 给的是字母序前 N 个 pair 而非最显著的，没价值
4. ~~**核对 nginx timeout** —— 如果当前默认 60 s，对 1 GB 链接太短，至少调到 600 s 或改用 `X-Accel-Redirect` 让 nginx 直发不经 uvicorn~~ ✓ 已落地：[deploy/nginx/nginx.conf](deploy/nginx/nginx.conf) `proxy_read_timeout 300 → 600s`；partial-result endpoint 加 `X-Accel-Buffering: no` 让 nginx 直 stream 不 buffer 整个响应（对 buffering 风险这才是关键修，timeout 是 belt-and-suspenders）

### ~~MinHash prefilter calibration~~ ✓ 已落地（结论：opt-in）

算法 + 集成 + 校准 + 单测 + 文档全部完成。**结论：默认关，仅作 power-user 开关保留。**

**已落地**：
- C++ 引擎：sketch（[motif.cpp:191-204](core/pairing/src/motif.cpp#L191-L204)）+ prefilter 分支（[utils.cpp:418-438](core/pairing/src/utils.cpp#L418-L438)）+ `-m` flag（[main.cpp:46](core/pairing/src/main.cpp#L46)）
- Workflow 集成：[scripts/lib/minhash.sh](scripts/lib/minhash.sh) 的 `resolve_minhash_min`，被三条 workflow（promoter / intervals / pair_only）source 后透传到 `-m`
- 后端 env 透传：`executor.py` 的 `os.environ.copy()` 自动把 `PMET_MINHASH_MIN/THRESHOLD/DEFAULT` 三个开关送到 workflow；compose worker `environment:` 段已加注释提示
- 单测：[tests/unit/test_minhash_resolver.sh](tests/unit/test_minhash_resolver.sh) 9 case 锁定 resolver 行为
- 校准 sweep 脚手架：[apps/cli/scripts/bench/calibrate_minhash.sh](apps/cli/scripts/bench/calibrate_minhash.sh) + [analyze_minhash_calibration.py](apps/cli/scripts/bench/analyze_minhash_calibration.py)
- 校准报告：[docs/perf/minhash_calibration.md](docs/perf/minhash_calibration.md)

**校准结论**（CIS-BP2，alpha=0.05 在 per-cluster Bonferroni 列）：

| m | random_genes_300 (truth=353) | heat_top300 (truth=72,948) |
|--:|---|---|
| 0 | 1.00 × | 1.00 × |
| 100 | 1.01 × / 0.00% FN | 1.00 × / 0.003% FN |
| 300 | 1.02 × / 0.00% FN | 1.03 × / 0.07% FN |
| 600 | 1.03 × / 5.38% FN | 1.04 × / 2.74% FN |
| 900 | 1.18 × / 21.53% FN | 1.19 × / 18.35% FN |
| 1200 | 1.50 × / 50.14% FN | 1.52 × / 47.62% FN |

加速 ≥ 30% 的档（m≥1200）丢一半显著 pair；FN 在可接受范围（≤ 5%）的档（m≤600）速度几乎没改善。**没有甜蜜点**——CIS-BP2 每个 motif hits cap=5000 → 期望 pair intersection ≈ 941，跳过低于此的就直接砍真信号。两个 gene list（随机 vs 真实生物）曲线同形，确认 random sweep 是诚实代理。

**算法上的下一步（如果将来想再啃）**：换个 prefilter 信号——比如先按 cluster gene-set 做 hypergeometric upper-bound 估计跳过永远不可能显著的 pair，而不是按 universe-level intersection。属于 P3+ 长期项，没列回来。

### Liveness watchdog：长阶段内更频繁 emit progress

watchdog 容器已落地（杀僵任务），但阈值偏保守（900 s），原因是 `scripts/lib/progress.sh` 只在阶段边界（`indexing → heterotypic → heatmaps`）打点。CIS-BP2 大库一次 pairing 在两个 emit 之间就要 ~10 分钟。

**接下来**：让内层循环（每 N 个 motif、每 N% pair test、每张 heatmap 前）push 心跳。完成后阈值可降到 300 s 不会误杀。

触点：`core/indexing/fused_fimo/src/main.cpp`、`core/pairing/parallel/src/...`、`scripts/r/heatmap.R`、`scripts/lib/progress.sh`（加 `bump_progress` helper 仅更 `updated_at`）。

### Worker concurrency 弹性化

`worker_concurrency=2` 通过 compose 的 `PMET_WORKERS=2` 写死。16 核机器闲置；2 核机器两个 CIS-BP2 就饱和。改：

```python
worker_concurrency = max(1, multiprocessing.cpu_count() // 2)
```

或暴露成 Makefile knob：`make up CONCURRENCY=4`。

### 仓库小整理

- ~~`data/configure/` 语义上属于部署期配置 → 该挪到 `deploy/configure/`（实际引用 ~30 处：backend/frontend/README/docs），等当前手头工作收尾后做~~ ✓ 已挪。`config.py` 通过 `CONFIGURE_DIR` 字段读取（host 默认 `deploy/configure/`，container 走 `PMET_CONFIGURE_DIR=/app/deploy/configure` env override + 单独 mount）。docstring/comment/translations 一并改
- ~~`core/indexing/{c,cpp}/scripts/{run,run_interval,debug_run}.sh` 写到 `$PROJECT_DIR/result/`（引擎本地），未集成到 monorepo `results/` —— 要么集成、要么文档说明这些是 throwaway dev-only~~ ✓ 已搬到 `core/legacy/indexing_{c,cpp}/scripts/`，按 legacy 命名空间约定即 throwaway dev-only
- ~~`scripts/fetch_data.sh` 和 `scripts/fetch_reference.sh` 在 TAIR10 拉取部分有重复。今天可接受（不同调用语境），但 `fetch_data.sh` 可以调用 `fetch_reference.sh` 处理 TAIR10 部分~~ ✓ `fetch_data.sh` TAIR10 部分已委托给 `fetch_reference.sh`（[scripts/fetch_data.sh:30-31](scripts/fetch_data.sh#L30-L31)）
