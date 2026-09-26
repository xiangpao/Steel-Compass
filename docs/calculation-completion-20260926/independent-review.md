# 独立求解器复审（2026-09-26）

审查基线：`af8b031`；工作树：`Steel-Compass-audit`。本轮只读生产实现，新增独立测试。结论仅针对小转角、直线等截面 Euler–Bernoulli 初应力求解器；所有生产模块继续 `unverified`。

**当前结论（二轮复审后）：第一轮 Important 已关闭，刚臂滑移恢复缺口也已修复。此次复查范围未发现新的 Critical/Important；工程适用范围与未验证等级继续保留。以下首轮段落是历史记录，当前结果见文末二轮复审。**

## 第一轮结论

发现 1 项 Important 完整性传播缺口，已即时通知主 Agent。没有在已执行探针范围内发现新的临界荷载误放行或正负轴力颠倒。开发者测试通过不能替代下列独立探针或工程签署。

### Important：桁架稳定适用边界未传播到用户结论

`scene_space_frame.py` 新增 `stability_scope.status=incomplete`，但第一轮审查时 `pergola_analysis.py` 和 `scene_routes.py` 未读取它。结构包只区分 member checks 的 `failed`，其余均为 `complete`；屈曲包只要其他框架构件形成正特征值便为 `complete`。因此含桁架的混合模型可以把不含桁架 Kg 的部分屈曲结果呈为完整。

`scene_member_checks.py` 的沿杆完整性门槛还要求端部轴力大于阈值；零轴力桁架可绕过显式 `incomplete`。独立回归文件中 `test_zero_axial_does_not_clear_explicit_incomplete_stability_scope` 第一轮为 strict xfail，证明存在缺口。主 Agent 正在修正传播；修复验收前不能关闭此项。

### 已诚实阻断的边界：刚臂与横向平移释放同时存在

三米悬臂，末端刚臂 0.4 m，柔性端局部 y 平移释放，端节点 y/z 约束，轴压 1000 kN、y 均布荷载 -2 kN/m。求解后 32 段沿杆端弯矩残差约 0.762312 kNm，`status=incomplete`。原因是刚臂恢复使用了释放后的柔性端位移；滑移端不能作为刚臂端的刚体运动坐标。当前残差门槛有效，未出现假通过。应明确此组合仍未闭合；不得仅调松残差阈值。

## 独立证据

新增 `backend/tests/test_space_frame_independent_review.py`。参考值和物理不变性在调用生产求解器前独立确定，没有复制生产矩阵，也未使用开发者的射击法 ODE 作为本轮独立依据。

| 探针 | 参考/判据 | 第一轮结果 |
| --- | --- | --- |
| 线性变化轴力的自重屈曲 | Greenhill `q_cr L^3/EI=7.8373`，实际荷载为临界的 0.2 | 16 段最低两系数约 5.000034462，参考 5，相对容限 2e-5，通过 |
| 自重荷载超临界 | 实际荷载为同一基准临界的 1.001 | 明确拒绝 `elastic_buckling_instability` |
| 受压构件端点逆序 | 交换起终点和两端刚臂，轴向 UDL、双轴弯曲同时存在 | 节点位移与沿杆弯矩/剪力/挠度最大值不变，通过 |
| 受拉构件端点逆序 | 同上，轴力改为拉力 | 通过 |
| 刚臂与平移释放组合 | 非零残差不得 `complete` | 通过（维持 incomplete） |
| 零轴力与显式稳定 incomplete | 成员包不得 complete | strict xfail，待修复 |

实际命令：在 audit/backend，`OPENBLAS_NUM_THREADS=1`、`OMP_NUM_THREADS=1`，使用主仓库 `.venv/Scripts/python.exe` 顺序运行：

- `-m pytest tests/test_space_frame_independent_review.py -q`：5 passed、1 xfailed。
- `-m pytest tests/test_space_frame_completion.py tests/test_space_frame_audit.py -q`：56 passed。

## 一手来源核对与适用范围

- [Trimble / Tekla 2026：Euler strut buckling](https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderbucklingeulerstrutbuckling)：已在线核对 0–5 内节点的六个公开数值。它们是特定离散化的收敛基准，单单元系数 12 不是 Euler 连续体精确值。
- [Trimble / Tekla 2026：Simple cantilever](https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderlinearsimplecantilever)：官方明确排除剪切变形与几何更新；167.7 mm 和 1.121 kNm 是单有限元结果，不能把这两项通过写成任意大位移或精确梁柱验证。
- [原始研究：Structural Analysis of Self-Weight Loading Standing Trees to Determine Its Critical Buckling Height, Sustainability 2023, 15(7), 6075](https://www.mdpi.com/2071-1050/15/7/6075)：在线搜索返回的正文 §2.7.2、式(28)–(29)给出 Greenhill 系数。换算 `I/A=D²/16` 得测试的无量纲表达式。随后网页直接 open 遇到 429；未把该网络故障解释为来源不存在。
- [Oasys GSA：P-delta Analysis](https://docs.oasys-software.com/structural/gsa/version/10.1.63/references/sbs-p-deltaanalysis.html)：官方两阶段初应力方法支持本实现的首阶轴力建立 Kg 范围，也明确二阶结果不得线性叠加。当前 pergola 按组合重新求解，符合这一点。
- [Oasys GSA：Geometric Stiffness](https://docs.oasys-software.com/structural/gsa/references/hidd-gssparam-kg/)：区分轴向 Euler、扭转及侧扭几何刚度项。当前实现仅有两个横向弯曲块；弹性扭转刚度的存在不能当作扭转/侧扭屈曲已经覆盖。工程发布说明应保留该界限。

以上是局部弹性力学、输入方向与完整性传播证据，不是国内规范承载力认可、商业软件模型导入、人工签署或生产验收。

## 第二轮集成复审

### 第一轮 Important 已关闭

已读取并核对 `pergola_analysis.py` 的组合/工况稳定范围聚合、`scene_member_checks.py` 的零轴力显式 incomplete 门槛、`scene_routes.py` 的结构/屈曲状态、missing_inputs 与 trace 传播，以及 `scene_graph.py` guided-grid 的能力未覆盖传播。第一轮 strict xfail 已移除，原失败回归现在通过。新独立包级测试还验证了两个工况的 incomplete 汇总与排除杆件去重。

PDF 汇总新增屈曲范围状态和未完成项，避免仅展示一个特征值而掩盖桁架 Kg 未计算。保存快照额外加入 engine_version 与 analysis_method；旧 snapshot_basis 本来就含 analysis，因此这里只确认版本追溯更显式，不把旧实现描述为完全没有分析结果或方法追踪。

### 刚臂滑移恢复缺口已修复

实现现在分别保存柔性端与刚臂端的位移，用节点刚体运动构造刚臂端位置。原轴压 1000 kN 探针现在 `complete`，端弯矩残差小于 0.001 Nmm，释放两侧弯矩连续、位移跳量仍保留。未降低残差容限。

独立新增零轴力手积分探针：柔性段长 l=2600 mm，刚臂 b=400 mm，q=-2 N/mm，EI=206000×10^8 Nmm²。刚臂均布荷载传递端偶矩而不传递已释放的剪力；曲率直接积分给出 `theta=q*l³/(6EI)-q*b²*l/(2EI)`、`v=q*l⁴/(8EI)-q*b²*l²/(4EI)`。柔性面位移与刚臂面 `-b*theta` 分别与计算相符。此探针未复用开发者的 ODE/传递矩阵。

### 新变化审查

- 非受压初应力跳过特征迭代：线性轴力场端点均非正时，几何刚度的应变能积分半负定，没有正的临界荷载倍数；跳过零特征子空间迭代不改变切线位移解。
- ARPACK 未收敛明确返回 `buckling_eigen_solver_not_converged`，不再冒充已证明的结构失稳；开发者的注入失败回归已在本轮实际执行。
- `stability_scope.boundary` 已明确排除桁架几何刚度、扭转/侧扭/翘曲屈曲、材料非线性和大转角。未以局部通过扩大工程能力边界。

### 本轮实际验证

使用同一解释器及单线程环境顺序运行，未启动数据库或重型整包：

- `-m pytest tests/test_space_frame_independent_review.py tests/test_space_frame_completion.py -q`：56 项通过（当时独立测试 6 项，开发者 completion 50 项，含 24 组滑移/刚臂案例、纯拉稀疏路径、ARPACK 分类）。
- 增加包级聚合与零轴力手积分后，`-m pytest tests/test_space_frame_independent_review.py tests/test_scene_typed_adapters.py::test_guided_grid_propagates_incomplete_stability_scope -q -o addopts=''`：**9 passed in 1.39s**，其中独立文件 8 项，guided-grid 集成回归 1 项。

本次未独立执行真实 PostgreSQL API、浏览器或完整 PDF 渲染；这些证据由主 Agent 另行提供。未修改生产源码，未提交或推送。

## 第三轮有界集成检查（性能优化前）

- `next.config.ts` 的 180000 ms proxyTimeout 在当前安装的 Next 配置 schema 中受支持。Docker build/runtime 继续显式设置 `API_INTERNAL_URL=http://backend:8000`，因此本地默认改为 127.0.0.1 未覆盖容器服务名。延长预算本身不构成计算性能验收。
- `live-audit.spec.ts` 从真实 analyze HTTP 响应和 report 链接对应的 snapshot 响应保存 JSON；本文件没有 API mock。尚未据此宣称真实运行已通过。
- 接触字段为可选值，旧柱脚缺字段时保持 None/空列表；新增字段未生成默认刚度。UI 新增锚栓行的零刚度是占位，后端正值与实际数量/位置校验阻止其作为有效刚度计算。
- 生产柱脚包继续 failed/incomplete，不因接触平衡求解成功改为通过。PDF 保留未验证说明、柱脚/基础整体状态、pending_checks 和 warnings。
- 实际执行 `tests/test_contact_profile_contract.py tests/test_contact_report.py tests/test_scene_column_base.py`：**11 passed in 0.74s**。这是 schema 兼容、报告文本和柱脚传参的局部检查，不是浏览器操作或 PDF 版面验收。

Minor 表达缺口已告知主 Agent：`_contact_paragraphs` 未逐组合输出 `contact_solutions[].status` 和 `missing_inputs`，缺项组合当前显示压力“—”与锚栓空列表。整体警告仍保留，因此未发现误显示通过；建议逐组合明确显示状态与缺项，方便对照真实组合。性能优化尚未进入本轮审查。

## 最终有界复审：系数数组性能优化与 PDF 缺项

**结论：此次优化与集成复查未发现新的 Critical/Important。第三轮 PDF Minor 已关闭。**

逐式核对 `space_frame.py` 的系数数组替代：Hermite 三次项和 UDL 四次 bubble 保持原式；`integral[(P0+qx*x)*v']` 的系数仍是 `P0*c_i` 及 `qx*i*c_i/(i+1)`；两弯曲轴符号、剪力导数、弦线扣除、挠度平方卷积、构成残差均与原方法一致。仍对弯矩、剪力、挠度平方和两轴残差分别求导数实根，再合入两端与中点。Horner 向量求值未缩减极值候选点，也未放松残差/收敛门槛。

额外独立数值探针使用预设三个驻点（相对位置 0.0001、0.333333333、0.9999），同时加入全零多项式及高阶尾零，在 0.1 mm 和 3000 mm 两种区间运行。全部驻点和端点被保留，最大根误差分别约 `1.39e-17 mm` 与 `9.09e-13 mm`；Polynomial 参考求值与 Horner 一致。这一探针专门检查此次改写的实根筛选和尾零处理，并不扩大整体工程验收范围。

本轮实际运行：

- 原独立文件 8 项＋接触 PDF 文本回归 1 项：**9 passed in 1.23s**。
- 公开 Tekla 复算：**8 个指标全部满足既定容差**。输出仅写临时文件 `C:\Users\86137\AppData\Local\Temp\tmpi2yl5a.tmp`，没有覆盖历史证据。
- PDF 源码及回归已确认每组合输出 `status` 和 `missing_inputs`；`UPLIFT-43 / incomplete / anchor_springs` 实际进入提取文本，第三轮 Minor 关闭。

完整 146 工况/组合的用时及浏览器/API 结果由主 Agent 的真实运行另行报告，本轮不把局部耗时或代数等价检查描述为整条生产流程验收。生产仍全部 `unverified`。
