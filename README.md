# Steel-Compass V2

面向景观构筑物方案阶段的结构快算与专业复核 Beta。V2 使用 Next.js、FastAPI、PostgreSQL 和 Docker Compose，旧 Streamlit 页面仅保留为迁移参考。

> 当前结论只表示“在当前输入、假定和适用范围内的方案筛查”。所有计算模块在规范映射、手算基准和独立复算签署完成前均保持 `unverified`；专业模式不会返回“通过”，也不生成可直接送审的正式设计文件。

## 当前里程碑

### 已开放完整场景

- 钢结构单跨廊架：仅支持平顶、单跨、等高钢柱、独立基础。
- 真实传力链：`顶面荷载 → 钢檩条 → 横向门式框架 → 左右柱脚/锚栓 → 左右独立基础`。
- 直线栈道：木面板、钢次梁/主梁、钢柱、柱脚和左右独立基础。
- 柱支钢雨棚：单排柱悬挑和双排柱横向框架；墙附悬挑仍为开发中。
- 钢单跨门楼：等高、对称单跨门式框架、双柱脚和独立基础。
- 单柱钢导视牌：正负面板风压、悬臂立柱、底板锚栓和独立基础。
- 约束砌体景墙：砌体填充、RC 构造柱、压顶梁、地梁和条形基础。
- 现浇坐凳、矩形树池和钢筋混凝土悬臂挡土墙：分别覆盖座板/支承、池壁土压力和挡土稳定快算。
- 快算状态分离为：
  - `workflow_status`：计算链是否完整、是否过期；
  - `quick_outcome`：方案筛查通过或失败；
  - `engineering_status=null`：快算不冒充专业结论。
- 上游即使筛查失败，只要分析已完成，反力仍会继续传给下游；整体结果保留失败项。

多跨、斜顶、不同柱高、木结构、钢木混合廊架，双柱/倾斜导视牌，重力式挡土墙，以及水池、小桥、桩基等未闭环变体均显示为“开发中”，不可生成结论。

### 计算诚信

- schema `3.1` 使用组合一致的六分量反力包：`N、Vx、Vy、Mx、My、T`；3.0 及更早快照只读兼容。
- 上游反力按已组合效应传递，基础自重、覆土和浮力只在基础节点加入一次。
- 生成 ULS 主导/伴随组合，以及 SLS 标准、频遇、准永久组合。
- 校验作用方向、分布形式、目标节点和单位，钢梁拒绝把水平风作为竖向均布荷载。
- 钢梁、刚架、柱脚和基础均显式保存 `verification_status`；未独立验证的专业计算返回 `incomplete`。
- `backend/verification` 保存独立参考脚本和证据门槛，不能仅凭自动测试改成 `independently_verified`。

### 项目闭环

- 场景实例、草稿和不可变修订保存到服务端，刷新后可恢复。
- A/B/C 方案是独立 `SceneInstance`，支持复制、重命名、归档和指定修订比较。
- PDF 地址统一为 `/api/v2/projects/{project_id}/revisions/{revision_id}/report.pdf`，网页与 PDF 使用同一保存结果对象。
- 自定义荷载必须记录目标节点、方向、分布形式、单位和资料依据；无雪地区可记录“不适用＋依据”。
- 桌面使用设置主体与右侧传力链，390px 布局使用“设置 / 结果与对比”双页签。

### 后续场景

- 水景池体继续复用水压力、主动土压力和浮力核心；RC 池壁、池底板和完整抗浮链路完成前不开放场景。
- 小型景观桥、桩基/承台、挡土墙复杂工况和任意三维建模不在本里程碑。

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
$env:PLAYWRIGHT_SYSTEM_CHROME = "1"
npm run e2e

cd ..
docker compose build
```

当前自动化基线：后端全量测试、独立闭式算例、应用代码覆盖率检查和前端 lint/build 已通过；浏览器回归以本地应用浏览器为准，CLI Playwright 需要预装 Chromium。CI 任一步失败都应阻止开放对应能力。

## Docker Compose 全栈运行

Docker Desktop 仅提供 Docker 引擎，不会自动读取本项目的 `docker-compose.yml`，因此“打开 Docker”后看不到 Steel-Compass 容器是正常的。必须在仓库根目录执行一次 `up`，Compose 才会创建容器。

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

等待 `postgres`、`backend`、`frontend` 和 `caddy` 的健康检查通过后，访问 `http://localhost`。本地 Docker 默认 `APP_SCHEME=http`，不会要求浏览器信任容器内的自签名证书；真实域名部署时可在 `.env` 设置 `APP_SCHEME=https`。Docker 模式只有 Caddy 将端口 `80/443` 发布到主机；`frontend:3000` 和 `backend:8000` 是 Compose 内部端口，所以不要用 `http://localhost:3000` 作为 Docker 模式入口。首次登录使用 `.env` 中的引导管理员账号，登录后必须立即修改临时密码。

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

1. 逐项核对并签署规范条文映射、适用条件和版本。
2. 为每个开放模块保存手算、规范例题和独立脚本复算证据。
3. 柱脚补齐混凝土锥体、拔出和劈裂等锚固破坏模式后，才能开放专业结论。
4. 直线栈道和水景池体完成真实场景图、全链反力平衡与结果报告前，继续保持“开发中”。
5. 建立具备相应资格的人工复核与签章流程前，不得对外输出正式设计成果。
