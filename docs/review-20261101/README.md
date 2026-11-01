# 审查修复后的证据快照 — 2026-11-01

分支 `fix/review-safety-and-payload-20261101`。本目录是代码审查修复后，按仓库现有脚本重新生成的本地证据，不是规范签署、真实商业软件同模型对照或工程验收。全部模块仍为 `unverified`。2026-09-26 目录中的历史数值保持原样，作为当时快照。

## 文件

| 文件 | 生成命令（cwd 为 backend，`OPENBLAS_NUM_THREADS=1`、`OMP_NUM_THREADS=1`） |
|---|---|
| `scene-variant-matrix.json` | `tests/test_scene_typed_adapters.py` 中 `__main__` 段的同一逻辑，输出改写到本目录 |
| `tekla-public-cases.json` | `python -m verification.audit_public_cases --output ../docs/review-20261101/tekla-public-cases.json` |
| `analytical-sweep.json` | `python -m verification.landscape_safety_cases ../docs/review-20261101/analytical-sweep.json` |
| `backend-tests.txt` | `python -m pytest -o addopts= -q --cov=app --cov-report=term:skip-covered tests` |

## 与 2026-09-26 的差异

- 40 变体工作流状态不变：25 个 `ready`（13 `screening_passed`、12 `screening_failed`），15 个 `capability_unavailable`。
- 计算节点：110 passed / 48 incomplete / 13 failed → 111 passed / 47 incomplete / 13 failed。变化集中在多跨框架的基础节点，原因是支座反力改为按支座位置取用（旧代码按集合顺序取，左右/中间基础可能拿到别的柱的反力）：
  - `pergola-pavilion/multi-bay`：`base_middle`、`rear_base_middle` incomplete → passed；`base_right`、`rear_base_right` passed → incomplete。
  - `entrance-frame/multi-span`：`foundation_middle` incomplete → passed。
- 节点 `verification_status`：旧矩阵有 29 个荷载节点硬编码为 `independently_verified`，现在 222 个节点全部为 `unverified`。
- Tekla 公开参考 8/8 仍在预登记容差内；景观解析敏感性扫描结果与 2026-09-26 逐字节相同。
- 后端测试 890 passed，语句覆盖率 92%。

## 真实后端浏览器任务流

`tests/live-audit.spec.ts` 1 项通过（51.9 s）：登录、新建项目、保存、完整分析、快照与 PDF、修改条件后结果失效、刷新恢复、390px 无横向溢出。后端为本机 uvicorn（临时 SQLite，`STEEL_COMPASS_ANALYSIS_WORKERS=4`），前端为生产构建，经代理访问该后端；不是 PostgreSQL 全栈验收。

- 摘要与哈希见 `live-evidence-summary.json`：快照 schema 4.0 / CN-2026.7，结构、构件、屈曲 complete，连接、基础与总工作流 incomplete，全部 unverified；PDF 200 页。
- 截图：[桌面结果](ui/live-result-desktop.png)、[390px 项目条件](ui/live-mobile.png)。原始快照 JSON（约 97 MB）和 PDF 留在被 Git 忽略的 `frontend/output/playwright/`。
- 该流程首次运行暴露了一个本轮引入的前端回归：保存模型会把规范化后的几何写回状态，旧的“输入代次”判定因此把每次分析都当作过期而丢弃，PDF 链接不出现。已改为按输入内容指纹比较，修复后流程通过。
- 快照体积：分析部分约 49 MB，其中 132 个组合的逐杆沿杆包络（`member_end_forces.along_member`）约 40 MB，是后续压缩或按需加载的主要对象。

## 容器验证

- 新前后端镜像已在 Docker 中构建，并用隔离 PostgreSQL（tmpfs）验证：迁移到 `20261101_08`、非 root 运行、健康检查、登录与限流、前端经 `backend` 别名代理；Caddyfile 校验通过。未替换或重建现有 Compose 容器和数据卷。
