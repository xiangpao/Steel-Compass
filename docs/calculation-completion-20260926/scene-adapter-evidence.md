# 场景 typed 输入与传力补全证据

2026-09-26；隔离工作树 `Steel-Compass-audit`，基线 `af8b031`。本记录描述本地计算合同和专项回归，不改变历史快照、专业验证级别或发布状态。

## 结果与范围

- 原先缺少专用转换的 27 个变体已能用显式专项输入生成其专用模型。实现覆盖连续梁、平面框架、双向板、RC 水池、钢木桥、RC 桥、群桩承台、三种景墙及重力式挡墙；不调用前端单项 `buildTypedInputs` 的隐藏几何/荷载/材料默认值。
- 新参考矩阵 `scene-variant-matrix.json` 共 40 变体：25 `ready`，15 `capability_unavailable`，0 `stale`。新增 typed 节点均实际产生计算结果；不是仅检验不抛异常。15 项剩余阻断来自柱脚受拉底板局部机制和基础等控制，不是 typed 转换缺失；逐节点 `warning_codes` 保留实际原因。`ready` 仍可能为 `screening_failed`。
- 所有计算结果保持 `unverified`。未进行生产部署、商业软件比对或专业签署。真实浏览器交互、全量前端构建及最终独立审计由主执行汇总。

## 最终矩阵状态解释

40 变体中，25 个工作流 `ready`：13 个 `screening_passed`，12 个 `screening_failed`。后者是当前显式尺寸/材料/荷载下至少一项方案验算不满足，不是执行器异常，也不能报告为工程合格。另 15 个 `capability_unavailable` 的 `quick_outcome` 为空，表示仍有必需计算机制不完整，不能计入通过或不通过。无 `missing_inputs` 或 `stale` 变体。

15 个未完整变体为：亭廊 `guided-grid / flat-single / mono-pitch / dual-pitch / multi-bay`；雨棚 `single-row / double-row`；导视 `single-post / double-post / ground-mounted / eccentric-panel`；入口 `single-span / multi-span / eccentric-lintel / unequal-columns`。矩阵保留每个节点的 `calculation_status`、是否存在计算结果及警告，能够区分未执行节点与已执行但机制不完整。

222 个节点中，171 个计算节点实际返回结果（110 `passed`、13 `failed`、48 `incomplete`）；51 个为荷载/边界/接口节点，不要求独立计算结果。40 次执行全部返回；没有把抛异常计作正常计算失败。所有 171 个计算结果的证据等级仍为 `unverified`，独立代码/数值探针通过不改变工程专业核验等级。

## 输入合同

前端将全场几何保存到 `parameters`，专项数值保存到 `parameters.scene_node_inputs[node_id]`，请求携带 `inputs.scene_parameters` 及该节点专项字段。专项输入初始为空，后端缺项返回字段名，不生成另一套模型。已有截面选择面板扩展到连续梁/平面框架；后端读取保存的材料、截面目录及强弱轴，推导 A、I、W、自重及方案级截面承载力。柱脚边界、梁分担宽度、门楣迎风高度、材料/配筋/桩承载力等均有显式入口。

梁、框架、板采用全场统一作用方向分支与既有 `FACTOR_SETS`。节点本地作用与上游同 ID、同限态组合相加，避免组合笛卡尔积。接收节点自重仅在传力后按该组合加入一次。相邻梁在同一物理支座汇合时，逐组合相加六分量，不覆盖前一条反力，也不拼接不同组合的最大分量。重算前清除旧反力 sidecar。

没有物理作用位置的 kN 集中荷载或集中弯矩明确返回 `physical_application_position` 缺项；不会把 kN 当作 kN/m 再乘跨度。这仍是范围限制，不宣称集中荷载场景位置编辑已完成。

## 真实几何和新增传力

1. 单坡、双坡及双跨亭廊显式建立前后两榀框架，分别接收纵向檩条两端反力，并传至 4 / 4 / 6 个基础。4×3 m 屋面恒载增加 1 kPa，SLS 全部柱脚合力增加 12 kN；双跨为 24 kN。旧单榀图只接收半片屋面的问题已修复。檩条节点明确是按分担宽度重复的构件代表，前后框架和基础逐个建模。
2. 平台新图 `viewing-platform-four-edge-chain-v33` 为四条真实边梁、四角支承、四基础。用户必须选择“45°几何分担法”；四边简支板的三角/梯形分担宽度为 `min(x,L-x,a/2)`，每段斜坡划分 8 段，按中点均布荷载积分。短边面积 a²/4、长边面积 ab/2−a²/4，四边面积合计 ab。每角汇总相邻两梁端反力，未使用任意 load_share。该法是明确的方案级几何分担假定，**不是弹性板精确边界反力**；固边板在此图不开放，前端不再提供该选项。
3. 斜梁加载支持 `FrameUniformLoadInput.local_x`。全局竖向均布荷载按投影长度分解到局部 x/y；二维内核形成 qx 一致等效载荷，恢复 `N(x)=-f0-qx*x`，轴向位移包含 `qx*x*(L-x)/(2EA)`。自重同样使用分布项，不再把轴向 UDL 只作为端部节点力而漏掉杆内轴力。
4. 群桩承台要求显式 `cap_concrete_unit_weight_kn_m3`、地下水条件与依据。承台重量按上游真实 `permanent/dead/self_weight` 系数进入当前组合轴力一次。已知淹没高度还需水重度；ULS 浮力系数使用已有上游 uplift 系数，或要求用户明确提供，不虚构地下水。未知水位、缺重度/组合系数均返回具体缺项。

## 专项测试与独立探针

运行目录 `audit/backend`；Windows 主机使用原项目虚拟环境；为避免同机并发 OpenBLAS 内存膨胀，固定线程数为 1：

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
& 'C:/Users/86137/Desktop/IP-Builder/03_Projects/Steel-Compass/backend/.venv/Scripts/python.exe' -m pytest tests/test_scene_typed_adapters.py tests/test_parametric_frame.py tests/test_scene_structural_variants.py tests/test_scene_site_walls_gravity.py tests/test_scene_pool_bridge_pile_variants.py tests/test_milestone_scenes.py -q --tb=short
& 'C:/Users/86137/Desktop/IP-Builder/03_Projects/Steel-Compass/backend/.venv/Scripts/python.exe' -m tests.test_scene_typed_adapters
```

最新结果：**151 passed**。其中新适配专项 78 例，其余为二维内核和原场景回归。fixture 文件 `backend/tests/test_scene_typed_adapters.py` 的 SHA-256：`33767679ff5d0457aa1b3528a265bfe080ba663ebdbfbc0220d9e786962dc6f3`。

覆盖：每个新增主模型的几何/荷载敏感性；连续梁、双向板及斜屋面全局力平衡；池水质量增量；钢木/RC 桥人群荷载乘桥面面积的增量；挡墙附加土压力；桩六分量的同组合传递；平台四边/四角逐组合守恒、本地 +10 kN/m 线荷载在两南角各增加 15 kN且无重复包；亭廊两榀全屋面传力；导视牌正负风；缺项拒绝；guided-grid 未完整稳定范围向场景状态传播。

独立代理复核记录见 `adapters-independent-review.md`。该代理提出的四项 Important 已修复，并使用其原始数值探针回验：

| 探针 | 独立期望 | 修复后复核 |
|---|---:|---:|
| 3×3 m 承台厚度 0.5→1 m，γ=25，SLS 每处桩合力增量 | 112.5 kN | 112.5 kN |
| 4×3 m 亭廊屋面恒载 +1 kPa，SLS 全部柱脚增量 | 12 kN | 12 kN |
| 南边梁 3 m 长，本地线荷载 +10 kN/m，南角各增量 | 15 kN | 15 kN；同组合仅两端包 |
| 斜梁 (0,0)→(4,2)，水平投影 q=7 kN/m，两端最大轴力 | 6.260990336999411 kN | 6.260990337000539 kN |

平台连续三角/梯形精确控制值与目前离散值的弯矩/挠度差小于 0.4%（独立报告的当前 3×4.5 m 算例），不是任意比例的收敛证明，也不把分段近似升级为精确控制。

## 边界

- 平面模型不等价于完整空间扭转、节点抗震构造或任意斜梁非线性分析；截面承载力仍为方案筛查。原型水池、桥和墙模型的已有适用边界继续生效。
- 新参考 fixture 的 typed 专项字段全部显式，旧快算节点沿用其既有合同并显式给出钢截面、基础与本轮接触参数；这不等于所有旧快算隐藏参数或完整用户项目均已完成生产验收。
- 历史图/快照未重写。新亭廊两榀图和四边平台图更改了当前拓扑，旧输入应重新确认新增实体与专项字段，不静默覆盖旧修订。
