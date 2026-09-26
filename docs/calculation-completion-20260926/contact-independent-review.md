# 接触、基础和柱脚独立代码审查

2026-09-26；审查对象：`Steel-Compass-audit` 的 `codex/complete-calculation-gaps-20260926` 工作树相对 `af8b031` 的 contact/foundation/baseplate/scene adapters/design profiles 增量。独立审查 Agent 不修改生产代码；仅新增本报告和 `backend/tests/test_contact_independent_review.py`。所有结论保持 `unverified`，不是注册工程师签署、国内规范条文验收或第三方软件认证。

## 首轮结论

发现 4 项 Important，其中 3 项可导致错误力学状态/需求/构造通过，1 项丢失控制组合追溯。已逐项实时交主 Agent 修复。首轮 9 项独立测试：**4 failed, 5 passed，exit 1**。以下行号是首次审查时位置，生产修复后可能移动。

|编号|级别|位置|独立复现与影响|
|---|---|---|---|
|C1|Important / P1|contact.py:142|收敛仅看残差，未验证活跃支承正定/秩。L=B=2m，N=-100kN，Mx=My=0，kc=250；四根 k=250kN/m 锚栓位于 x=(-.6,-.2,.2,.6)m、y=0。返回 solved、每栓25kN、接触面积0，但绕 x 转动完全无恢复刚度。恰好初始残差为零绕过线性求解的奇异矩阵检查。需要在宣告求解成功前拒绝活跃支承机构。|
|C2|Important / P2|foundation.py:852|顶筋 check 先记录真实控制组合，随后通用循环用不含顶筋名称的字典 `.get` 清成 None。2×1×.2m 基础、上游 N=90/My=40，顶筋记录含 review-ULS，而最终 X向顶筋 check 控制组合为空。需保留已选顶筋组合。|
|C3|Important / P1|baseplate.py:122,221,427|新逐栓坐标用于力学，旧 anchor_spacing_mm 仍独立用于构造和劈裂容量。4栓 x,y=±.001m，最近实际间距2mm，输入纯压100kN，未提供旧间距时默认260mm；最小间距 check demand60/capacity260 passed，整体 passed/ready。需从实际坐标派生间距，或明确拒绝与声明几何不一致，不能使用更有利的旧默认容量。边距同样应核清相对于板/混凝土的真实几何来源。|
|C4|Important / P1|foundation.py:652|按 combination_name 回找自重系数组合；名称可缺省/重名，不能用作唯一键。2×1×.2m 基础，A:ULS N10/leading permanent、B:ULS N90/leading uplift，独立 ID A/B、名称均 None。B 单算 X剪31.815kN、冲切81.168795kN；A+B降到30.401和77.561293，因 B 错扣 A 的1.3自重而不是0.9。应把原组合对象/系数直接随解携带或按唯一ID关联。|

## 独立正向检查

测试未复用生产裁切/积分内部函数构造参考。新造的测试包括：

- 3×.8m 非方形基础，制造压力 `max(30+70x/1.5-20y/.4,0)`，使用360×360 Gauss张量积分独立得到 N/Mx/My，再送入求解器。恢复系数及120kPa峰值，容差0.002kPa，三分量平衡容差1e-7。
- 四根不同刚度、非对称坐标锚栓，制造全上拔位移 `w=-.1+.02x-.03y`；从逐栓位移独立算拉力及合力矩，生产解逐栓拉力和平衡容差1e-7，接触面积0。
- 非对称锚栓组剪力，平移坐标原点并同步转换扭矩后，每根二维剪力保持不变；总扭矩平衡通过。
- 300×120mm 连续矩形焊缝，四边分别8点Gauss线积分生成长度及 Ix/Iy/J；N、Vx、Vy、Mx、My、T 同时作用时，与独立角点向量峰值一致，relative tolerance 1e-12。
- .6m³混凝土体积与2×1×.2m底板不一致的非均匀自重输入，确认返回 incomplete/capability_unavailable、unresolved_nonuniform_weight 和 unverified；未冒充 ready 结构通过。

此外静态检查：净压区积分真实裁切多边形，不是截掉线性负压力后直接使用；二阶三角求积对所用多项式精确。锚栓拉力按位移协调，V/T剪力在群形心分配后回到原点平衡。连续矩形焊缝用角点求峰值符合仿射向量范数沿每条直线边的凸性。基础按外伸两侧积分，并检查柱边和零剪力截面的正负弯矩。上述仅是模型数学和有限用例证据，不能证明适用于柔性底板、非均匀土刚度、塑性或沉降。

## 一手来源与适用边界

本轮重新在线读取以下原始来源；未把实现者报告作为外部认证：

1. [SCIA Engineer 22 — Support nonlinearity/Basic soil spring](https://help.scia.net/22.0/en/analysis/nonlinear_analysis/support_nonlinearity/support_non-linearity-basic_soil_spring.htm)：明确弹性压缩单向/拉力单向支承属于非线性分析。支持本轮模型类别；不提供这套求解器精度或中国规范容量认证。
2. [Dlubal — Modeling Base Plate Considering Plate Bending and Real Dowel Force Distribution](https://www.dlubal.com/en/support-and-learning/support/knowledge-base/001404)：原文区分刚性板、真实板刚度、单向支承；指出板柔性与局部支承会显著改变锚栓力。由此本项目保留柔性板/撬力 pending 是必要边界；刚性兼容解不能直接证明实际锚固通过。
3. [AISC Engineering Journal — Eccentrically Loaded Weld Groups; AISC Design Tables, Raymond H. R. Tide, 1980](https://ej.aisc.org/index.php/engj/article/view/354)：记录弹性群组按相对形心距离分配、极惯性矩方法及非弹性限制。本轮 Ix/Iy/J 具体公式另由独立线积分核验，并未套用美标容量替代中国规范。

## 运行记录

解释器：`C:/Users/86137/Desktop/IP-Builder/03_Projects/Steel-Compass/backend/.venv/Scripts/python.exe`；cwd：audit/backend。临时进程环境 `OPENBLAS_NUM_THREADS=1`、`OMP_NUM_THREADS=1`。未安装依赖、改服务或部署。

```
python -m pytest tests/test_contact_independent_review.py -o addopts= -q
```

首次7项：3 failed/4 passed；扩充组合错配与非均匀自重后9项：4 failed/5 passed。测试失败均为真实断言失败，不是导入/环境异常。待主Agent修复后需运行同一文件并记录新的退出码；本报告首轮缺陷记录应保留。

## 主 Agent 修复后的独立复核

主 Agent 完成四项生产修复后，本审查 Agent 重新读取实际源码并执行原失败测试，未按其口头结果直接验收：

- C1：收敛退出前检查活跃切线对称特征值，非正或最小/最大特征值比不大于1e-12时明确拒绝。原共线纯拔机构被拒绝；稳定异刚度全拔制造解继续通过。
- C2：通用组合回填保留 check 已有控制组合；原顶筋 review-ULS 通过。
- C3：实际坐标在混凝土承载力、劈裂及构造检查之前导出最近间距；原2mm间距不再被260mm默认值覆盖。边距采用声明混凝土边距和实际底板边距的较小值。此为暂定保守边界，不等于已经建立真实基础/短柱边界几何模型，后续规范映射仍须保留 unverified。
- C4：contact_cases 直接携带所属原组合对象，扣重从本组合 leading_action 取系数，彻底移除按名称回找。原缺名称组合的联合包络不再低于单独计算。

复核命令：

```
python -m pytest tests/test_contact_independent_review.py tests/test_contact_completion.py tests/test_contact_profile_contract.py tests/test_baseplate.py tests/test_foundation.py tests/test_scene_foundation.py tests/test_scene_column_base.py -o addopts= -q
```

独立 fresh 结果：**60 passed in 0.69s，exit 0**；其中本审查9项均通过。相关生产文件及审查测试 `git diff --check` 无错误（仅Windows换行提示）。四项首轮发现均在此次限定范围内关闭；没有获得专业签署、真实工程软件对照、现场或生产验收证据。

此次复核源码 SHA256：

|文件|SHA256|
|---|---|
|contact.py|5ACF11821D3B859F8398E28862AA0F5B055CECAA2AD51ED9C9A299EE0E50BFB6|
|baseplate.py|B82FEA1B158F1BAA1721A3C7777B381FBFDD502FDCED7D31E07468C9BC1E436A|
|foundation.py|8E6ADDB69C90A764FE7914891EEB203AE50AF09AA66FBFAEF63C058C2CA3F344|
|test_contact_independent_review.py|55C7D0F4E63A4C935CE9D085525814E503A1F43F2941721476C6F105BD6F20EE|
