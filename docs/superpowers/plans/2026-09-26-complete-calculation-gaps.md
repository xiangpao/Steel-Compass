# Calculation capability completion Implementation Plan

**Goal:** 补齐已登记的二阶沿杆包络、杆端释放稳定、部分接触、场景转换和可独立取得的专业证据，保持历史快照及工程签署门槛。

**Architecture:** 在既有 FastAPI/Next.js 与 SpaceFrameModel 上兼容扩展。求解器输出可追溯的沿杆状态；接触求解独立保存受压区域和力矩平衡；场景转换由已保存几何/荷载显式生成专用输入。数值完成与具名专业审核分开。

**Tech Stack:** Python/NumPy/SciPy/Shapely/Pydantic/pytest，TypeScript/React/Playwright。

用户已授权实现与独立Agent审计；本工作树沿用隔离目录，基线af8b031，不推送、不部署、不改AGENTS/.agents或生产数据库。没有可用的superpowers执行技能，直接依现有TDD、系统调试与独立代码审查技能执行。

## A 求解器（独立执行）
- [x] 在 `backend/tests/test_space_frame_audit.py` 与新增专项测试固定释放等价、铰支临界、双轴、轴拉/轴压、分布荷载与0.99/1.01临界边界；先运行确认现有guard失败。
- [x] 修改 `space_frame.py`：释放的内部面自由度参与几何刚度与屈曲，不用弹性凝聚矩阵冒充切线凝聚。实现二阶沿杆力/位移及极值恢复；保留不稳定拒绝。
- [x] 修改 `scene_space_frame.py` / `scene_member_checks.py` 接入已验证输出；只有有完整能力元数据的构件解除not_calculated。
- [x] 以 `python -m pytest tests/test_space_frame.py tests/test_space_frame_audit.py tests/test_landscape_safety.py` 及新专项文件复测；外部公式/算例固定参考独立于生产代码。

## B 部分接触（独立执行）
- [x] 新 `contact.py` 与 `test_contact.py`：矩形受压无拉接触满足N/Mx/My，单向三角压区100kN/40kNm/2×1m应qmax111.111111kPa；双向及对称反转、无解/纯上拔明确测试。
- [x] 将压区积分与结果接入 `foundation.py`，修正需要真实压区的冲切/弯曲，而非截断负压力；独立核查浮力/自重只计一次。
- [x] 对 `baseplate.py` 建立受压混凝土与受拉锚栓兼容平衡；缺少必要刚度/锚栓布置时必须明确缺项，不虚构默认参数。
- [x] 执行接触/基础/柱脚/传力专项测试并保存来源与局限。

## C 场景转换（独立执行）
- [x] 根据 `scene-variant-matrix.json` 逐模块识别27个转换缺口，检查前后端保存参数与typed schema，不套单项默认模型。
- [x] `scene_graph.py` 与专用适配模块接入几何/荷载/上游反力；`scene-workspace.tsx` 传递缺失字段。对确实缺输入的变体返回具体字段缺失。
- [x] 每个新增转换有参数变化测试与荷载总量/支承反力守恒测试，覆盖完整40变体能力矩阵；不以“无异常”代表计算通过。

## D 专业证据与集成（主执行）
- [x] 查发布机构/厂商原始资料，保存来源版本、定位、单位、固定参考、预登记容差、哈希与覆盖模块。区分公开资料、独立脚本、软件导出、人工复核。
- [x] 建立33模块×40变体能力/证据登记，运行现有独立脚本与新增公开基准；既有未签署材料不改成已审核。
- [x] 全量pytest、lint/build、真实后端操作和报告状态一致性；独立数据库保留既有卷。
- [x] 独立Agent交叉复审修复，完成所有可执行工作后本地快进合并；缺失真实软件导出和专业签署明确列为外部阻塞，不伪造结论。

实施与专项验证见 docs/calculation-completion-20260926/README.md；勾选表示已执行对应工作，不表示所有物理机制或正式工程验收通过。真实浏览器/PDF最终结果和本地合并以总报告最终记录为准。
