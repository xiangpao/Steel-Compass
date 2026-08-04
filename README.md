# Steel-Compass V2

面向景观工程方案阶段的结构计算与复核工具。V2 将旧 Streamlit 原型迁移为：

- Next.js 产品界面；
- FastAPI 认证、项目、版本、计算和报告 API；
- 独立 Python 计算引擎；
- PostgreSQL 可追溯数据存储；
- Caddy HTTPS 入口与 Docker Compose 部署。

> 当前为受邀团队使用的 Beta。输出表示“当前输入和适用范围内通过/不通过”，需由具备资格的专业人员复核，不作为已签章设计文件。

## 已实现范围

### 双入口与场景体系

- 一级入口固定为 **完整场景** 与 **单项计算**，快算/专业 Beta 只在选中对象后切换。
- 首批公开五类可闭环场景：廊架/景亭、雨棚、导视/广告牌、景墙/围墙、门楼/入口构架。栈道/平台、坐凳/树池、水景池体、小型景观桥和挡土设施明确标记为“开发中”，不可创建场景实例。
- 场景工作台只有“设置”和“结果与对比”两个主页面状态；材料、几何、荷载、支承、连接及条件化地基在同一设置面集中编辑，右侧持续显示实例化传力链和节点状态。
- 单项计算按“荷载与环境、上部构件、连接与支承、基础与地基、挡土与池体”折叠；材料仅作为筛选。
- 旧“廊架檩条、导视牌立柱、导视牌基础”等条目已迁移为模块应用预设，不再与完整场景并列。
- **快算模式**：显式确认场景假定，结果标记为方案快算。
- **专业模式 Beta**：关键字段与荷载来源必填，拒绝静默关键默认值。
- 两种模式共用 `backend/app/core` 计算引擎和统一结果 schema。
- 桌面侧栏选择立即生效并保持展开；移动抽屉保留“应用并关闭”。场景草稿按场景族保留。

场景图使用有向无环图拓扑执行，校验循环连接、缺失上游和单位不兼容。变体把节点实例化为 `required | optional | not_applicable`，不适用节点不显示也不参与完成度；例如墙附雨棚只有墙体基材和锚栓组，不出现地基基础。上游输入变化后，仅对应节点及下游结果过期；重新计算创建不可变场景修订。

### 计算模块

- 钢结构：简支/悬挑梁、轴压/压弯柱、单跨门式刚架。
- 混凝土：矩形梁、单向板、矩形/圆形柱。
- 木结构：简支/悬挑梁、轴压柱基础验算。
- 基础：柱下方形/矩形独立基础、墙下条形基础，含压力、偏心、滑移、倾覆、剪切/冲切、弯曲配筋及地下水/上拔检查。
- 荷载：版本化常用荷载目录、城市风雪向导、恒/活/风/雪及 ULS/SLS 自动组合。
- 材料：后端版本化钢筋目录，区分纵筋与箍筋，包含现行、旧项目兼容和未开放牌号状态。
- 结果：输入摘要、组合、反力/内力、逐步公式、规范来源、验算、利用率、警告、适用范围与追踪编号。

上部构件反力可以建立到独立基础的节点连接；修改上部节点后，已保存的基础结果不会被静默覆盖，需形成新的不可变项目修订。

城市风雪目录当前只录入了经人工校核的首批城市/气象站样本，并在 API 中显式返回覆盖范围，**不是全国完整库**。不得用网页抓取值或未复核数据填满目录；全国数据需在合法取得标准资料后继续录入并双人复核。

单跨刚架采用经自动化测试覆盖的二维矩阵位移法，并沿杆件取样求跨内内力和位移极值。每个模块显式保存 `verification_status`；规范映射、手算基准、规范例题和独立脚本复算未完成前，即使单项验算满足，专业模式仍返回 `incomplete`，不显示“通过”。商业软件对照可作为附加证据，但不作为唯一开放条件。

### 产品能力

- 管理员邀请账号，首次登录强制修改临时密码；
- Argon2 密码哈希、服务端随机会话、数据库仅存会话哈希；
- `HttpOnly` Cookie；生产环境可启用 `Secure`；
- 项目保存、复制和不可变版本；
- 项目修订保存 `calculations + connections + catalog_versions + result_bundle`；
- 场景实例保存向导草稿、模板版本和过期节点；场景修订保存图模板、节点结果、控制路径和完整性结论；
- 每个版本保留原始输入、计算结果、引擎版本和报告编号；
- 网页与 PDF 使用同一个计算结果对象，并保留荷载来源、覆盖原因和目录版本；
- 所有项目查询按当前用户所有权隔离。

旧 Streamlit 文件仅作为迁移期参考，入口不再接受原公开访问码。Git 历史中的旧访问码应视为永久泄露，不得恢复使用。

## 本地开发

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 和 Node.js 22。

```powershell
cd backend
uv sync --extra dev --locked
$env:STEEL_COMPASS_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:STEEL_COMPASS_BOOTSTRAP_ADMIN_PASSWORD = "replace-with-a-long-random-password"
uv run uvicorn app.main:app --reload
```

另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://localhost:3000`。首次登录必须修改管理员临时密码。

## 测试与发布门槛

```powershell
cd backend
uv run pytest --cov=app --cov-report=term-missing
uv run alembic upgrade head

cd ../frontend
npm run lint
npm run build
$env:PLAYWRIGHT_SYSTEM_CHROME = "1"
npm run e2e
```

GitHub Actions 会执行后端测试、Alembic 迁移、前端 lint/build、Playwright 交互测试和 Docker 镜像构建。任一失败即阻断后续发布。

当前自动化测试覆盖：

- 截面属性与非法壁厚；
- 各材料计算模块与五类公开场景默认闭环；
- 正负风、上拔和主导/伴随组合，反力包传递不得重复乘分项系数；
- 刚架对称荷载反力平衡、边界条件及跨内内力/位移极值；
- 独立基础中心受压/偏心/局部脱开/冲切/地下水/抗浮/资料不完整与条形基础符号基准；
- 目录检索、反力连接、不可变项目修订和合并 PDF；
- 五类公开场景、五类开发中场景阻断、DAG 循环阻断、上游修改后的下游过期、场景实例所有权和场景 PDF；
- 双入口导航、两状态工作台、传力链持续显示、移动抽屉“应用并关闭”、390px 无横向滚动和方案对比；
- 专业模式关键字段/荷载来源校验；
- 登录、首次改密、邀请账号、项目隔离；
- 不可变项目版本和 PDF 报告贯通。

当前模块仍标记为 `unverified`；待规范映射、手算、规范例题及独立脚本证据固化后，才可逐模块改为 `independently_verified` 并开放专业结论。

## Docker Compose 部署

复制环境文件并替换全部示例密码：

```bash
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

大陆生产环境建议：

- `APP_DOMAIN=app.已备案主域名`；
- `STEEL_COMPASS_COOKIE_SECURE=true`；
- `STEEL_COMPASS_FRONTEND_ORIGIN=https://app.已备案主域名`；
- 使用当前备案接入商的大陆云资源，变更接入商前完成接入备案；
- 新加坡域名不指向首期大陆应用。

Caddy 自动申请和续期 HTTPS 证书。上线前应由运维侧配置安全组、日志采集、监控和定时备份。

### 备份

生产服务器加载 `.env` 后执行：

```bash
set -a
. ./.env
set +a
./ops/backup-postgres.sh
```

可通过 cron 每日调用，默认保留 30 天。恢复脚本会明确提示将覆盖目标数据库，只有输入 `RESTORE` 才继续：

```bash
./ops/restore-postgres.sh ./backups/steel-compass-YYYYMMDDTHHMMSSZ.dump
```

必须定期在隔离环境做恢复演练，不能只检查备份文件是否存在。

## 目录

```text
backend/           FastAPI、认证、目录、项目修订、PDF、Alembic、计算引擎与测试
frontend/          Next.js 双入口工作台、场景向导与单项计算库
ops/               PostgreSQL 备份与恢复脚本
pages/             旧 Streamlit 迁移参考
docker-compose.yml 本地/单机生产编排
Caddyfile          HTTPS 与反向代理
```

## 发布前仍需人工完成

1. 将 Git 历史中的旧访问码视为已泄露，确认没有任何外部系统继续接受这些值。
2. 为每个支持模块加入至少一组有签字记录的手算基准和一组 YJK/Midas 等独立软件对照。
3. 完成规范条文逐项授权核对，记录条款版本、适用条件和修订来源。
4. 配置真实备案域名、云资源、密钥、备份任务、恢复演练和监控告警。
5. 在具备相应资格的人工复核与签章流程建立前，保持专业模式 Beta 与免责声明。

连续梁、多跨二维框架、平面桁架、钢/木柱脚、双向板、墙体、挡土墙、池体、桩基和承台已进入版本化计算库及场景图，但当前仍标记为 `planned`。在公式条文映射、基准算例和认可软件对照完成前，不提供专业“通过”结论。
