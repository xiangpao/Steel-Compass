# 计算模块验证证据

这里保存用于改变 `verification_status` 的不可变证据。一个模块只有同时满足以下条件，才允许从 `unverified` 改为 `independently_verified`：

1. 明确、有限的适用范围；
2. 规范版本、条款和公式适用条件映射；
3. 至少一组人工手算记录；
4. 不调用生产计算函数的独立复算脚本；
5. 边界、非法输入及 `0.99/1.01` 结论翻转测试；
6. 证据清单经过人工复核并记录日期。

公开软件算例只能用于相同力学模型的交叉核对，不能代替中国规范承载力映射。

当前状态：钢梁以及 3.1 场景筛查器的独立力学复算脚本已经加入；规范条款逐项人工签核和认可软件对照尚未完成，因此所有新增模块仍保持 `unverified`，专业模式仍返回 `incomplete`。

`milestone_references.py` 只包含直线木铺板、单柱悬臂、墙片、RC 墙和悬臂挡土墙的封闭解，用于快算回归，不得直接作为正式设计依据。

## 亭廊商业软件对照门禁

`PERGOLA_COMMERCIAL_COMPARISON_TEMPLATE.json` 是 YJK/PKPM 实际导出结果的录入模板；必须填写软件版本、模型编号、导出日期、复核人和源文件。`pergola_commercial_comparison.compare_file()` 只负责逐指标误差计算，不会自动生成或冒充外部软件结果。只有真实导出文件进入证据库并经具名复核后，`PERGOLA_PROFESSIONAL_EVIDENCE.md` 中的商业软件对照门禁才允许关闭。
