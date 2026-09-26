# 二阶包络与释放稳定实现证据

日期：2026-09-26。工作树 `Steel-Compass-audit`，基线 `af8b031`，本次独立执行未提交、未推送、未部署。所有结果保持 `unverified`，本文不是规范签署、商业软件导出或工程验收。

## 完成的算法与传递

- `space_frame.py`：梁柱每个被释放的局部端面自由度均成为独立未知量，和内部细分节点一起保留在 K、Kg、切线求解及屈曲特征问题内。没有把弹性凝聚矩阵用作切线凝聚。两端扭转释放的无荷载刚体自旋只固定一个基准；实际横移机构不删除。线性静力凝聚同步采用伪逆，拒绝释放零空间中无法平衡的荷载。
- `P(x)` 来自一阶轴力与轴向均布荷载，为沿柔性段/刚臂的线性函数。三点Gauss积分精确计算 `integral(P H' H'^T dx)`；刚臂另外包含 `integral(P dx)*theta²` 初应力能量。轴拉提高横向刚度，轴压降低刚度。
- 沿杆恢复采用二阶平衡 `Mz=M0-V0*x-qy*x²/2+integral(P*v' dx)`、对应Y向式及其导数。位移采用Hermite插值；常轴力下增加均布荷载泡函数，零预应力时恢复精确四次位移。变轴力使用Hermite插值和细分。刚臂使用其真实线性刚体位移。弯矩、剪力、弦线相对位移范数的内部极值由多项式导数实根查找，不只看20个采样点。
- 每个子段检查端矩相容误差及弯矩与EI曲率之间的残差。残差大于2%不标记完整。场景入口执行4→8→16→32细分，比较节点位移、首屈曲系数、双轴弯矩及相对挠度，最大相对变化须≤0.5%；未达到时保持 `incomplete`。近零量用1e-4mm/1e-5输出单位作为数值归一化下限。
- 场景 `member_end_forces[*].along_member` 保存方法、细分数、收敛指标、残差、极值、沿杆站点及 `unverified`。构件检查只接受识别的方法和完整收敛元数据；旧快照/缺少该数据仍阻断有轴力的二阶包络。弦线挠度和支承相对侧移共同进入既有变形检查。
- 同时修正轴力符号判断：局部杆端作用的start N>0、end N<0均对应压缩；不能因为两个端力异号就把拉杆误用压杆折减。
- adapter版本 `2.1`，构件检查版本 `2026.3-unverified`。不重写任何历史快照。

## 独立参考与来源

1. [Tekla 2026 Euler strut](https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderbucklingeulerstrutbuckling)：官方离散基准1～6单元系数12.000、9.944、9.885、9.875、9.872、9.871；网页明确单单元与连续体误差21.59%。本次复查官方来源，保留原有独立字面参考与0.0006绝对容差。连续体目标为π²而不是12。
2. [Tekla 2026单单元悬臂](https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderlinearsimplecantilever)：既有位移-167.7mm、根矩1.121kN·m对照仍通过。保持默认 `member_subdivisions=1` 的离散定义，场景入口另行使用收敛版本，不修改旧参考值适应新输出。
3. [Dlubal 0042官方PDF](https://www.dlubal.com/cs/webfile/000054/2199523/0042-bending-cantilever-with-axial-force.pdf?hash=f3920580dbc6ef1a7475b7b30ffa5749736a838e)：本次联网读取，2015、RSTAB8.05.0030/RFEM5.05.0030。既有独立轴拉闭式 `F/P*(L-tanh(alpha L)/alpha)` 与RSTAB3266.163mm的10/20单元回归仍通过。其大位移尺度不作为景观结构正常使用的安全样本。
4. 新铰支压杆均布横载参考直接解 `EI*v''''+P*v''=q`，两端位移与弯矩为零：`Mmid=q/k²*(sec(kL/2)-1)`、`vmid=(Mmid-qL²/8)/P`，`k=sqrt(P/EI)`。预先写入双轴、P/Pcr=0.2及0.8、12单元的3e-4相对容差；没有用生产输出生成期望值。
5. 刚臂/轴向均布载荷新增独立ODE射击解：状态(v,theta,M,Veff)，`v'=theta`、柔性区`theta'=-M/EI`/刚区`theta'=0`、`M'=-Veff+P(x)*theta`、`Veff'=q`。SciPy solve_ivp rtol1e-11/atol1e-10分区积分与端矩边界求根，不调用生产刚度、形函数或沿杆恢复。8组轴拉/压×刚臂有/无×轴向分布载有/无，端移/根矩相对1e-4，每个返回站点位移绝对2e-4mm、弯矩绝对2e-4kNm。该组测试在实现后追加，因此不宣称盲测或事前登记。

官方文件的长期归档/文件哈希由本次主任务的统一证据登记负责；本文未把URL内的hash参数冒充文件SHA256。

## 收敛示例

L=3000mm、E=206000MPa、I=1e8mm4、q=1N/mm、P=0.8Pcr、两端释放。独立连续体参考：屈曲系数1.25，跨中弯矩5.7652882976703115kNm，挠度0.25676186437225734mm。

| 每杆细分 | 屈曲系数 | 弯矩相对误差 | 挠度相对误差 | EI曲率相对残差 |
|---:|---:|---:|---:|---:|
| 1 | 1.519817754635 | 39.7381% | 49.3722% | 41.5285% |
| 2 | 1.259402909222 | 2.39223% | 2.97221% | 12.2008% |
| 4 | 1.250640175678 | 0.165404% | 0.205505% | 3.83316% |
| 8 | 1.250040957607 | 0.0105570% | 0.0131165% | 1.01043% |
| 16 | 1.250002575265 | 0.000663087% | 0.000823847% | 0.255914% |
| 32 | 1.250000161214 | 0.0000414968% | 0.0000515566% | 0.0641860% |

## 执行与验收证据

环境：Windows、Python3.14.3、NumPy2.5.1、SciPy1.18.0；解释器为原main `backend/.venv/Scripts/python.exe`，运行目录为audit/backend。主机提交内存偏紧时默认BLAS线程池导致两次pytest无输出exit1；单次进程设置 `OPENBLAS_NUM_THREADS=1`、`OMP_NUM_THREADS=1` 后恢复。未写持久环境变量。

- 初始新增8项均失败：API缺少细分参数/along_member。实现后通过。
- 双端扭转释放测试先失败（明确奇异矩阵），修正无荷载自旋基准后通过。
- mode_count=0测试先失败（没有拒绝），新增1～20模态数验证后通过，防止空模态集合绕开失稳门槛。
- 拉压符号测试先失败，期望拉杆利用率0.5692167577而旧实现给0.7912，修复后通过。
- 桁架竖向杆局部轴力测试先失败（输出global X的0而非局部1000N），修正一阶/二阶结果局部坐标输出，并显式保留桁架稳定未覆盖状态后通过。
- 最后完整专项：`python -m pytest tests/test_space_frame_completion.py tests/test_space_frame_audit.py tests/test_space_frame.py tests/test_scene_space_frame.py tests/test_landscape_safety.py -q --tb=short`，88项通过，exit0。
- `verification.audit_public_cases.run()`：8项参考全部passed，证据仍为public_reference/unreviewed/unverified。未仅凭脚本exit0判断对照通过。
- `git diff --check`对应修改文件通过，只有Windows换行提示。

## 明确边界

- 本次覆盖直线等截面Euler-Bernoulli梁柱、六自由度释放、轴拉/压、双轴弯曲、刚臂、均布荷载、线性P(x)及弹性初应力屈曲。0.99Pcr稳定与1.01Pcr拒绝均有测试；实际机构/释放零空间中的非平衡荷载拒绝。
- 未实现材料非线性、剪切变形、剪切中心/翘曲扭转、局部板件屈曲、更新几何、大转角、随动力或施工阶段。桁架仅保留轴向弹性刚度及正确局部轴力；其几何刚度/自身屈曲明确不覆盖，场景stability_scope与along_member标记incomplete，不能用梁柱验证宣称桁架稳定已完成。
- 子段曲率残差与两级细分差是数值诊断，不是对所有结构误差的数学上界。达到32细分仍不收敛保留incomplete；接近奇异或特征求解失败不放宽容差、不删除模式来通过。
- PyNite独立对照继续原路径；细分后的连续体近似不一定与单单元P-Delta实现一致，差异仍通过现有工程门槛暴露，不更改对照容差。
- 未做整站浏览器、PDF、Docker、生产数据库或具名专业审核。本次自动化与解析/ODE证据只证明所列离散和力学行为，不升级为independently_verified。

## 独立复审后的二次修复

### 刚臂与横向平移释放的位移两侧

独立审查发现：末端刚臂0.4m、柔性端面Y向平移释放、末端Y/Z约束、轴压1000kN及横向均布载-2kN/m时，恢复把滑移后的柔性侧坐标误当刚臂尖端坐标，端矩残差约0.762kNm。原有残差门槛正确阻断了轴压算例，但零轴力时该错误也会导致刚臂位移错误而未触发弯矩残差。

修复只改变恢复阶段：刚臂尖端始终使用 `rigid_arm_transform @ joint_u`；柔性侧保留独立释放自由度，两者在同一物理位置可以有不同位移。沿杆站点保留 `rigid_arm` 区分两侧，并新增 `released_face_displacement_jumps`（柔性侧减刚臂侧、局部平移mm/转角rad）。未改变已经正确的刚度组装或降低残差容差。

新增独立边值参考：柔性跨度l=2.6m、刚臂b=0.4m；`Veff(l)=0`，端部无外加力矩给出 `M(l)+theta(l)*integral_arm(P dx)-q*b²/2=0`。常轴力用5状态常系数ODE的矩阵指数精确传递，变轴力用独立基本解矩阵积分；不调用生产有限元矩阵/恢复函数。24组覆盖Y/Z、轴压/零轴/轴拉、杆件方向正反、轴向均布载0/-2kN/m。根矩和转角相对1e-5，每个站点位移绝对1e-5mm、弯矩绝对1e-5kNm，界面位移跳跃同容差。最初12组（无轴向分布载）修复前全部失败，修复后通过；另12组变轴力为后加扩展。独立审查原复现已改为要求complete、端矩残差<1e-3Nmm、界面力矩连续且位移跳跃非零。

### 纯受拉组合与特征迭代错误分类

全量测试另外复现了两个既有亭廊整包测试：上拔风组合的Kg为受拉主导负半定，ARPACK在高重数零特征空间迭代3601次、0/5模态收敛，旧错误映射将它称为结构失稳。两个原测试在本地补丁前再次确认失败。

现在无压缩初应力时按能量积分判断无正屈曲系数，不对零特征子空间作无意义迭代。初始轴力的符号判断使用整模型最大轴力幅值的1e-12作为浮点舍入尺度（上拔风梁端数值噪声约6e-11N），不使用固定单位的荷载阈值；受拉Kg仍完整进入切线刚度求解。真正的 `ArpackNoConvergence` 单独返回 `buckling_eigen_solver_not_converged`，明确是无法判定而非证明结构失稳，不放宽迭代容差或制造通过结论。

新增384自由度纯拉悬臂闭式位移与空正屈曲谱对照；另注入实际ARPACK迭代耗尽异常，证明错误代码不同于结构失稳（此项修复前失败）。既有两项亭廊整包回归在补丁后通过。依然不将无正屈曲模态解释为材料强度、局部屈曲或大变形安全。

二次修复最终fresh复测：设置进程级OPENBLAS/OMP线程数1，执行 `python -m pytest -o addopts='' tests/test_space_frame_completion.py tests/test_space_frame_audit.py tests/test_space_frame.py tests/test_scene_space_frame.py tests/test_landscape_safety.py tests/test_space_frame_independent_review.py tests/test_pergola_analysis40.py -q --tb=short`，**124 passed in 64.27s**，exit0。此次范围只改space_frame.py、求解器专项/独立复审测试及本证据；未覆盖root并行修改的构件状态门槛或工作流聚合文件。

## 真实默认亭廊性能优化（不改变数值验收）

只读打开隔离DB `completion-live-20260926.db`（SQLite URI `mode=ro`），采用项目2/场景1当前保存几何与屋面条件：18节点、21杆、14独立工况和132组合。未修改数据库。

优化前对真实自重工况的cProfile：总1.203s，`_member_envelope`累计1.071s（约89%）；432/936自由度两次eigsh分别0.0054s/0.0055s。热点是NumPy Polynomial运算产生127086次as_series及32442次对象构造，不是稀疏屈曲求解。去掉profiler后同一自重分析0.4814167s，完整数值保存在 `solver-performance-baseline.json`；它是优化前后的内部差分基线，**不是独立外部参考或专业证据**。

最小优化：Hermite＋均布载荷泡函数、`integral(P*v')`、弦线位移、EI曲率残差全部用同一个低阶多项式的直接系数表示；Horner同时计算所有极值站点。仍通过相同多项式导数实根求极值，未删除工况、组合、站点类别或必需检查，未改变0.5%细分收敛、2%曲率残差及端矩门槛。模型刚度、特征方程和求解路径不变。

同一自重模型优化后3次0.2002703/0.1751321/0.1728847s；所有杆件双轴弯矩/剪力/弦线挠度的最大绝对差6.9389e-18，状态与细分数完全一致。六个求解与独立复审测试文件fresh结果：**122 passed in 2.99s**。

完整默认模型实际运行（不是从单工况估算）：**14工况＋132组合全部完成，43.9509742s**；一阶求解146次共0.44847s，收敛二阶分析146次共39.44554s，独立PyNite比较292次共3.60734s。`balanced=true`，构件检查status=complete，verification_status仍unverified。机器为原记录Windows/Python3.14.3，进程级OPENBLAS/OMP均为1。测时保存在 `solver-performance-after.json`。

此测时覆盖完整pergola mechanics package（包括所有组合与双路径PyNite），不包含HTTP代理、快照写入、基础候选或PDF；真实浏览器端到端由root在同一冻结代码上另行测量。完整分析仍可能超过原30秒代理预算，性能结论没有把超时冒充通过。
