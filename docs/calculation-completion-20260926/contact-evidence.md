# 矩形脱开接触、柱脚兼容与基础积分证据

日期：2026-09-26。基线：`af8b031`；工作树 `Steel-Compass-audit`，分支 `codex/complete-calculation-gaps-20260926`。以下是新力学模型的本地实现与数值证据，不是规范签署或外部工程软件认证。所有结果保持 `unverified`，没有推送、部署或改动原 main 源码。

## 已实现范围

`backend/app/core/contact.py` 新增矩形刚性板与均匀压缩单向线性支承求解。以板中心为原点，x 沿 length、y 沿 width；N 受压为正，Mx=∫yq、My=∫xq。使用 kN、m、kPa。压力为 `q=max(a+b*2x/L+c*2y/B,0)`，先裁切真实压区多边形，再以三角形二阶精确积分规则计算合力、力矩及切线刚度，使用带能量线搜索的三自由度 Newton 求解。不是把一次线性解的负值直接截零。

无锚栓基础只需 L/B/N/Mx/My；均匀支承刚度的绝对量从力平衡中消去，并未虚构土刚度或沉降。若 N≤0 或合力落在矩形支持域边界/外部，拒绝有限压缩平衡；不返回零压力通过。迭代上限100，最大缩放残差阈值 `1e-10*max(1,|N|,|2My/L|,|2Mx/B|)` kN。狭小压区病态或未收敛也明确失败。

柱脚可以同时求解压区与拉力锚栓：显式输入 `contact_stiffness_kn_m3`、`contact_model_source` 以及 `anchor_springs=[{x_m,y_m,stiffness_kn_m}]`。令 w=q_plane/kc、Ti=ki*max(-wi,0)，解 ∫q−ΣTi=N 及两个力矩平衡。模型限定为无预拉、无初始间隙、均匀接触支承、刚性平面；输出每栓拉力、压区、参数来源与平衡残差。没有隐藏1.25撬力放大系数。缺参数的上拔/脱开组合不生成伪造的锚栓拉力或底板通过行。

存在逐根坐标时，锚栓剪力采用刚性板、等剪切刚度、所有锚栓同时受剪、无孔隙滑移的弹性分配。先把扭矩换算到锚栓群形心，再计算 V/n+T*r/J，保留逐栓二维剪力，并与同一根锚栓的拉力计算组合；不从轴向弹簧刚度推测剪切刚度。缺坐标且T≠0继续明确不支持。

声明 `continuous_perimeter_weld=True` 时，以现有矩形柱截面和等焊喉输入计算连续周边弹性线焊缝组：轴拉、双向弯矩、双向剪力、扭矩，按角点矢量合力确定最大线力；不采用焊缝方向强度提升系数。现有材料承载值仍属于未独立验证的方案映射。未声明连续焊缝时，上拔焊缝不计算；旧压剪快算路径保留兼容。

基础逐个真实 SLS/ULS 组合求解接触，地基压力、脱开面积、双侧剪切、冲切、底筋分别选自己的控制组合。等厚且覆土均匀时，按原组合自重系数从实际土反力中扣除均布基础/覆土有效重量，积分净荷载。沿两侧外伸区寻找柱边与零剪力截面的正、负弯矩峰值，明确输出顶筋需求。`top_bar_dia_x_mm`、`top_bar_spacing_x_mm`、y向同名参数齐全后验算顶筋；场景适配从可选 `top_x/top_y` 配筋字符串读取。缺顶筋而有反向弯矩返回 incomplete，不以“保守”掩盖漏项。

阶形/锥形上部截面已改用真实压区积分，避免用峰值压力减冲切内反力。但非均匀自重/覆土分布尚未完整建模，所以结构结果仍为 incomplete，其总土反力积分只作为诊断，不能代替净荷载设计。

## 独立参考与容差

新增 `tests/test_contact_completion.py` 共23项：

- 单向独立手算：L=2m、B=1m、N=100kN、My=40kN·m；a=3(1−0.4)=1.8m，qmax=2N/(Ba)=111.111111111kPa。峰值容差1e-6kPa，面积1e-8m²，三分量平衡绝对容差1e-7。
- 双向/四种反转及单轴强偏心、核心条件0.99/1.01、纯上拔/零压力纯矩/支持域边界之外。
- 双向三角压区独立闭式：L=B=2m，q=600(x+y−1)只在角部三角形为正；面积0.5m²，合力100kN，形心(0.75,0.75)m，Mx=My=75kN·m。
- 独立三角压区加四个点弹簧制造解：kc=1000kN/m³、每栓k=10kN/m、坐标(±0.8,±0.8)m；固定压力平面[-600,600,600]kPa，逐栓拉力[15.6,6,6,0]kN，由该独立几何闭式先给出目标合力/矩，再比较生产解。
- 基础压区另用300×300 Gauss-Legendre张量求积校验3组双向合力/矩，绝对容差0.003（kN或kN·m）；它不调用生产裁切积分函数。
- 柱脚纯拔N=−100kN、4个同刚度对称锚栓应为每栓25kN，压力为零；同时验证兼容式和有限残差。
- 基础集成参考保留10kN基础自重：SLS N=100、ULS N=103。独立三角积分校验扣6.5kPa均布自重后的剪切和冲切，校验每项组合包络；独立二次方程求零剪力截面，校验脱开区自重造成的反向弯矩及缺顶筋阻断。
- 非对称锚栓群剪力/扭矩平衡；200×200mm正方形连续焊缝参考：80kN轴拉=100N/mm、4kN·m单向矩=75N/mm、4kN·m扭矩=53.033008589N/mm。

最先写入单向脱开用例，在没有contact模块的基线上运行，明确失败 `compression-only contact solver missing`；实现后首批14项通过。额外积分、场景和剪力/焊缝验证分批追加，后4项属于实现后独立闭式验证，不称为全套事前盲测。历史底板golden使用N/A和M/z算法，超出全接触范围，现改为明确缺兼容输入的阻断测试；未把旧公式当新求解器参考。

## 官方来源与归档

1. [SCIA Engineer 22 支承非线性说明](https://help.scia.net/22.0/en/analysis/nonlinear_analysis/support_nonlinearity/support_non-linearity-basic_soil_spring.htm)：支持压缩单向/拉力单向弹簧及非线性分析边界。仅用于模型类别和适用范围，不提供本项目精度认证。归档 `sources/scia22-support-nonlinearity.html`，SHA256 `10c67a634ee2544b67050c00311b822e3eda12ffe3c40816b8aa7ae5f32ac043`。
2. [Tekla Structural Designer 2025 柱脚说明](https://support.tekla.com/doc/tekla-structural-designer/2025/ref_baseplatesaisc360)：本轮页面显示2026-04-01修改，分别列上拔底板弯曲、锚固和焊缝受拉检查。仅用于失效模式边界，不采用其AISC/ACI承载力代替中国规范。归档 `sources/tekla2025-baseplates.html`，SHA256 `c6f363232361adba8beb3bef2f0d5d427314f45529d32c66bbfd4df8143eda8c`。

两份HTML均为本轮实际下载后计算SHA256，不把URL中的标识当本地文件哈希。数值参考来自上列公开记录的平衡/几何闭式和独立张量求积，不冒充Tekla/SCIA的实际模型导出。

## 当前执行记录

解释器：原main的 `backend/.venv/Scripts/python.exe`；cwd为audit/backend，导入audit代码；Python3.14.3、NumPy2.5.1、pytest8.4.2。未运行uv、未安装依赖。

最终定向命令：

```
python -m pytest tests/test_contact_completion.py tests/test_foundation.py tests/test_baseplate.py tests/test_scene_foundation.py tests/test_scene_column_base.py tests/test_transfer_audit.py tests/test_steel_timber_verification.py tests/test_contact_profile_contract.py -o addopts= -q
```

本轮结果：91 passed，进程exit0。`-o addopts=`明确覆盖仓库附加输出/门槛参数；不把仅有点号的中间输出当作完成。专项新用例单独结果23 passed，exit0。本次改动文件 `git diff --check` 无错误。测试过程中并行space_frame写入曾产生暂时ImportError、基础警告插入位置曾产生NameError，最终上述运行均已消除；不把中间失败隐去或当通过。

当时源码SHA256：

- contact.py：`ba3f2828fab44a430e632d5a571a419560a641d06969757ae11a18a2918c7c6c`
- foundation.py：`bbb12118ea26e8d85b27b784fab442745caa9aa53f1e9988a2afba6a47b6f980`
- baseplate.py：`9c5c406e468224cb58ea36a646fef4e0023ecdab3c6feb78b4e0dbc2b362d537`
- test_contact_completion.py：`14baab6d2207b0be115ef4c301b1d5bb9cf06e46a65c3c52c33bf46e8b140841`

## 必须保留的未完成项

- 有锚栓拉力时，刚性平面兼容不证明实际底板刚性。柔性底板局部弯曲/屈服线、撬力、垫圈/垫板局部承压尚未闭合，仍incomplete。至少需明确锚栓相对柱边的受拉条带/屈服线有效宽度、垫圈/垫板接触尺寸及厚度、局部边界/加劲肋和可能撬力接触点；不能用隐含撬力系数填补。
- 弹簧参数须来自实际锚栓有效拉伸长度、材料刚度和灌浆/混凝土支承依据；本实现不提供假定刚度。预拉、孔隙、非均匀剪刚度、滑移、塑性、接触大转动不支持。
- 地基非均匀刚度、土塑性、沉降与接触共同迭代、非等厚自重分布及完整负弯矩构造未完成。
- 全部承载力规范映射、认可软件模型/导出、独立审计签署、真实工程验收仍未完成。本文件不是应用全面验收，也不是本轮主Agent最终独立复核报告。
