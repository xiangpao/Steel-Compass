# 景观设计参数与场景契约独立审计

日期：2026-09-26。工作树：`Steel-Compass-audit`，分支 `codex/landscape-safety-20260926`。

## 审计结论

柱边长、壁厚、节点位置确实能够进入截面性质、空间刚度、杆端内力和支座反力链，不能把当前产品简单描述为“只画模型、参数不参与计算”。但它也不能证明“把柱做细、把柱距拉大后，页面筛查通过就安全”：构件稳定/变形采用有限的方案级近似；长度与约束假定、节点、锚固、基础和场景输入转换均存在明确边界。所有工程验证等级继续保持 `unverified`。

本子审计复现并修复了三个参数契约缺陷：强/弱轴方向被忽略、方管宽度输入静默失效、非标准支座自由度被忽略；另限制了工作台不受支持的 Q390B 选项。未增加钢材强度表，未补做 typed adapter，未发布、推送或改动生产数据库。

主审计进一步将含轴力杆件的二阶沿杆弯矩/变形包络标为未完成：杆端二阶力已经传递，但沿杆极值尚未独立验证时，构件返回 `not_calculated` 和 `utilization=null`，不会继续冒充利用率通过。本子审计相应修复结果 UI 的 null 格式化，显示未完成构件数量及原因，未完成构件/连接/基础不再用绿色通过样式。

## 参数从界面到计算的链路

| 景观设计操作 | 当前实际传递路径 | 可依赖的结论与边界 |
|---|---|---|
| 调整方管柱粗细/壁厚 | `pergola-workbench-v2.tsx` 的 `sectionDrafts` → `persistProjectModel` 自定义截面修订 → `member_types.section_id` → `scene_routes._structural_profile_from_saved_geometry` → `scene_space_frame` | 截面 A、Iy、Iz、J、自重进入模型，宽厚比、回转半径与截面承载进入构件筛查。修改作用于同类型全部构件，不是仅选中的一根。 |
| 调整矩形管强弱轴 | 类型 orientation → 本次修复的空间适配器局部轴旋转 | 原先强弱轴结果完全相同；现 weak=90°。显式单根角度优先，避免相加成 180°；在 UI 改方向会同步已有显式角度。 |
| 拉大柱距/改变柱高 | `updateNode`/二维编辑修改节点坐标 → 杆长、单元矩阵、屋面分担条带、风荷载投影 → 反力 | 这是真实几何变化。节点/连接必须保持实际设计意图；只移动柱顶可以形成斜柱，不能将任意拖动解释成自动重建正交柱网。 |
| 设置刚接/铰接 | `updateMemberType` 更新起终端 release DOFs → `SpaceMember` | 类型切换是批量作用；必须同时审查整体稳定。删除柱但保留梁不代表剩余模型稳定。 |
| 设置支承 | `SupportAssignment` → 空间适配器 → `SpaceRestraint` | 完整固定、标准铰支可计算。弹簧原先已有阻断；本次增加非标准 `restrained_dofs` 阻断，不能静默代换。 |
| 修改后重算基础 | `/analyze` 按已保存 Geometry 2.3 读取自定义截面，组合支座反力 → 柱脚、短柱、基础 | 局部修改不能只检查梁柱。柱脚、锚栓、短柱、地基随组合反力重新审查；基础候选不等于最终基础设计。 |
| 保存后继续修改 | 前端 effect 清空分析，后端几何/项目条件更新清空服务端分析指针和基础候选 | 源码具备失效处理。本子审计未进行浏览器异步编辑竞争条件验证。 |

主要定位：

- `frontend/components/pergola-workbench-v2.tsx:763` 结果失效 effect；`:982` 节点编辑；`:989` 构件类型编辑；`:1372` 保存；`:1490` 分析入口；`:1610` 牌号/尺寸界面。
- `backend/app/core/design_profiles.py:616` 自定义截面计算，矩形空心截面在 `:639` 开始计算 A/I/J。
- `backend/app/routers/scene_routes.py:534` 保存几何到结构 profile；`:566` 分组无支撑长度；`:748` 调用计算；`:598` 支承组合反力；`:85`、`:329` 服务端分析失效。
- `backend/app/core/scene_space_frame.py:260` 支承契约检查；`:286` 类型映射；`:301` 方向来源；`:331` 单元截面/释放/偏移/旋转装配；其后为荷载条带与反力求解。
- `backend/app/core/pergola_analysis.py:99` 组合结果作为构件检查依据；`:108` 默认长度参数；`backend/app/core/scene_member_checks.py:68` 构件筛查入口。
- `backend/app/core/scene_column_base.py:47`、`scene_foundation.py:276` 接收支承反力；基础通过 `scene_foundation.py:58` 读取真实组合 `_cases`。

## 可复现问题与本次处置

### P1：强弱轴 UI 设置不参与空间刚度（已修）

初始复现使用 `test_pergola_analysis40.geometry_23()`，经保存契约与 API profile 转换后，只将 `member_types.orientation` 全部改成 `weak_axis`，完整求解结果仍完全相同，最大节点位移均为 `0.005616 mm`。

原因：适配器以前只读取 `member.design_parameters.local_axis_rotation_deg`，不读取类型、单根截面覆盖或旧 role specification 的 orientation。类型选择的强弱轴未触达刚度矩阵。

修复后采用更清晰的 4m RHS-200×100×6 水平悬臂，自重下端部位移由强轴 `2.303807 mm` 变为弱轴 `6.899212 mm`，比值 `2.9947005`。自动回归覆盖保存/恢复、单根覆盖与 0°/30°/90° 显式角度不重复叠加。显式单根角度优先于类型；UI 类型方向改动同步已有单根角度。

文件：`backend/tests/test_scene_orientation_contract.py`（5 例）。测试先捕获 2 个失败；最初整框架对最大节点位移的 1.2 倍断言不合理，因为柱轴向缩短占主导，随后换成明确的悬臂物理模型，保留对原缺陷的检测能力。

### P1：非标准支承自由度静默被忽略（已阻断）

原先 `restraint='fixed', restrained_dofs=['uz']` 仍按六向固定求解；`pinned` 加额外转动约束也不被采用。若输入意图是滑动/部分约束，这会改变刚度及稳定性。

回归首次运行结果为 3 失败：2 例未抛错误，1 例错误地进入整体失稳求解；修复后非空且不符合 fixed/pinned 完整定义的列表统一返回 `unsupported_support_dofs`。空列表按旧语义兼容，规范的六向固定按任意顺序接受。spring 本就返回 `unsupported_spring_support`，并非本轮新发现的静默代换。

文件：`backend/tests/test_scene_support_contract.py`（6 例）。

### P2：方管“宽”可改但不保存（已修 UI）

方管默认 `family='SHS'`。旧界面同时提供高/宽/厚，而保存表达式为 `b_mm = draft.family === 'SHS' ? draft.h : draft.b`。因此将宽改为任意值都会被高覆盖，用户无法从该输入得到矩形管。现方管只提供“边长”和“厚”，边长同步高宽，并说明同类型批量修改。没有把方管偷偷转换为矩形管。

### P2：Q390B UI 与后端强度 ID 不匹配（已限制入口）

`_design_strength('Q390B', 6)` 返回 `None`，而现有映射的 `Q390` 返回 `335 MPa`。这会令用户选择的材料没有构件筛查结果。工作台现在只开放已有主流程使用的 Q235B/Q355B；历史不支持牌号保留显示但要求重新选择，保存前校验。不新增或宣称核准任何强度表。

## 10 类、40 变体的实际任务矩阵

口径：逐个调用现有 `_execute_public_variant`，使用目录参数默认值和明确确认的参考荷载。该 fixture 对基础还明确注入 `120 kPa` 方案假定，因此它只验证旧场景图执行契约，不能代表用户项目输入、Geometry 2.3 的完整工作台或工程安全验收。生产亭廊独立 `/analyze` 路径另有 70 例相关测试覆盖。

当前 40 次运行无未捕获异常：6 个 `ready`，7 个柱脚部分接触阻断，27 个缺场景 typed 转换。`ready` 也可为 `screening_failed`，不能把执行完成写成筛查通过。

| 类别 | 景观人员的真实任务 | 可走完参考链的变体 | 当前阻断/缺口 |
|---|---|---|---|
| 亭廊 5 | 改柱截面、柱距、缺柱、坡屋面、屋面覆盖，比较梁柱与基础 | 旧图无 ready；生产 Geometry 2.3 可进入空间模型分析 | guided-grid/flat-single 旧图触发柱脚部分接触；mono-pitch/dual-pitch/multi-bay 的旧图缺连续梁 typed adapter。不能把工作台有坡屋面和旧图参数接口混为一种实现。 |
| 雨棚 3 | 落地或附墙，单排悬挑/双排，屋面上拔与墙锚固 | wall-cantilever：ready，但本参考输入筛查失败 | single-row/double-row 柱脚接触阻断；附墙形式不等于已验证既有墙承载、锚固施工和围护适配。 |
| 导视牌 4 | 立柱细化、面板增大/偏心、双柱分担、风反向 | 无 ready | single-post/eccentric-panel 柱脚接触阻断；double-post/ground-mounted 平面刚架 typed adapter 缺失。 |
| 景墙/围栏 4 | 墙高/柱距/墙厚、RC/钢填充/砌体选型 | constrained-masonry：ready，参考输入筛查失败 | concrete-straight/steel-infill/plain-masonry 专用 typed adapter 缺失；整体同时呈 stale，不能误判成只需再点一次计算。 |
| 门楼 4 | 通行净宽、门楣加高/偏心、双跨、不同柱高 | 无 ready | single-span 柱脚接触阻断；multi-span/eccentric-lintel/unequal-columns 平面刚架 typed adapter 缺失。 |
| 栈道/平台 2 | 主次梁跨度/间距、柱高、木面板、观景平台 | straight：ready，参考输入筛查通过 | viewing-platform 双向板 typed adapter 缺失；长期木变形、连接、人群振动和滨水基础不能从 straight 的单次通过推断完成。 |
| 坐凳/树池 2 | 座板跨长/厚度、支承，池壁高度/土压力 | bench：ready/通过；planter：ready/失败 | 只有限定的现浇坐凳和矩形树池；异形、根系、生长、水压和材料耐久并未因此覆盖。 |
| 水池 6 | 地上/半埋/埋地、抗浮、地基或桩承 | 无 ready | rect-above/rect-buried/rect-semi-buried 及三个 `-pile` 均缺 RC 水池 typed adapter；地震本版本未叠加，温度收缩/水密和施工水位不能省略。 |
| 景观桥 8 | 单跨/多跨、钢木或 RC、浅基础或桩基 | 无 ready | single-straight、multi-span、single/multi-steel-timber-pile、single/multi-rc-shallow、single/multi-rc-pile 均缺桥梁专用 typed adapter；人行振动、地震、桥台/桩基资料未因目录存在而闭环。 |
| 挡土设施 2 | 墙高、墙趾/踵、附加载荷、排水水位、抗滑抗倾覆 | cantilever-rc：ready/通过 | gravity 专用 typed adapter 缺失；目录范围不能替代全寿命排水、水位与地勘审查，地震本版本未叠加。 |

27 个 adapter 缺口已被显式阻断，未偷偷使用单项计算器默认模型。这是正确的安全行为，但用户层面仍不是“40 个完整场景”。源码：`frontend/components/scene-workspace.tsx:1838-1844` 避免调用带默认荷载的 `buildTypedInputs`；`backend/app/core/scene_graph.py:1226` 将 typed mismatch 转为 capability unavailable。各图定义在 `backend/app/core/scene_catalog.py`。

## 尚不能由本次修复推出的安全能力

1. `scene_routes.py:566-567` 自动以类型内最长杆长作为两向无支撑长度，计算长度系数默认 1；工作台没有明确输入该工程假定的界面。对悬臂、无侧向支撑、斜柱和开敞亭廊，应由结构人员核定，不能把类型“柱”自动等同某一种有效长度条件。
2. `scene_member_checks.py` 中压弯相互作用、`phi=1/(1+lambda_bar^2)`、H/I 梁侧扭近似以及宽厚比均为有限方案筛查模型；ULS/SLS 组合检查未在服务性变形指标处严格分离。当前主审计已将含轴力且使用二阶结果的构件阻断为未计算，保留 `case_checks` 仅供诊断；不得从其中某个诊断利用率推导通过。母项目的边界仍为 unverified，不能把局部回归绿色升级为规范完整性。
3. 挠度包含节点相对位移及均布荷载简支公式近似，不是对所有边界条件、内跨极值、集中荷载及非线性曲线的通用服务性求解。不同支承情形可能保守或漏项，需专门验证。
4. 截面库计算为理想几何；制造圆角、公差、有效壁厚、腐蚀余量、材料证明不由画面尺寸自动核实。
5. 真实景观验收还涉及栏杆防坠、使用舒适度、人群振动、玻璃及紧固件、覆面脱落、排水积雪积水、维护荷载、邻近开挖/地下管线、施工阶段。当前没有证据证明这些因“场景完成”而全部覆盖。

## 验证与交付边界

- 独立回归：`test_scene_support_contract.py`、`test_scene_orientation_contract.py`、`test_scene_space_frame.py`、`test_pergola_analysis40.py`、`test_milestone_scenes.py`、`test_scene_structural_variants.py`、`test_scene_condition_profiles.py`，共 **70 passed in 5.57s**。
- 前端：`npm run lint` 与 `npx tsc --noEmit` 成功，null 利用率/未完成状态显示变更后再次通过。第一次类型检查发现条件数组中的 callback 缺失类型，补充 `value: number` 后重跑成功。
- 未由本子审计进行浏览器点选/保存/刷新、Docker、迁移、荷载规范签署或商业软件对照；不得将以上结果写成整机验收、工程可用性或施工依据。
- 主审计同时修改二阶分析传递及其他力学问题。本文件仅对本子审计范围负责；全量测试与最终统一差异由主审计收口。
- 回退范围：本子审计新增的两个测试文件、本报告，以及 `scene_space_frame.py` 中输入支承验证/方向选择和 `pergola-workbench-v2.tsx` 中四处局部参数修复；不回退其它审计代理的二阶/稳定/柱脚改动。
