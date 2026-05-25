# PMET Email Infrastructure

**[English](#en) · [汉文](#cn)**

How PMET sends and receives mail on `@pmet.online` — SMTP relay, MX forwarding, maintenance, and troubleshooting.

---

<a id="en"></a>

## Contents

- [1. Architecture](#en-1)
- [2. Why this setup](#en-2)
- [3. Outbound — Brevo SMTP](#en-3)
  - [3.1 DNS records](#en-3-1)
  - [3.2 SMTP credentials](#en-3-2)
  - [3.3 Relay chain (VPS socat)](#en-3-3)
  - [3.4 IP whitelist](#en-3-4)
- [4. Inbound — ImprovMX](#en-4)
- [5. PMET config file](#en-5)
- [6. Verification](#en-6)
- [7. Maintenance](#en-7)
- [8. Troubleshooting](#en-8)
- [9. Emergency recovery](#en-9)
- [10. Known issues](#en-10)
- [11. Incident log](#en-11)

<a id="en-1"></a>

## 1. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      pmet.online                          │
│                                                           │
│  📤 SEND (outbound)                                       │
│  Berlin Docker → DO VPS :10587 (socat) → Brevo :2525     │
│  (&lt;vps-ip&gt;)                                            │
│                                                           │
│  📥 RECEIVE (inbound)                                     │
│  Internet → ImprovMX MX → admin inbox                     │
└──────────────────────────────────────────────────────────┘
```

| Direction | Service | Cost | Role |
|---|---|---|---|
| Outbound | **Brevo** (France, EEA) | Free — 300/day | Transactional email to users |
| Outbound relay | **socat** on DO VPS | $0 (existing VPS) | Hides dynamic IP address behind fixed DO IP |
| Inbound | **ImprovMX** | Free — 25 aliases | `questions@pmet.online` → Gmail |

<a id="en-2"></a>

## 2. Why this setup

Two problems made direct Brevo connections impossible:

| Problem | Detail |
|---|---|
| **Dynamic IP address** | Berlin ISP rotates the public IP periodically. Brevo's anti-spam marks dynamic IP ranges as low-reputation → `525 Unauthorized IP` on every rotation. |
| **DO blocks port 587** | DigitalOcean blocks outbound 587 on all VPS to prevent spam abuse. This cannot be lifted. Brevo provides **port 2525** as an alternative for cloud-hosted relays. |

**Solution**: socat on the DO VPS listens on `:10587` and forwards to `smtp-relay.brevo.com:2525`. Brevo only sees the VPS static IP (`<vps-ip>`), and the 2525 port bypasses DO's 587 block.

<a id="en-3"></a>

## 3. Outbound — Brevo SMTP

Brevo account: `your-email@gmail.com` (login placeholder). Dashboard: [app.brevo.com](https://app.brevo.com).

<a id="en-3-1"></a>

### 3.1 DNS records (one-time)

> These are **examples specific to `pmet.online`**. Each domain gets its own values from Brevo → Senders, domains, IPs → Domains → Authenticate. Do not copy-paste.

Add at your DNS provider (Aliyun):

| Type | Host | Value (example only) | TTL |
|---|---|---|---|
| TXT | `@` | `v=spf1 include:spf.brevo.com include:spf.improvmx.com ~all` | 600 |
| TXT | `@` | `brevo-code:<your-code>` | 600 |
| CNAME | `brevo1._domainkey` | `<dkim1>`.dkim.brevo.com | 600 |
| CNAME | `brevo2._domainkey` | `<dkim2>`.dkim.brevo.com | 600 |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` | 600 |

Verify: Brevo → Senders, domains, IPs → Domains → all green ✅.

<a id="en-3-2"></a>

### 3.2 SMTP credentials

Brevo → SMTP & API → SMTP tab:

| Field | Value |
|---|---|
| Server | `smtp-relay.brevo.com` |
| Port | `2525` (STARTTLS) — use 2525, not 587, because DO blocks 587 |
| Login | `ab9e48001@smtp-brevo.com` (auto-generated, not your login email) |
| Key | `xsmtpsib-...` (Generate SMTP key → store in password manager, **never git**) |

Revoke & regenerate the key immediately if it appears in any log, chat, or screenshot.

<a id="en-3-3"></a>

### 3.3 Relay chain (VPS socat)

**VPS info:** DigitalOcean Droplet · `<vps-ip>` · Ubuntu 22.04 · SSH: `vpsadmin` / `root`

**Deploy the socat service (one-time):**

```bash
sudo tee /etc/systemd/system/socat-brevo.service <<'EOF'
[Unit]
Description=Socat SMTP Relay to Brevo (Port 2525)
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/usr/bin/socat -d -d TCP4-LISTEN:10587,fork,reuseaddr,bind=0.0.0.0 TCP4:smtp-relay.brevo.com:2525
Restart=always
RestartSec=2
User=root
StandardOutput=journal
StandardError=journal
SyslogIdentifier=socat-brevo

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now socat-brevo.service
sudo ufw allow 10587/tcp && sudo ufw reload
```

**Key points:**
- Listens on `10587` (all interfaces), forwards to `smtp-relay.brevo.com:2525`
- `-d -d` logs every connect/disconnect to journal
- `RestartSec=2` — fast recovery on crash

<a id="en-3-4"></a>

### 3.4 IP whitelist

Brevo → SMTP & API → IP Access → toggle ON:

| IP | Role |
|---|---|
| `<vps-ip>` | DO VPS — the **only** IP Brevo sees in production |
| `<current dynamic IP>` | Dev only — add from [whatismyip.com](https://whatismyip.com) when testing direct |

When mail stops with `525`, the relay chain is bypassed or broken — never add a dynamic IP as a permanent fix.

<a id="en-4"></a>

## 4. Inbound — ImprovMX

Account: [improvmx.com](https://improvmx.com). Referral email: `your-email@gmail.com`.

**DNS (Aliyun):**

| Type | Host | Value | Priority |
|---|---|---|---|
| MX | `@` | `mx1.improvmx.com` | 10 |
| MX | `@` | `mx2.improvmx.com` | 20 |

**Aliases:**

| Alias | → | Public? |
|---|---|---|
| `questions@pmet.online` | `your-private@email.com` | Yes (footer / Impressum) |

<a id="en-5"></a>

## 5. PMET config file

`deploy/configure/email_credential.txt` — **gitignored, 5 lines:**

```
ab9e48001@smtp-brevo.com          # line 1: SMTP login
xsmtpsib-...                      # line 2: SMTP key
noreply@pmet.online               # line 3: From address
<vps-ip>:10587               # line 4: SMTP host[:port]  (production)
# smtp-relay.brevo.com            # line 4: (dev / direct only)
587                               # line 5: fallback port (overridden by line 4 port if present)
```

Line 4 supports `host:port` — the parser extracts the port so `smtplib` receives host and port separately.

Apply: `cd deploy && docker compose restart worker`

<a id="en-6"></a>

## 6. Verification

### VPS side

```bash
systemctl status socat-brevo      # Active: active (running)
ss -tulpn | grep :10587           # port listening
curl -v telnet://smtp-relay.brevo.com:2525  # Brevo reachable → 220 ESMTP banner
journalctl -u socat-brevo -n 20   # recent connections
```

### Berlin side

```bash
nc -zv &lt;vps-ip&gt; 10587        # → succeeded!
```

### End-to-end

Submit a demo task at `/submit` → check Gmail for notification. Or check `/admin` → Activity log → Mail tab for `send_ok`.

<a id="en-7"></a>

## 7. Maintenance

| Task | Cadence | Command / Action |
|---|---|---|
| Check relay status | Weekly | `systemctl status socat-brevo` on VPS |
| View relay logs | On demand | `journalctl -u socat-brevo --since today` |
| Real-time log monitor | Debugging | `journalctl -u socat-brevo -f` |
| Restart relay | If stuck | `systemctl restart socat-brevo` on VPS |
| Rotate SMTP key | ~90 days | Brevo → Revoke → Generate → update line 2 → restart worker |
| Check sending quota | Monthly | Brevo dashboard → Usage |
| Audit mail events | On demand | `/admin` → Activity log → Mail tab |

<a id="en-8"></a>

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `525 Unauthorized IP` | Direct connection, not through relay | Check line 4 points to VPS; verify socat running |
| `Connection unexpectedly closed` / timeout | socat down, or ufw blocks 10587 | `systemctl restart socat-brevo`; `ufw allow 10587/tcp` |
| `535 Authentication failed` | SMTP key revoked / wrong | Brevo → regenerate key → update line 2 |
| TCP connects but no SMTP banner | Wrong Brevo port on VPS | Check socat uses `:2525`, not `:587` |
| Mail in Gmail Spam | DKIM/DMARC missing | Verify Brevo → Domains shows all green |
| socat exits immediately | Port 10587 already in use | `lsof -i :10587` → kill the stale process |

<a id="en-9"></a>

## 9. Emergency recovery

If the VPS relay is completely down and mail must go out **now**:

1. Visit [whatismyip.com](https://whatismyip.com) from the Berlin host → note the IP
2. Brevo → SMTP & API → IP Access → add that IP
3. Edit `email_credential.txt` line 4 → `smtp-relay.brevo.com` (direct)
4. `docker compose restart worker`
5. Wait ~5 min for Brevo to apply the whitelist change

This is **temporary** — the IP will rotate again. Fix the relay and revert to VPS as soon as possible.

<a id="en-10"></a>

## 10. Known issues

| Issue | Impact | Mitigation |
|---|---|---|
| DO blocks outbound 587 | Must use 2525 | socat configured with 2525 upstream |
| socat has no queue | Mail lost if Brevo unreachable | Acceptable for now (< 300/day); [future: Postfix](#en-10-future) |
| No auth on port 10587 | Anyone who knows the IP can relay | Don't publish the VPS IP; [future: Postfix + SASL](#en-10-future) |
| Single VPS = single point of failure | Relay down → mail stops | Emergency recovery procedure in [§9](#en-9) |

<a id="en-10-future"></a>

**Future improvements:**
- **Postfix relay** instead of socat — mail queue with retry, SMTP auth, multi-upstream failover
- **Monitoring** — Prometheus + Grafana alert on relay down
- **HA** — second VPS relay node with DNS round-robin

<a id="en-11"></a>

## 11. Incident log

### 2026-05-24 — All mail broken: 525 Unauthorized IP

**Symptom:** Every email returned `525 5.7.1 Unauthorized IP address`.

**Root cause:** IP rotated. `email_credential.txt` was set to `smtp-relay.brevo.com` (direct) instead of the VPS relay, so Brevo saw the new (unlisted) IP. Additionally, the VPS socat was not running — no systemd unit had been created yet.

**Timeline (UTC):**

| Time | Event |
|---|---|
| May 17–20 | `send_ok` — normal |
| May 24 06:55 | First `525` — ISP rotated IP |
| May 24 14:51 | `535` — credential file briefly misconfigured |
| May 25 09:49 | VPS socat systemd unit created, credential fixed to `<vps-ip>:10587` |
| May 25 ~10:00 | End-to-end test passed — relay chain working |

**Prevention:**
- `tests/unit/test_mail_dispatch.py` → `SmtpErrorHandlingTests` validates Brevo error codes (525, 535) produce distinct `send_fail` audit records
- socat now runs as a systemd service with `Restart=always`, surviving VPS reboots
- `config.py` line 4 now supports `host:port` format

---

<a id="cn"></a>

## 目录

- [1. 架构](#cn-1)
- [2. 为什么这样设计](#cn-2)
- [3. 发信 — Brevo SMTP](#cn-3)
  - [3.1 DNS 记录](#cn-3-1)
  - [3.2 SMTP 凭据](#cn-3-2)
  - [3.3 转发链（VPS socat）](#cn-3-3)
  - [3.4 IP 白名单](#cn-3-4)
- [4. 收信 — ImprovMX](#cn-4)
- [5. PMET 配置文件](#cn-5)
- [6. 验证](#cn-6)
- [7. 日常运维](#cn-7)
- [8. 排错](#cn-8)
- [9. 紧急恢复](#cn-9)
- [10. 已知问题](#cn-10)
- [11. 事件日志](#cn-11)

<a id="cn-1"></a>

## 1. 架构

```
┌──────────────────────────────────────────────────────────┐
│                      pmet.online                          │
│                                                           │
│  📤 发信（出站）                                          │
│  Berlin Docker → DO VPS :10587 (socat) → Brevo :2525     │
│  (&lt;vps-ip&gt;)                                            │
│                                                           │
│  📥 收信（入站）                                          │
│  互联网 → ImprovMX MX → 管理员邮箱                         │
└──────────────────────────────────────────────────────────┘
```

| 方向 | 服务 | 费用 | 作用 |
|---|---|---|---|
| 发信 | **Brevo**（法国，EEA） | 免费 300 封/天 | 事务性邮件通知用户 |
| 发信中继 | **socat** 在 DO VPS | $0（现有 VPS） | 动态 IP 隐藏在 VPS 固定 IP 之后 |
| 收信 | **ImprovMX** | 免费 25 别名 | `questions@pmet.online` → Gmail |

<a id="cn-2"></a>

## 2. 为什么这样设计

两个问题导致无法直连 Brevo：

| 问题 | 详情 |
|---|---|
| **动态 IP** | Berlin ISP 定期更换公网 IP。Brevo 反垃圾系统将动态 IP 段标记为低信誉，每次 IP 变动返回 `525 Unauthorized IP`。 |
| **DO 封禁 587 端口** | DigitalOcean 为防止垃圾邮件滥用，默认封禁所有 VPS 的出站 587 端口，无法解除。Brevo 提供 **2525 端口** 作为云服务商环境的替代。 |

**方案**：VPS 上 socat 监听 `:10587`，转发到 `smtp-relay.brevo.com:2525`。Brevo 只看到 VPS 的固定 IP（`<vps-ip>`），2525 端口绕过 DO 的 587 封锁。

<a id="cn-3"></a>

## 3. 发信 — Brevo SMTP

Brevo 账号：`your-email@gmail.com`（登录占位）。控制台：[app.brevo.com](https://app.brevo.com)。

<a id="cn-3-1"></a>

### 3.1 DNS 记录（一次性）

> 以下为 **`pmet.online` 的示例值**。每个域名需从 Brevo → Senders, domains, IPs → Domains → Authenticate 获取自己的记录值。切勿直接复制粘贴。

在 DNS 服务商（阿里云）添加：

| 类型 | 主机记录 | 记录值（仅示例） | TTL |
|---|---|---|---|
| TXT | `@` | `v=spf1 include:spf.brevo.com include:spf.improvmx.com ~all` | 600 |
| TXT | `@` | `brevo-code:<your-code>` | 600 |
| CNAME | `brevo1._domainkey` | `<dkim1>`.dkim.brevo.com | 600 |
| CNAME | `brevo2._domainkey` | `<dkim2>`.dkim.brevo.com | 600 |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` | 600 |

验证：Brevo → Senders, domains, IPs → Domains → 全部绿勾 ✅。

<a id="cn-3-2"></a>

### 3.2 SMTP 凭据

Brevo → SMTP & API → SMTP 标签页：

| 字段 | 值 |
|---|---|
| 服务器 | `smtp-relay.brevo.com` |
| 端口 | `2525`（STARTTLS）—— 用 2525 而非 587，因为 DO 封禁 587 |
| 登录名 | `ab9e48001@smtp-brevo.com`（Brevo 自动生成，不是登录邮箱） |
| Key | `xsmtpsib-...`（Generate SMTP key 生成；存密码管理器，**绝不入 git**） |

Key 一旦出现在日志、聊天或截图中立即作废重新生成。

<a id="cn-3-3"></a>

### 3.3 转发链（VPS socat）

**VPS 信息：** DigitalOcean Droplet · `<vps-ip>` · Ubuntu 22.04 · SSH: `vpsadmin` / `root`

**部署 socat 服务（一次性）：**

```bash
sudo tee /etc/systemd/system/socat-brevo.service <<'EOF'
[Unit]
Description=Socat SMTP Relay to Brevo (Port 2525)
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/usr/bin/socat -d -d TCP4-LISTEN:10587,fork,reuseaddr,bind=0.0.0.0 TCP4:smtp-relay.brevo.com:2525
Restart=always
RestartSec=2
User=root
StandardOutput=journal
StandardError=journal
SyslogIdentifier=socat-brevo

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now socat-brevo.service
sudo ufw allow 10587/tcp && sudo ufw reload
```

**要点：**
- 监听 `10587`（所有接口），转发到 `smtp-relay.brevo.com:2525`
- `-d -d` 每次连接/断开均写入 journal
- `RestartSec=2` — 崩溃后快速恢复

<a id="cn-3-4"></a>

### 3.4 IP 白名单

Brevo → SMTP & API → IP Access → 开启：

| IP | 用途 |
|---|---|
| `<vps-ip>` | DO VPS — 生产环境中 Brevo **唯一**看到的 IP |
| `<当前动态 IP>` | 仅开发测试 — 从 [whatismyip.com](https://whatismyip.com) 获取 |

邮件出现 `525` 说明绕过了中继或中继挂了 —— 不要把动态 IP 加白名单当永久方案。

<a id="cn-4"></a>

## 4. 收信 — ImprovMX

账号：[improvmx.com](https://improvmx.com)。关联邮箱：`your-email@gmail.com`。

**DNS（阿里云）：**

| 类型 | 主机记录 | 记录值 | 优先级 |
|---|---|---|---|
| MX | `@` | `mx1.improvmx.com` | 10 |
| MX | `@` | `mx2.improvmx.com` | 20 |

**别名：**

| 别名 | → | 公开？ |
|---|---|---|
| `questions@pmet.online` | `your-private@email.com` | 是（footer / Impressum） |

<a id="cn-5"></a>

## 5. PMET 配置文件

`deploy/configure/email_credential.txt` — **gitignored，5 行：**

```
ab9e48001@smtp-brevo.com          # 第 1 行：SMTP 登录名
xsmtpsib-...                      # 第 2 行：SMTP key
noreply@pmet.online               # 第 3 行：发件人地址
<vps-ip>:10587               # 第 4 行：SMTP 主机[:端口]（生产环境）
# smtp-relay.brevo.com            # 第 4 行：（开发/直连用）
587                               # 第 5 行：备用端口（若第 4 行含端口则被覆盖）
```

第 4 行支持 `host:port` 格式，解析器会自动提取端口。

生效：`cd deploy && docker compose restart worker`

<a id="cn-6"></a>

## 6. 验证

### VPS 端

```bash
systemctl status socat-brevo      # Active: active (running)
ss -tulpn | grep :10587           # 端口监听中
curl -v telnet://smtp-relay.brevo.com:2525  # Brevo 可达 → 220 ESMTP banner
journalctl -u socat-brevo -n 20   # 最近连接记录
```

### Berlin 端

```bash
nc -zv &lt;vps-ip&gt; 10587        # → succeeded!
```

### 端到端

在 `/submit` 提交一个 demo 任务 → Gmail 查收通知。或查看 `/admin` → Activity log → Mail tab 的 `send_ok` 记录。

<a id="cn-7"></a>

## 7. 日常运维

| 任务 | 频率 | 命令 / 操作 |
|---|---|---|
| 检查中继状态 | 每周 | `systemctl status socat-brevo`（VPS 上） |
| 查看中继日志 | 按需 | `journalctl -u socat-brevo --since today` |
| 实时监控日志 | 调试时 | `journalctl -u socat-brevo -f` |
| 重启中继 | 卡住时 | `systemctl restart socat-brevo`（VPS 上） |
| 轮换 SMTP key | ~90 天 | Brevo → Revoke → Generate → 更新第 2 行 → restart worker |
| 检查发送额度 | 每月 | Brevo 控制台 → Usage |
| 审计邮件事件 | 按需 | `/admin` → Activity log → Mail tab |

<a id="cn-8"></a>

## 8. 排错

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `525 Unauthorized IP` | 直连而非走中继 | 检查第 4 行是否指向 VPS；确认 socat 在运行 |
| `Connection unexpectedly closed` / 超时 | socat 挂了或 ufw 挡了 10587 | `systemctl restart socat-brevo`；`ufw allow 10587/tcp` |
| `535 Authentication failed` | SMTP key 作废或写错 | Brevo → 重新生成 key → 更新第 2 行 |
| TCP 通但无 SMTP banner | VPS 上 Brevo 端口配错 | 检查 socat 用的是 `:2525` 不是 `:587` |
| 邮件进 Gmail 垃圾箱 | DKIM/DMARC 缺失 | Brevo → Domains 确认全部绿勾 |
| socat 启动即退出 | 10587 端口被占用 | `lsof -i :10587` → 杀掉占用进程 |

<a id="cn-9"></a>

## 9. 紧急恢复

VPS 中继完全失效、必须立即发信时：

1. Berlin 主机访问 [whatismyip.com](https://whatismyip.com) → 记下当前 IP
2. Brevo → SMTP & API → IP Access → 添加该 IP
3. 编辑 `email_credential.txt` 第 4 行 → `smtp-relay.brevo.com`（直连）
4. `docker compose restart worker`
5. 等 ~5 分钟让 Brevo 白名单生效

**这是临时方案** —— 动态 IP 还会变。尽快修复中继并切回 VPS。

<a id="cn-10"></a>

## 10. 已知问题

| 问题 | 影响 | 缓解措施 |
|---|---|---|
| DO 封禁出站 587 | 必须用 2525 | socat 已配置 2525 上游 |
| socat 无队列机制 | Brevo 不可达时邮件直接丢失 | 当前量小可接受（< 300/天）；[未来：Postfix](#cn-10-future) |
| 10587 端口无认证 | 知道 IP 即可中继 | 勿公开 VPS IP；[未来：Postfix + SASL](#cn-10-future) |
| 单 VPS = 单点故障 | 中继挂 → 邮件停 | 紧急恢复流程见 [§9](#cn-9) |

<a id="cn-10-future"></a>

**未来改进：**
- **Postfix 中继** 替代 socat — 邮件队列 + 自动重试 + SMTP 认证 + 多上游故障转移
- **监控告警** — Prometheus + Grafana 监控端口状态
- **高可用** — 第二个 VPS 中继节点 + DNS 轮询

<a id="cn-11"></a>

## 11. 事件日志

### 2026-05-24 — 全部邮件静默失败：525 Unauthorized IP

**现象：** 所有邮件返回 `525 5.7.1 Unauthorized IP address`。

**根因：** IP 被 ISP 更换。`email_credential.txt` 配置为 `smtp-relay.brevo.com`（直连）而非 VPS 中继，导致 Brevo 看到新的（不在白名单的）IP。同时 VPS 上 socat 未运行 —— 此前从未创建 systemd 服务。

**时间线（UTC）：**

| 时间 | 事件 |
|---|---|
| 5 月 17–20 日 | `send_ok` — 正常 |
| 5 月 24 日 06:55 | 首次 `525` — ISP 更换 IP |
| 5 月 24 日 14:51 | `535` — credential 文件短暂配错 |
| 5 月 25 日 09:49 | VPS socat systemd 单元创建，credential 改为 `<vps-ip>:10587` |
| 5 月 25 日 ~10:00 | 端到端测试通过 — 中继链恢复 |

**预防措施：**
- `tests/unit/test_mail_dispatch.py` → `SmtpErrorHandlingTests` 验证 Brevo 错误码（525, 535）产生可区分的 `send_fail` 审计记录
- socat 现作为 systemd 服务运行，`Restart=always`，VPS 重启后自动恢复
- `config.py` 第 4 行支持 `host:port` 格式
