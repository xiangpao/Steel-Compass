# 计算能力补全与独立审计 — 2026-09-26

> **2026-11-01 补记（历史数值待复算）**：计算核心修正了参数化亭廊空间分析的组合方式（改为逐个真实组合求解，±X/±Y 风不再相互抵消）、按节点命名支座反力的取用顺序、多杆件汇合反力的组合一致性、基础标量上拔的重复扣减、控制组合标签，以及非棱柱基础转换截面有效高度。以下已记录结果据此被取代，需按项目验证流程重新生成后再引用：本目录 `scene-variant-matrix.json` 与 40 变体状态统计、`live-report.pdf`/`live-evidence-summary.json` 中的“最大空间位移”和基础结果、`backend-tests.txt`；`../landscape-validation-20260926/scene-variant-matrix.json` 中的多跨/双柱框架基础结果。下文数值保留为历史快照，未改写；全部模块仍为 unverified。

基线 `af8b031`；在 `codex/complete-calculation-gaps-20260926` 隔离工作树实现。范围是软件计算能力及证据补充，不是工程签署。不推送、不部署，不改既有数据库卷、历史快照或本地规则文件。

## 已实现

| 原缺口 | 当前实现与证据 | 适用边界 |
|---|---|---|
| 二阶沿杆包络 | 梁柱初应力二阶力/位移恢复、杆内极值、自适应细分及平衡/收敛检查；[求解器证据](solver-evidence.md) | 小转角 Euler–Bernoulli；不是任意几何/材料非线性 |
| 杆端释放稳定 | 释放面自由度参加弹性/几何刚度；刚臂与滑移面分别恢复；[独立复审](independent-review.md) | 桁架几何刚度、扭转/侧扭/翘曲屈曲仍明确排除并传播 incomplete |
| 脱开接触 | 无拉受压区域积分、显式锚栓弹簧兼容、逐组合平衡、基础正负弯矩与上层配筋输入；[接触证据](contact-evidence.md)、[独立复审](contact-independent-review.md) | 接触收敛不能证明受拉底板的局部弯曲/撬力合格；缺少机制或输入仍阻断 |
| 场景转换 | 27 个原转换缺口接入已保存的几何、材料、荷载和六分量反力；[转换证据](scene-adapter-evidence.md) | 全部 40 变体能执行登记的参考输入，不等于全部完整或通过 |
| 专业证据 | 固定 Tekla 8 项、Dlubal 2 项公开参考指标；核读 GB 55006 官方资料；清理四条未关联原件的旧 verified 声明；[专业交接](professional-evidence.md) | 公开基准/独立 Agent 不替代真实软件同模型导出和具名签署；全部 33 模块 unverified |

## 独立审计关闭记录

- 求解器：稳定范围 incomplete 未向包/API/构件结果传播；刚臂滑移的位移恢复不一致。已修复，独立手积分与集成复测通过。
- 接触：纯拉共线锚栓存在未约束转动却可能报收敛；锚栓真实间距/边距未控制容量；同名组合导致基础自重系数错配；上层钢筋控制组合丢失。四项均先固化回归再修复，独立复测通过。
- 场景：承台自重遗漏；屋面另一端反力未进入基础；平台局部边荷载丢失且组合重复；斜杆轴向分布荷载未恢复杆内轴力。四项均由独立 Agent 的原始探针复测通过，见[完整报告](adapters-independent-review.md)。
- 旧专业证据声明恢复为 unverified，保留 Git 历史及缺口说明，不将无关联的审核组名称当签署。

## 40 变体的真实状态

[逐节点矩阵](scene-variant-matrix.json)：25 个工作流 ready，其中 13 个 screening_passed、12 个 screening_failed；另 15 个 capability_unavailable，不能计为通过或不通过。没有 typed 转换缺项或 stale。171 个计算节点返回 110 passed / 13 failed / 48 incomplete；51 个荷载/接口节点不要求独立计算结果。全部结果 unverified。

15 个未完整变体涉及亭廊、雨棚、导视和入口的柱脚/基础链；受拉底板局部弯曲、撬力等机制仍阻断。不能据“有结果”称完整安全边界已验证。

景观设计调整柱径、壁厚、柱距时，可以比较同一荷载/模型边界下的需求、位移及利用率变化，定位控制构件；应同时查看连接、基础、适用范围和结果完整性。截面变粗不代表整个传力链自动合格。前轮[景观敏感性验证](../landscape-validation-20260926/README.md)与本轮同组合传力回归共同保留。美观、通行/遮阴功能和场地协调需由设计者评价，软件不生成虚假的综合最优评分。

## 验证与运行环境

- 后端全量 pytest：853 项通过，63.69 秒，exit 0；语句覆盖率 92%，仅一条 Starlette/httpx 弃用警告。[输出](backend-tests.txt)
- 前端 lint、生产 build：通过。[构建输出](frontend-build.txt)
- 公布参考：Tekla 8/8、Dlubal 2/2 在预登记容差内；[Tekla](tekla-public-cases.json)、[Dlubal](contact-public-cases.json)。不在结果出来后放宽容差。
- PostgreSQL 17.10：新建隔离 tmpfs 实例，空库迁移、旧版库带数据迁移及重复迁移通过，旧行/输入/快照内容保留。[结果](postgres-migration.json)
- 真实后端＋独立 SQLite 数据库＋生产前端浏览器任务流 1 项通过（1.3 分钟）：登录、新建、保存、完整分析、快照/PDF、修改失效、刷新恢复、390px 无横向溢出。[真实输出](live-browser.txt)、[模拟回归 21 项](browser-regression.txt)、[快照与 PDF 哈希](live-evidence-summary.json)。真实 PostgreSQL 的本轮范围是迁移与历史数据保留，未把 SQLite 浏览器流程说成 PostgreSQL 全栈验收。
- 目视检查[桌面结果](ui/live-result-desktop.png)、[390px 项目条件](ui/live-mobile.png)、[接触参数输入](ui/completion-contact-mobile.png)。当前快照结构/构件/屈曲为 complete，连接/基础和总工作流 incomplete；页面、快照、PDF 状态一致。PDF 内容哈希与不可变快照一致，输入地区/风雪/地震/单位对应；后续修改为内陆后旧结果失效，刷新保留新输入。
- [真实 PDF](ui/live-report.pdf) 199 页，保留逐组合接触详情；全页渲染缩略图和第 1/20/100/199 页抽查无裁切或缺字。该文件是完整审计计算书，篇幅较长，未宣称为精简汇报版。完整快照原始 JSON 约 53 MB，保存在被 Git 忽略的 frontend/output/playwright/live-snapshot.json，本目录只存摘要/哈希；大型模型的存储和页面传输仍有优化空间。
- Docker Desktop 本轮成功启动并运行了上述隔离 PostgreSQL，但新前端镜像构建遇到宿主提交内存不足和构建器 EOF，未完成新镜像构建、全栈健康检查或新容器入口验证。启动曾恢复旧容器，不把旧镜像健康视为当前代码验收。测试结束恢复 Docker 停止状态；既有卷未清空。该项继续阻塞容器交付验收。

主要命令（后端 cwd 为 backend，线程环境 OPENBLAS_NUM_THREADS=1、OMP_NUM_THREADS=1）：

```text
python -m pytest -o addopts= --strict-markers -q --cov=app --cov-report=term:skip-covered
python -m verification.audit_public_cases --output ../docs/calculation-completion-20260926/tekla-public-cases.json
python -m tests.test_scene_typed_adapters
npm run lint
npm run build
npx playwright test --workers=1
```

实际解释器使用原工作目录 backend/.venv/Scripts/python.exe，导入的是隔离工作树代码。前端构建使用临时 NODE_OPTIONS=--max-old-space-size=512、RAYON_NUM_THREADS=1、UV_THREADPOOL_SIZE=1，未修改宿主持久配置。

覆盖缺口：space_frame 96%、contact/baseplate/foundation 各 93%、scene_typed_adapters 88%、scene_routes 79%、report 89%。这些是语句覆盖率，不能证明物理机制和所有参数域正确；API 低频分支、格式异常及未开放机制继续按各专项边界列出。独立外部算例、极限/非法输入、平衡与敏感性测试才提供对应数值证据。

真实流程曾触发默认 30 秒代理中断。定位到沿杆多项式对象算术的重复开销后，保留数学/极值搜索/收敛阈值改用系数数组和 Horner；同工况最大差约 7×10⁻¹⁸，独立复审通过。18 节点/21 杆、14 工况加 132 组合的完整力学包实测 43.95 秒，见 [测时](solver-performance-after.json)。同步代理设置有界 180 秒预算；未删除组合或放宽计算容差。

## 尚不能关闭的验收

1. 受拉底板局部弯曲/屈服线、撬力及垫板局部承压；非等厚基础自重分布、土塑性与沉降接触耦合等超出已实现模型的机制。
2. 被明确排除的桁架几何刚度和扭转/侧扭/翘曲屈曲；未提供作用位置的集中荷载不能靠换单位模拟。
3. 逐模块规范映射、实际认可软件同模型原件/导出、具名复核和工程签署。来源与交接字段已准备，用户未提供这些真实资料。
4. 当前代码的 Docker 全栈构建及容器入口验证。

本地主线软件整合与正式工程验收分别报告；上述缺口不通过修改标签或使用测试夹具关闭。

## 本地整合与恢复

审计分支 `codex/complete-calculation-gaps-20260926`；原主线和候选恢复引用分别为 `codex/recovery-main-before-completion-20260926`、`codex/recovery-completion-candidate-20260926`，均指向 `af8b0312c9500e89372354a5e9b0aef640d9f61c`。最终提交号和快进结果以交付消息及本地 Git 记录为准；没有强制覆盖主线或远程写入。原目录的未跟踪 AGENTS.md 与 .agents/ 保留。
