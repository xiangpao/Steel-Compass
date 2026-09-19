# Steel-Compass 本地整合审计记录（2026-09-19）

## 结论与边界

本轮交付是可回归的软件修复与明确的能力门禁，不是整个产品的正式工程验收。

- 候选基线：`bb34ded4de081f843b1bf25abbef236e72cb58e4`，已包含 Antigravity 分支 `d64ffba`。旧本地主线：`d5d59647bc66c73636c1ac01df20af74e73fd4f4`。
- 恢复引用：`codex/recovery-main-20260919`、`codex/recovery-v2-20260919`。修复分支：`codex/full-audit-20260919`，独立工作目录 `Steel-Compass-audit`。
- 本轮已确认的危险通过路径已修复或明确阻断；独立代码复核限定在这些修复，未发现尚未安全关闭的本轮 P1。未接入生产的实验计算辅助实现不属于本轮准入保证。
- 33 个模块全部仍是 `unverified`；正式工程结论不允许升级。公开算例只验证有限弹性力学模型，不替代中国规范承载力与具名复核。
- 没有推送、部署、改动现有生产库/数据卷，原目录未跟踪的 `AGENTS.md`、`.agents/`不纳入提交。

## 范围对应表

逐模块入口、生产计算函数、输入、API、存储、报告、测试线索及证据缺口见 [inventory.json](inventory.json)，包含全部 **33 模块、10 类场景、40 变体**。测试文件名称关联只是检索索引，不能解释成逐项算例全部覆盖。

| 层 | 当前实现 | 审计结论 |
|---|---|---|
| 页面 | `frontend/app/page.tsx`、`scene-workspace.tsx`、`pergola-workbench-v2.tsx` | V2 主线；旧 Home.py/pages 不替换 V2 |
| 输入 | CalculationRequest、专用 typed_inputs、SceneGeometryProfile 2.3 | 旧快照只读；执行时拦截非有限值；部分场景专用模型转换仍缺失 |
| API | calculation_routes、project_routes、scene_routes | 所有权隔离继续由服务端校验；客户端不能重放服务端分析指针 |
| 计算 | engine 的 33 个 handler；nextgen→structural_solvers；场景空间杆系→space_frame | 未接入生产的同名实验文件不能作为生产正确性证据 |
| 结果 | CalculationResult、SceneRevisionResult、SceneAnalysisView | 数值筛查、工作流完成度、工程证据等级分别保留 |
| 存储 | ProjectVersion/Revision、SceneInstance 草稿、不可变 SceneAnalysisSnapshot | 条件/截面/草稿变化失效；新快照冻结自定义截面，不改旧记录 |
| 报告 | report.py | 从快照生成；长文本换行；反力分量来源完整保留并注明不能拼成同一组合 |

## 已复现问题、修复与回归

| 编号 | 问题与影响 | 处理 | 回归 |
|---|---|---|---|
| A01 | 商业模板占位、零值互比可返回 passed | 来源及快照文件/hash/id/path 绑定；数值通过与证据审核分离；容差上限 | test_comparison_provenance、test_pergola_commercial_comparison |
| A02 | 刚臂只缩短杆长，3m/10kN 悬臂根弯矩从30误为25kNm | 位移/力双向刚臂变换，刚区分布荷载计入总平衡 | test_space_frame_audit |
| A03 | 两弯曲方向几何刚度符号不同，等惯性响应不对称 | 统一局部转角约定；轴向张拉保留增刚效应 | 对称性、张拉、Tekla 公开参考 |
| A04 | 有释放的稳定处理可在临界附近误判通过 | 此能力明确拒绝；一阶静力仍可计算。没有声称已实现完整释放切线凝聚 | 5700kN 临界反例 |
| A05 | 钢柱零 My 隐藏 Mx；RC柱漏读上游弯矩；组合向量被合成 | 按原组合双分量线性交互筛查，保留原六分量；不是规范完整双偏压解 | test_transfer_audit |
| A06 | N=0 被当作缺失，剪力变轴力；平面梁架竖向坐标转换缺失 | 在明确模块接口转换 Vy→N，禁止按零值猜测 | 梁/平面框架/桁架/板接口回归 |
| A07 | 抗滑选最大剪力而非最大利用率；上拔基础自重仍用1.3 | 按组合利用率选择；明确上拔控制组合采用有利永久系数 | A/B 组合反例、0.9系数回归 |
| A08 | 浮重再除浮力重复扣水；中心冲切用峰值压力抵扣导致低估 | 抗浮恢复一次毛重；全接触压力积分用平均值，冲切独立包络 | 全浸没25/10=2.5；冲切1000/800kN反例 |
| A09 | 柱脚纯弯矩可输出零承压/零板弯曲通过；全接触也忽略梯度 | 全接触用角点压力；脱开接触与基础脱开结构检查明确未完成 | 100kN+5kNm得到1.414609MPa；脱开门禁 |
| A10 | 柱脚焊缝沿用其他检查控制组合 | 每项检查单独包络并保留组合名 | 500kN焊缝等效需求反例 |
| A11 | 项目条件变化与客户端草稿可保留旧结果指针 | 条件/岩土/截面变更清理草稿结果；服务端分析指针不能由客户端恢复 | test_project_invalidation；真实流程修改失效 |
| A12 | 新快照只留自定义截面引用，不冻结定义 | 自定义截面数据纳入快照和内容hash；兼容旧快照空字段 | API完整任务流、真实快照检查 |
| A13 | 亭廊无新建项目入口，嵌入后横向视区裁切；移动导航不切属性 | 新建入口、可用宽度布局、移动导航/页脚修复 | 真实桌面与390px截图、浏览器回归 |
| A14 | 保存提示被画布自动适配提示覆盖；编辑后仍显示旧结果 | 操作与画布状态分离；输入改变即清除当前结果；加载保留原岩土资料 | live-audit.spec.ts |
| A15 | 部分场景提交错误 typed_inputs，不能形成完整链路 | 禁止拿单项默认模型冒充场景；按节点显式标记能力不足，不整条流程笼统崩溃 | 40变体缺口回归、scene-smoke.json |
| A16 | 报告组合名与来源越出单元格，部分控制来源被截断 | 表格段落换行、保留全部分量来源、顶部工程未核验说明 | 真实PDF渲染前后检查 |

## 算例与误差

[public-cases.json](public-cases.json) 固定了参考版本、编号、几何/约束、EI、荷载、单位、参考值、实际值、误差和预先登记容差。8 个指标均在登记容差内：

- [Tekla 2026 Euler strut](https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderbucklingeulerstrutbuckling)：1–6 单元，L=10m，EI=100Nm²，轴压1N；六个屈曲系数。
- [Tekla 2026 second-order cantilever](https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderlinearsimplecantilever)：L=10m，EI=250000Nm²，轴压4000N、横力45N；位移与根部力矩。

来源不提供中国材料牌号，按刚度等效构造模型；不作规范承载力比较。原有19个模块的有限独立闭式复算由 inventory 对应到三个 evidence register。本轮重跑相关测试，但没有把原有 `unverified` 提升。其余模块不能填写虚假的外部误差值，明确记录 `external_same_model_comparison=not_completed`。

## 场景覆盖结果不是40个工程通过

[scene-smoke.json](scene-smoke.json) 是目录默认条件与显式确认测试荷载下的输入/图执行检查：40项无未捕获异常；**6 ready、24 capability_unavailable、10 stale**。stale 是现有工作流对不完整上游的传播状态，不代表历史工程已经算过。

这些结果揭示了专用场景输入转换、完整组合/反力链及能力不足；不能说40变体均完成端到端计算。具备单项专用输入的计算器仍可独立使用；将其接入每个场景还需逐场景模型/荷载映射和真实流程复核。

## 实际验证

- 后端：`python -m pytest -o addopts='' -q --tb=line --cov=app --cov-report=term`：**613 passed**，app 行覆盖率 **92%**。唯一剩余警告是 FastAPI TestClient 的 httpx 弃用提示；覆盖率不等于工程证明。
- 前端：`npm run lint`、`npm run build` 通过。
- 浏览器：本机 Chrome，**21 passed**（20项现有模拟/QA回归，1项真实后端完整任务流）。真实库为隔离 `audit-live.db`，端口18000/3100。
- 实际任务流：登录、新建、项目条件、保存、计算、快照、PDF、修改失效、再保存、刷新、390px布局。既有API测试覆盖修订、复制、权限隔离和报告；**真实浏览器的方案对比、所有失败项定位、离线重试与全部键盘/读屏验收未完成**。
- 迁移：空 SQLite 与 `20260730_01` 旧版隔离库升级到 `20260813_07`，保留原用户/项目行。
- Docker 管道 `docker_engine` 不存在，当前无法连接 daemon；容器构建、容器健康入口与 PostgreSQL 空/旧库迁移 **未执行**，不引用历史成功记录。
- 独立复核最后一次运行相关99项测试通过，结论仅覆盖本轮已确认缺陷的安全关闭。

本地证据：`frontend/output/playwright/live-saved-desktop.png`、`live-result-desktop.png`、`live-mobile.png`、`live-report.pdf`、`live-report-page1.png`、`live-report-page3.png`；原始日志在 `artifacts/backend-final.txt`、`artifacts/frontend-build.txt`。这些运行产物不作为正式工程证据。

提交内保留的证据：[保存页面](screenshots/live-saved-desktop.png)、[结果页面](screenshots/live-result-desktop.png)、[390px页面](screenshots/live-mobile.png)、[报告首页](screenshots/live-report-page1.png)、[报告组合表](screenshots/live-report-page3.png)、[后端验证日志](backend-final.txt)、[前端构建日志](frontend-build.txt)。PDF本地渲染已检查；截图不能代替所有数据项的独立复算。

## 未完成的正式验收项

1. 33模块逐条中国规范映射、独立手算签署、适用的真实商业软件导出与具名复核。
2. 含释放杆件的二阶/屈曲、底板/基础脱开压区耦合；当前安全阻断，不算功能实现完成。
3. 部分场景专用输入转换、每变体完整传力链及全部操作路径验证。
4. 每个模块/变体的外部独立基准和适用边界穷尽验证；本轮8指标不能代表全产品。
5. Docker/PostgreSQL实环境验证、浏览器方案比较及全面无障碍验收。

因此，“本地软件整合”和“完整计划/正式工程验收”必须分别报告；后两者仍未完成。此次局部软件准入不解除上述门禁。
