# 景观结构安全边界独立审计

日期：2026-09-26。基线：`main cc54f0d`。修复工作树：`Steel-Compass-audit`，分支 `codex/landscape-safety-20260926`。

这是独立 Agent 对指定计算边界的源码、公开资料和局部运行审查，不是规范签署或工程验收。全部模块继续 `unverified`。未推送、未部署；未改原 main 的源码、AGENTS.md 或 .agents。复测使用原 main 的 Python 虚拟环境解释器、audit 工作树的代码。原 main 首次 `uv run` 重建了本地 editable 包，但没有变更跟踪源码。

## 结论

释放构件的二阶/屈曲阻断，以及基础双向偏心脱开后的不可用状态，是合理的保守边界。它们防止超出当前模型能力时宣称通过，不代表相关计算能力已完成。本次独立发现并在授权范围内修复两项缺陷：二阶杆端力回收与支反力不一致；柱脚纯上拔漏过接触/底板能力阻断。其余材料表、自动选柱及基础多组合候选问题仍须保留明确边界。

## 发现与处理

### P1：二阶杆端力与支反力使用不同刚度（已修复，待主 Agent 复核）

基线 `backend/app/core/space_frame.py:583` 用弹性 `K*u` 恢复杆端力，而支反力在第567行使用 `(K-Kg)*u`。同一已登记 Tekla 悬臂算例，根部反力矩是 `1.1208661417 kN·m`，杆端根矩却是 `1.2224409449 kN·m`；未施加端矩的自由端出现 `-0.0708661417 kN·m`，端剪力为 `-0.1151574803 kN`，实际施加载荷仅 `-0.045 kN`。这是节点力平衡不一致，不是舍入误差。

修复在每杆保留与整体组装相同、已包含刚臂变换的几何刚度，使用 `(K-Kg)*u-p_fixed` 回收节点作用。没有改变位移解、屈曲矩阵或参考值。`test_space_frame_audit.py:84-112` 增加公开根矩/自由端零矩检查，以及双轴、拉/压、无/有刚臂、无/有均布荷载的16项节点平衡回归。修改前17项全部失败，修改后通过。

适用性仍限于首阶轴力形成的初应力刚度、小位移线弹性分析；不是材料非线性、更新几何或完整构件内部二阶应力恢复。杆端节点作用一致不能单独证明杆内每一截面的二阶弯矩包络正确。公开算例只覆盖直杆；释放、刚臂和分布荷载组合没有由本次外部软件签署验证。

### P1：纯上拔柱脚会返回零底板应力通过（已加阻断，待主 Agent 复核）

基线 `backend/app/core/baseplate.py:240` 仅在无压力且有弯矩时阻断。构造 `N=-10 kN, Vx=Vy=Mx=My=T=0` 的 SLS/ULS 上游反力，quick 柱脚返回 `passed / ready / screening_passed`；底板局部承压、悬臂弯曲和柱底焊缝需求均为零。锚栓虽有拉力检查，也不能证明上拔力经过底板、焊缝的传递安全。

修复将 `axial < 0` 纳入既有能力阻断，删除不适用的承压/底板弯曲检查，返回 `incomplete / capability_unavailable`，`quick_outcome=None`。不是新增一个上拔底板设计公式。`test_transfer_audit.py:76-86` 修改前明确失败（实际 passed，预期 incomplete），修改后通过。当前保留的锚栓等行仍仅为风险筛查；焊缝受拉模型仍需补齐，不能把其中零需求通过当作完整柱脚设计。

一手资料：[Tekla 柱脚设计说明](https://support.tekla.com/doc/tekla-structural-designer/2025/ref_baseplatesaisc360) 分别列出上拔时底板弯曲、锚固及焊缝受拉检查。此处只用它确认力学失效模式，不套用 AISC 承载力替代中国规范。

### P2：景观构件材料厚度表不一致（未修改）

`scene_member_checks.py:11-18` 与 `steel.py` 的厚度分档不一致。例如 Q235B 厚度40～100mm前者195MPa，后者200MPa；Q355B前者40～100mm统一285MPa，后者分63/80/100mm为290/280/270MPa。后一处代码不能充当前一处的规范证据。高强材料的其他分档也有差异。

本次检索到[济南住建托管 GB 50017-2017](https://jncc.jinan.gov.cn/cms_files/jcms1/web19/site/attach/0/c24799cca3194d3ba1d87c72caa1c3ef.pdf?fileName=c24799cca3194d3ba1d87c72caa1c3ef.pdf) 的表4.4.1文本，支持 Q235 该厚度档200MPa，但它是含Q345的原版；[住建部 GB 55006 公告](https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_761191.html) 已查到，附件抓取超时；[中国钢结构协会提供的正文](https://www.cnass.cn/upload/gjgfenhui/file/20230116/1673863559727197.pdf) 不含条文说明材料表。未把第三方转载的Q355表升级为最终规范事实。

建议在取得当前适用规范原文、勘误和产品材性来源前，对未经共同映射的厚度/牌号返回未计算或限制适用范围。不得仅选较大强度来统一表。

### P2：不能称为已验证的截面/壁厚/柱距优化器（能力边界）

`scene_routes.py:1043-1073` 的 recommendations 只接收基础目标；`DesignCandidateSet` 虽有 member 类型，本次搜索未见实际构件自动离散推荐生产入口。当前可以调整截面、壁厚、几何后重新分析和比较；不能据此宣称能自动给出最安全或最经济柱距。改柱距会同时改变分担面积、跨度、二阶响应、连接和基础反力，必须重新计算完整链，不能把单根柱承载力反推为可用柱距。

`scene_member_checks.py` 的稳定系数、截面局部稳定和侧扭模型仍是简化筛查；没有本次独立规范签署。在现有矩阵外的冷弯、厚壁、自定义截面、局部屈曲和连接控制状态应保留未验证边界。

### P1：基础候选最大体积并不满足全部组合（已复现，交主 Agent 处理）

`scene_routes.py:1155-1175` 将每个组合独立推荐的基础按体积选最大一份，没有把最终长宽回验所有组合。使用 `recommend_spread_foundation_from_reaction`：共同输入N=100kN、fa=100kPa、初始L=W=0.5m、h=200mm；A组合Mx=100/My=0kN·m推荐L=0.5/W=5.1m、h550mm；B组合My=100/Mx=0则推荐L=5.1/W=0.5m、h550mm。二者均converged、各自qmax=99.1018kPa、qmin=6.8296kPa，体积相同。按路由max选择A后，其尺寸用于B组合，qmin=-417.622549kPa、qmax=523.553922kPa（含候选自重35.0625kN），严重超限。风险不是只存在于理论边界。本 Agent 未修改该路由；主 Agent 另行处理。

### 二阶传递补丁交叉审查

主 Agent 将 `scene_space_frame.py` 下游统一使用 `stability.second_order`，同时保留一阶诊断，解决了原有二阶结果未实际传递的问题。但 `scene_member_checks.py:153-170` 仍按 `M0-V*x-q*x²/2` 沿杆采样，没有轴力乘横移差的项。公开Tekla悬臂修复后M0=1.120866kN·m、V=0.045kN，L=10m，该一阶式在自由端仍残余0.670866kN·m，而真实端矩为零。某一个悬臂的最大值偏保守，不能证明一般压弯构件的内峰值不被漏算。建议二阶有轴力构件保留端部诊断，但在二阶杆内恢复/包络验证完成前不得返回构件pass/complete，应明确incomplete。该建议不是要求撤回正确的二阶反力传递。

## 既有防护的独立判断

- `space_frame.py:461-467` 对任何杆端释放阻断二阶/屈曲，仍允许独立一阶求解。弹性刚度的静力凝聚不能未经证明就等同于切线刚度凝聚。该保守阻断合理，但会阻止部分物理上稳定的释放模型；应按“不支持”理解，不能向用户解释为结构一定失稳。现有释放近临界回归通过。
- `foundation.py:782-822` 逐组合用 `N<=0` 或双向核心条件 `6|My|/L+6|Mx|/B>N` 阻断线性全接触结论。该条件对应四角线性压力最小值小于零，不应将负土压力截为零后继续宣称承载力/冲切已完整验证。现有脱开、抗浮、控制组合和浮力一次计入的回归通过。
- [SCIA 压力单向支承说明](https://help.scia.net/22.0/en/analysis/nonlinear_analysis/support_nonlinearity/support_non-linearity-basic_soil_spring.htm) 说明土体支承的压缩单向非线性建模边界；它支持采用能力阻断或压区接触求解的方向，不为本项目当前代码提供精度认证。

## 已有 public-cases 证据独立审查

检查了 `docs/audit-20260919/public-cases.json` 与 `backend/verification/audit_public_cases.py`，并直接打开两份 Tekla 原始网页。六个欧拉离散值和两项悬臂结果均与网页表值对应，脚本中 reference 为独立字面量；生产求解器只用于 actual。未用生产输出生成期望值。用 `run()` 复测，8项均在既定容差内，没有重写旧JSON。

1. [Tekla Euler strut](https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderbucklingeulerstrutbuckling)：L=10m，EI=100N·m²，P=1N，两端铰支，1～6单元的离散系数12.000、9.944、9.885、9.875、9.872、9.871。原来源明确一单元误差21.59%，不能把与12.000一致称作连续体欧拉精确解；解析极限为π²≈9.869604。这里支持离散实现的一致性和收敛性。
2. [Tekla single-element cantilever](https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderlinearsimplecantilever)：L=10m，EI=250000N·m²，P=4000N，横向45N；忽略剪切变形、固定初应力几何刚度、单单元。参考端移-167.7mm、根反力矩1.121kN·m。它不验证释放、接触、截面承载力或中国规范组合。

尚缺：来源文件哈希和长期归档、执行环境/源码版本、人工签署；脚本命令行即使 `all_within_registered_tolerance=False` 仍不会主动非零退出，不能只根据进程exit code判定证据通过。旧证据应继续保留 `unreviewed/unverified`。

## 建议追加的可复算外部证据

### A. Dlubal 0042：轴拉引起的刚度增强及大变形边界

[官方算例和PDF下载](https://www.dlubal.com/en/downloads-and-information/examples-and-tutorials/verification-examples/000042)。模型：10m悬臂、80mm实心方截面，E=210000MPa，ν=0.3，端轴拉1.6kN、横向7.65kN，无自重/剪切变形。发布二阶参考：RSTAB端横移3266.163mm；轴向约0.012mm。独立闭式式子为 `F/P*(L-tanh(alpha*L)/alpha)`，`alpha=sqrt(P/EI)`，本次仅用math算得3266.162918922mm；生产20单元实际3266.162917682mm、轴移0.011904762mm。

源PDF把解析表项写3266.136mm，与其闭式复算及RSTAB数值差约0.027mm；应保留这一差异，不反过来调整参考值。原例横移超过3m，是二阶公式与大变形模型的区别演示，不能作为景观结构正常使用的安全通过样本。

已追加 `test_dlubal_0042_axial_tension_cantilever_against_independent_closed_form`，10/20单元直接对照独立math闭式值，并单独核对RSTAB发布数值。测试容差0.0005mm取自三位小数半舍入单位，在新增回归运行前写入；但20单元探索计算先于该容差，故不声称这是完整盲测或事前注册证据。两项通过。

资料版本：PDF标记2015，RFEM 5.05.0030 / RSTAB 8.05.0030；[具体PDF](https://www.dlubal.com/en/webfile/000054/2199523/0042-bending-cantilever-with-axial-force.pdf?hash=f3920580dbc6ef1a7475b7b30ffa5749736a838e)。网页浏览工具读取成功，直接下载用于SHA256固化时HTTP403，因此尚无独立文件哈希；URL中的hash参数不能冒充本地计算的文件哈希。来源长期固定门槛仍未关闭。

### B. Dlubal 002041：基础自重、土重、风力臂与控制组合

[官方孤立基础例题](https://www.dlubal.com/en/support-and-learning/support/knowledge-base/002041)。6×6ft基础厚1.75ft，居中1×1ft柱高2ft，混凝土0.150kip/ft³，覆土1ft、土重0.110kip/ft³；外加恒载60kip、活载25kip；上半柱1ft施加2kip/ft水平风及同向25kip·ft端矩。来源给总恒载73.60kip；组合D+0.75L+0.45W得N=92.35kip、M=14.175kip·ft、qmax=2.959ksf、qmin=2.172ksf。该例可核对基础/柱/覆土不重复计重和风力臂。只比较力学中间量，ASD组合及地基限值不映射为中国规范签署。

### C. 自编公开可重复的脱开边界挑战（参考值来自平衡，不冒充外部软件导出）

先锁定基底净合力，避免混入自重：矩形L=2m、B=1m，N=100kN，单向M=20/33⅓/40kN·m。全接触参考前两项(qmin,qmax)分别(20,80)/(0,100)kPa；M=40时线性qmin=-10kPa，应阻断而非通过。若以后实现单向无拉接触，e=0.4m、压区长a=3(L/2-e)=1.8m，三角形qmax=2N/(B*a)=111.111111kPa，其面积与形心应精确恢复N和M。再加双向反例N=100kN、L=B=2m、Mx=My=20kN·m，两方向分别满足e<B/6却合成qmin=-5kPa，防止只做分轴判断。双向压区实际压力本次未求解。

## 执行证据与未验证范围

- 基线：在原 main/backend 运行 `uv run pytest tests/test_space_frame.py tests/test_space_frame_audit.py tests/test_transfer_audit.py tests/test_design_profiles.py tests/test_foundation.py tests/test_baseplate.py -q`，56项通过。
- 修复前：audit/backend用原main `.venv/Scripts/python.exe -m pytest tests/test_space_frame_audit.py -k 'second_order_member_end_actions or tekla_published_second_order_cantilever' -q --tb=short`，17项全部失败；纯上拔新增回归单独1项失败。
- 修复后：同一解释器运行上述六个完整测试文件，加入Dlubal两项后共75项通过；`verification.audit_public_cases.run()`返回8项全部通过；`git diff --check`无空白错误，仅Windows换行提示。
- audit工作树首次 `uv run pytest` 因新虚拟环境仅安装主依赖、无pytest而失败；后续有效验证均使用显式已安装pytest的解释器，未把安装失败算成测试通过。
- 未完成或未覆盖：整站浏览器与PDF一致性、数据库迁移、Docker运行、真实YJK/PKPM导出与原模型、节点/锚固/地基全规范逐条签署、双向脱开耦合模型、内力沿杆二阶包络、大位移与材料非线性。主 Agent 的其它并行修复须单独审查；这里的75项并不构成全应用验收。
