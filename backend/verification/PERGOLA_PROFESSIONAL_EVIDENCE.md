# Pergola professional verification evidence

## Release boundary

Geometry `2.3`、Snapshot Schema `4.0` 和标准配置 `CN-2026.7` 已接通亭廊的建模、荷载、分析、构件、连接、柱脚、短柱、基础和报告数据路径。该状态只表示功能链已实现，不表示规范验算已经独立验证。

在下表全部关闭前：

- 发布等级保持 `scheme_estimate`。
- `verification_status` 保持 `unverified`。
- 未完成检查必须返回 `incomplete`、`not_calculated`、`unsupported` 或 `insufficient_data`，不得显示为通过。
- 不得生成 `project_check` 通过结论。

## Verification register

| Gate | Current evidence | Missing evidence | Status |
|---|---|---|---|
| Geometry and topology | Automated tests cover Geometry 2.3 conversion, releases, offsets and model validation | Signed irregular-roof reference models | open |
| Load generation | Automated wind, snow, seismic, roof-zone and balance tests | Clause-by-clause hand calculations and signed Zhejiang catalog review | open |
| Linear and P-Delta analysis | Production solver, PyNite adapter and analytical regression tests | Fixed independent-program and recognized-commercial-software comparison set | open |
| Buckling | Elastic eigenvalue implementation and regression tests | Hand/analytical benchmarks and applicability review | open |
| Steel members | Strength, stability, slenderness, width-thickness and deflection checks implemented | Clause mapping, hand calculations and reviewer sign-off | open |
| Steel connections | Implemented rectangular-tube and H/I connection families | Yield-line/stiffness models, unsupported-family matrix and signed benchmarks | open |
| Column base and anchors | Base plate, anchor tension/shear and weld checks implemented | Deep pull-out, splitting, reinforcement coupling and edge-case benchmarks | open |
| RC pedestal | Biaxial demand and reinforcement data path implemented | Crack control, local reinforcement, seismic joint zone and anchorage review | open |
| Spread foundation | Bearing, eccentricity, sliding, overturning, uplift, shear, punching and reinforcement path implemented | Settlement and stepped/sloped upper-control-section verification | open |
| Immutable report | Snapshot-backed PDF and trace package implemented | Random-object reconciliation against API, drawings and calculations | open |

## Evidence required to close a gate

Each gate requires all of the following:

1. Exact standard number, edition, clause, applicability, symbols and units.
2. A human-readable hand calculation with reviewer, date and conclusion.
3. An independent executable calculation that does not import the production implementation.
4. A fixed comparison model and tolerance against a recognized domestic commercial program where applicable.
5. Regression tests covering pass, fail, incomplete and unsupported outcomes.
6. A recorded approval that changes the gate from `open` to `closed`; automated tests alone cannot close it.

## Current automated baseline

The repository test suite, frontend lint/build, browser regression, database migration and Docker health are execution evidence only. Record their command, date, commit and environment in the release receipt; they do not replace the professional evidence above.
