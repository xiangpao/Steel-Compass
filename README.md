# Steel-Compass V2

面向非结构设计人员的景观结构方案筛查工具。V2 使用 Next.js、FastAPI、PostgreSQL 和 Docker Compose，旧 Streamlit 页面仅保留为迁移参考。

> 当前结论只表示“在当前输入、假定和适用范围内的方案筛查”。所有计算模块在规范映射、手算基准和独立复算签署完成前均保持 `unverified`，不生成可直接用于施工图或送审的正式设计文件。历史 `professional` 快照继续只读兼容，新建和重新计算统一采用“方案筛查”。

## 当前里程碑：亭廊专业流程预览

当前生产入口已经接入 Geometry `2.3` 工作台和完整的数据传递路径，但发布等级仍是 `scheme_estimate`。构件、连接、柱脚、短柱和基础中存在未完成或未独立验证的检查，因此工作流可能返回 `incomplete`，当前版本不能生成 `project_check` 通过结论。

### 已开放完整场景

- 首页默认展示廊架、雨棚、导视牌、景墙、门楼、栈道/平台六类常用场景；坐凳/树池、水池、桥和挡土设施收在“更多场景”。
- 项目条件采用 Profile `1.1`：浙江沿海、浙江内陆、浙江山区及其他地区手动输入；条件可按场景分步完成，重现期默认 50 年，适用场景的地震档必须明确选择。
- 六类常用场景生成 `F_Ek = α1 × G_eq` 的正负 X/Y 等效地震作用包；该能力保持 `unverified`。水池、桥梁和挡土结构本版本明确标记未叠加地震作用。
- 场景条件由目录声明：屋盖类显示风、雪、地震；导视牌、景墙、门楼不显示雪和屋面字段；栈道只显示露天积雪与地震；水池、挡土等不显示无关的风雪地震向导。原始系数仅在高级参数中覆盖，且必须记录原因。
- 新亭廊修订采用 Snapshot Schema `4.0`、Geometry `2.3` 与标准配置 `CN-2026.7`；Geometry `2.2` 及更早记录保持只读，可另存为新版模型，不原地覆盖。
- 完整场景不再静默采用基础尺寸、`120kPa` 承载力、地下水 `5m` 或钢截面默认值；区域土质仅能生成 `scheme_estimate`，工程勘察资料和已验证模块齐全后才可能生成 `project_check`。
- 项目地下部分按“土质与承载力—施工/使用/抗浮水位—柱脚反力—基础尺寸与控制验算”保存；没有沉降参数时报告明确标注“资料不足”。
- 钢构件必须记录牌号、截面目录项、方向、计算长度和无侧向支撑长度；首版目录覆盖方管、矩形管、圆管、H 型和工字形候选，全部保持 `unverified`。

- 钢亭廊采用二维精确编辑＋三维实时联动：支持不等跨、不同柱高、缺柱保梁、局部补梁、直线/圆弧边界及任意角度单坡；圆弧构件按可追溯直线分段近似，真正弯梁和自由曲面不在当前范围。
- 生产亭廊入口已使用 Geometry 2.3 工作台，但当前只开放方案测算专业流程预览；`/qa/pergola-workbench-v2` 继续作为隔离回归路由，QA 草稿只保存在浏览器本地，不写入项目。
- 屋面分区经真实边界、开洞和分担条带裁切后形成杆件均布荷载，并进入线性空间分析、P-Δ、弹性屈曲、组合包络和 PyNite 并行复核。构件、连接、柱脚、短柱和基础检查均保持 `unverified`；未完成项返回 `incomplete`，不形成工程校核通过结论。
- 真实传力链：`屋面分区 → 檩条/次梁/主梁 → 梁柱连接 → 钢柱 → 柱脚/锚栓 → RC短柱 → 独立基础 → 地基`。
- 直线栈道：木面板、钢次梁/主梁、钢柱、柱脚和左右独立基础。
- 钢雨棚：单排柱悬挑、双排柱横向框架和墙附悬挑；墙体锚固边界在场景结果中单独说明。
- 钢单跨门楼：等高、对称单跨门式框架、双柱脚和独立基础。
- 单柱钢导视牌：正负面板风压、悬臂立柱、底板锚栓和独立基础。
- 约束砌体景墙：砌体填充、RC 构造柱、压顶梁、地梁和条形基础。
- 现浇坐凳、矩形树池和钢筋混凝土悬臂挡土墙：分别覆盖座板/支承、池壁土压力和挡土稳定快算。
- 快算状态分离为：
  - `workflow_status`：计算链是否完整、是否过期；
  - `quick_outcome`：方案筛查通过或失败；
  - `engineering_status=null`：快算不冒充专业结论。
- 上游即使筛查失败，只要分析已完成，反力仍会继续传给下游；整体结果保留失败项。

完整场景与单项工具均只保留方案筛查边界；页面不重复展示送审提示，结果和 PDF 仍会保留适用范围与不可直接送审说明。

### 计算诚信

- schema `3.1` 使用组合一致的六分量反力包：`N、Vx、Vy、Mx、My、T`；3.0 及更早快照只读兼容。
- 上游反力按已组合效应传递，基础自重、覆土和浮力只在基础节点加入一次。
- 生成 ULS 主导/伴随组合，以及 SLS 标准、频遇、准永久组合。
- 校验作用方向、分布形式、目标节点和单位，钢梁拒绝把水平风作为竖向均布荷载。
- 钢梁、刚架、柱脚和基础均显式保存 `verification_status`；全部新计算保持方案筛查边界，历史专业记录只读。
- `backend/verification` 保存独立参考脚本和证据门槛，不能仅凭自动测试改成 `independently_verified`。

### 项目闭环

- 场景实例、草稿和不可变修订保存到服务端，刷新后可恢复。
- A/B/C 方案是独立 `SceneInstance`，支持复制、重命名、归档和指定修订比较。
- 亭廊专业工作台的 PDF 只读取不可变分析快照：`/api/v2/projects/{project_id}/scene-instances/{instance_id}/analysis-snapshots/{snapshot_id}/report.pdf`；旧场景修订继续使用原报告接口。
- 自定义荷载必须记录目标节点、方向、分布形式、单位和资料依据；无雪地区可记录“不适用＋依据”。
- 桌面使用设置主体与右侧传力链，390px 布局使用“设置 / 结果与对比”双页签。

### 后续计划

未完成能力、发布前验证与明确不开发范围见 [ROADMAP.md](ROADMAP.md)。当前默认显示六类常用场景和十三个常用单项；其余已开放能力可通过“更多场景 / 更多单项”按需展开。

## 本地运行

需要 Python 3.11+、uv、Node.js 22 和 Docker。运行时请选择下面一种方式；两种方式不要同时占用相同端口。

### 方式 A：本地进程开发

终端一启动 FastAPI：

```powershell
cd backend
uv sync --extra dev --locked
$env:STEEL_COMPASS_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:STEEL_COMPASS_BOOTSTRAP_ADMIN_PASSWORD = "replace-with-a-long-random-password"
uv run uvicorn app.main:app --reload
```

另开终端二启动 Next.js：

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:3000`；后端健康检查为 `http://127.0.0.1:8000/health`。这种方式只启动两个本地进程，不会在 Docker Desktop 中创建 Steel-Compass 容器。首次登录必须修改管理员临时密码。

## 验证

```powershell
cd backend
uv run pytest --cov=app --cov-report=term-missing
uv run alembic upgrade head

cd ../frontend
npm run lint
npm run build
npm run e2e

cd ..
docker compose build
```

默认使用 Playwright 自带 Chromium。只有明确需要验证本机 Chrome 且其代理配置允许访问本地端口时，才设置 `PLAYWRIGHT_SYSTEM_CHROME=1`。

若 Docker 全栈已经运行，可直接复用 `http://127.0.0.1`，避免 Playwright 再启动一套 Next.js：

```powershell
cd frontend
$env:PLAYWRIGHT_SKIP_WEBSERVER = "1"
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1"
npm run e2e -- --workers=1
```

当前自动化基线：后端全量测试、独立闭式算例、应用代码覆盖率检查和前端 lint/build 已通过；CLI Playwright 需要预装 Chromium。CI 任一步失败都应阻止开放对应能力。

## Docker Compose 全栈运行

Docker Desktop 仅提供 Docker 引擎，不会自动读取本项目的 `docker-compose.yml`，因此“打开 Docker”后看不到 Steel-Compass 容器是正常的。必须在仓库根目录执行一次 `up`，Compose 才会创建容器。

### 一键启动（Windows）

双击项目根目录的 [start-steel-compass.bat](start-steel-compass.bat)。脚本会检查 Docker、校验 `.env`、启动 Compose 容器，等待 `http://127.0.0.1/health` 通过后自动打开 `http://127.0.0.1/`。本地镜像不存在时才会自动构建；代码或依赖变更后如需强制重建，请执行 `docker compose --env-file .env up -d --build`。首次运行会创建并打开 `.env`，请先替换示例密码，再重新双击脚本。

### 本机登录信息

- 登录地址：`http://127.0.0.1/`
- 登录账号：`admin`
- 登录密码：已配置在本机 `.env` 的 `STEEL_COMPASS_BOOTSTRAP_ADMIN_PASSWORD`，`.env` 已被 Git 忽略，不要把它复制到公开说明或提交到仓库。
- `POSTGRES_PASSWORD` 是 PostgreSQL 内部连接密码，与网页登录密码不同；两个变量都不能保留 `replace-with-...` 示例值，否则启动脚本会停止并提示修改。
- 首次登录可能会要求立即修改临时密码；修改后以后以新密码为准。启动脚本本身不会再询问管理员密码。

首次运行（PowerShell）：

```powershell
# 当前目录必须是 Steel-Compass 仓库根目录
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 编辑 .env，至少替换 POSTGRES_PASSWORD 和 STEEL_COMPASS_BOOTSTRAP_ADMIN_PASSWORD
notepad .env

docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
```

等待 `postgres`、`backend`、`frontend` 和 `caddy` 的健康检查通过后，访问 `http://127.0.0.1`。本地 Docker 默认使用明确的 IPv4 回环地址，避免部分 Windows/Docker Desktop 组合把 `localhost` 解析为未发布的 `::1` 后超时；不要改用 `http://localhost`。本地默认 `APP_SCHEME=http`，不会要求浏览器信任容器内的自签名证书；真实域名部署时可在 `.env` 设置 `APP_SCHEME=https` 并同步修改 `APP_DOMAIN` 与 `STEEL_COMPASS_FRONTEND_ORIGIN`。Docker 模式只有 Caddy 将端口 `80/443` 发布到主机；`frontend:3000` 和 `backend:8000` 是 Compose 内部端口，所以也不要使用带 `:3000` 的地址。首次登录使用 `.env` 中的引导管理员账号，登录后必须立即修改临时密码。

常用操作：

```powershell
# 查看本项目容器和健康状态
docker compose --env-file .env ps

# 查看启动失败或计算请求相关日志
docker compose --env-file .env logs -f backend frontend caddy

# 停止容器（保留 PostgreSQL 数据卷）
docker compose --env-file .env down
```

如果 `docker compose ps` 没有 Steel-Compass 服务，通常是尚未在本仓库根目录执行 `up`，或执行时没有加载 `.env`；先重新执行上面的 `config` 和 `up`。如果页面能打开但计算失败，先确认 `backend` 为 `healthy`，再查看 `backend` 和 `frontend` 日志。只有明确要删除本地数据库时才使用 `docker compose --env-file .env down -v`，该命令会删除 PostgreSQL 数据卷。

本里程碑只完成本地实现和验证，不推送、不部署。生产环境还必须配置真实域名、HTTPS、安全组、密钥、日志、每日备份和恢复演练。

## 发布前人工门槛

2026-09-26 景观设计安全边界补充验证见 [本轮报告](docs/landscape-validation-20260926/README.md)：新增柱截面、壁厚、柱距/梁跨、方向及水位敏感性验证，修复二阶传递、纯上拔与基础候选跨组合等问题。二阶沿杆包络、释放稳定、脱开接触、部分场景输入转换和独立专业证据仍未完成；本轮测试通过不代表工程安全边界已获验证，全部模块保持 `unverified`。

1. 逐项核对并签署规范条文映射、适用条件和版本。
2. 为每个开放模块保存手算、规范例题和独立脚本复算证据。
3. 柱脚补齐混凝土锥体、拔出和劈裂等锚固破坏模式后，才能开放专业结论。
4. 对场景自动风雪与地震作用补充独立算例、版本化来源与人工复核后，才可扩大适用范围。
5. 建立具备相应资格的人工复核与签章流程前，不得对外输出正式设计成果。
