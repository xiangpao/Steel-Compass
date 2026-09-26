# 最终独立代码审查

日期：2026-09-26。基线：`cc54f0d`；工作树：`Steel-Compass-audit`，分支 `codex/landscape-safety-20260926`。审查对象为当前未提交增量及两份已有审计报告。该审查不构成中国规范签署、工程发布许可或浏览器全面验收，全部工程能力继续 `unverified`。

## 结论

本轮独立复现了一个 Important/P1 状态汇总缺陷，主 Agent 修复后复核通过。所审增量未再发现可复现的 Critical/Important 缺陷。结论只适用于本报告注明的代码和验证范围；其他 Agent 随后追加的修改需要单独复测。

## 独立发现及闭环

`scene_member_checks.py` 新增的二阶能力 guard 在遍历构件时直接设置 `package_status = "incomplete"`，会覆盖较早构件的 `failed`。用同一组输入：C1 零轴力、1000 kN·m 弯矩，C2 二阶轴力 1 kN；构件顺序 `[C1,C2]` 返回包 `incomplete`、明细 `failed/not_calculated`，反转顺序返回 `failed`。路由据此将结构包状态从失败降成 complete；最终工作流仅为 incomplete，已知失败没有优先保留。

主 Agent 在函数末尾改为按全部明细统一聚合，`failed` 优先于 `not_calculated`，空明细为 incomplete；新增双顺序回归。独立读回最终聚合代码并复跑目标测试，两个顺序均保留 failed，闭环完成。本审查未修改生产代码。

## 重点检查结果

- 二阶杆端力：新增恢复使用与整体求解一致的 `K-Kg`，几何刚度与弹性刚度均经过相同刚臂变换；力从 N 转 kN 除以 1000，力矩从 N·mm 转 kN·m 除以 1e6。节点力平衡回归、已登记 Tekla 及 Dlubal 算例测试通过。这只能支持当前初应力、小位移弹性方法，不证明一般沿杆截面内力包络、大位移或材料非线性。
- 二阶传递：adapter 的主要位移、反力、杆端力和力平衡均读取 `stability.second_order`；一阶值保留于新增诊断字段。下游组合及传力函数读取上述主要字段。未发现更新已有不可变快照的代码。
- 未完成构件：缺少某构件组合端力不会再按零需求通过；二阶含轴力构件返回 `not_calculated`、顶层利用率 null，并保留明确标为诊断的 case_checks。路由将构件包纳入工作流状态，trace 保存原因。原有全截面材料映射/厚度限制不能由这些测试证明。
- 基础候选：复核使用推荐器第一迭代，对已选定的同一长宽厚逐组合检查承压、全接触和抗滑；不能把后续增长尺寸当作原候选的证据。正交弯矩反例会清空 recommended 并返回不收敛。路由在保存和响应前调用复核。冲切、配筋、沉降等仍为待完成项，且未升级候选证据等级。
- 方向与支座契约：类型弱轴转换为 90°；单根显式角度优先、不叠加。非标准 restrained_dofs 明确拒绝，保留完整固定和标准铰支契约；弹簧仍被阻断。独立重跑相关测试通过。
- 展示传播：源代码已把未计算构件改为 warning 而非 pass，null 利用率显示“未计算”，并显示原因；构件总览只有完整且无失败/未完成时才为 done。PDF 源码输出“未计算”和 reason。本子审查未执行浏览器交互或 PDF 视觉排版检查。

## 实际运行证据

使用原 main 的已安装测试依赖解释器，在 audit/backend 执行，生产导入来自 audit 工作树：

```powershell
& ../../Steel-Compass/backend/.venv/Scripts/python.exe -m pytest tests/test_landscape_safety.py tests/test_foundation_candidate_multicase.py tests/test_scene_orientation_contract.py tests/test_scene_support_contract.py tests/test_space_frame_audit.py tests/test_transfer_audit.py -q
```

修复前目标回归为 79 项通过，但额外顺序反例复现缺陷。修复后的上述命令为 83 项通过，包含双顺序回归及新增服务性边界测试。

```powershell
& ../../Steel-Compass/backend/.venv/Scripts/python.exe -m pytest tests/test_api.py tests/test_pergola_analysis40.py tests/test_scene_column_base.py tests/test_scene_foundation.py tests/test_scene_steel_connection.py -q
```

20 项通过。API 测试包含分析、快照、PDF 和基础候选路由；PDF 断言只证明接口与 PDF 文件头有效，不证明分页、文本和颜色已视觉验收。出现 Starlette/httpx 弃用提示，不是本次计算失败。

`git diff --check` 通过，仅 Windows 换行提示。未改数据库持久数据、未启动或替换生产服务、未提交、未推送、未部署。

## 追加厚度边界复核

主 Agent 随后对 `_design_strength` 增加 `thickness_mm <= 0 or thickness_mm > 40` 返回 None 的保守限制，没有从相互冲突的厚度表中选择较大值。独立读码并运行 `tests/test_landscape_safety.py` 全文件，25 项通过；单独 `-k thick_plate` 为 2 项通过。额外直接调用复核确认 Q355B 在 40 mm 仍返回 295 MPa、40.001 mm 返回 None；150×150×41 mm SHS 在完整零需求组合下返回包 incomplete、构件 not_calculated 和“材料牌号或厚度超出强度映射范围”原因。该限制避免未映射厚度的通过结论，不构成对 40 mm 及以下既有材料表的独立规范签署。
