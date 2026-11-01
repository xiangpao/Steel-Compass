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

## 本轮未生成

- 真实后端浏览器任务流、`live-report.pdf` 与快照哈希：需要启动真实后端和浏览器任务流，本轮未重跑。
- 新前后端镜像已在 Docker 中构建，并用隔离 PostgreSQL（tmpfs）验证：迁移到 `20261101_08`、非 root 运行、健康检查、登录与限流、前端经 `backend` 别名代理；Caddyfile 校验通过。未替换或重建现有 Compose 容器和数据卷。
