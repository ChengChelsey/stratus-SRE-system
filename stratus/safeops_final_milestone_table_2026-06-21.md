# SafeOps-Agent / STRATUS-AIOps 最终阶段总表

## 1. 当前完整路线

```text
offline dataset
→ QLoRA training
→ offline eval
→ A800 online Planner Server
→ ARM shadow replay on 9 live episodes
→ dry-run gate
→ sandbox server-side dry-run pass
→ sandbox controlled execution with rollback
→ trajectory/reward event export
→ multi-fault LinUCB hard-mode replay
```

## 2. 阶段成果总表

| 阶段 | 已完成内容 | 关键结果 | 证据/产物 |
|---|---|---:|---|
| Live STRATUS/AIOpsLab 轨迹 | 覆盖 targetPort、scale=0、nodeSelector 三类故障族 | targetPort 3-run success；scale 3 success + 1 infra failure；assign 3 success | `multifault_live_probe_2026-06-21.tar.gz` |
| Multi-fault 数据集 | 构造 SFT / Tool-Calling / preference pairs | 570 / 570 / 570；train/val/test=462/53/55 | `planner/data_multifault/` |
| QLoRA Planner | Qwen2.5-7B-Instruct 4-bit QLoRA | Base schema 0%；QLoRA schema/field acc 100%；unsafe 0 | `qwen25_7b_multifault_qlora_result_2026-06-21_163342.tar.gz` |
| A800 Planner Server | FastAPI 服务化 QLoRA Planner | `/health` 与 `/plan` OK；ARM 通过 SSH tunnel 调用成功 | `planner_server_multifault_deploy_2026-06-21_171651.tar.gz` |
| Shadow replay | 9 条 live-success episode 旁路推理 | server/schema/local schema/static safety/agreement 均 9/9；executed=0 | `shadow_mode_3families_9episodes_2026-06-21_101021.tar.gz` |
| Dry-run gate | shadow plan 转 `kubectl patch --dry-run=server` | historical 9 条 static_safe=9；sandbox 3 条 dry_run_passed=3/3 | `dry_run_gate_3families_*.tar.gz` |
| Controlled execution | Kind sandbox 真 patch + postcondition + rollback | 3/3 real_executed；3/3 patch/postcondition/rollback success | `controlled_exec_sandbox_3families_2026-06-21_111723.tar.gz` |
| Trajectory/Reward Evaluator | 导出 trajectory_events / reward_events | 21 trajectory events；21 reward events；final execution reward n=3 mean=0.8 | `../artifacts/reward_events/` |
| Multi-fault LinUCB | 三故障族 hard-mode offline replay | random 17.04%；min-risk 33.56%；LinUCB 73.68%；unsafe=0 | `multifault_linucb_replay_summary_2026-06-21_214157.json` |

## 3. 简历表述落实情况

| 简历表述 | 当前完成度 | 说明 |
|---|---:|---|
| 基于 STRATUS 架构搭建并扩展多智能体 SRE 系统 | 基本完成 | 已复现 STRATUS/AIOpsLab live 故障修复，并扩展 Planner、Gate、Executor、Reward、LinUCB 模块；但 QLoRA Gate 尚未完全嵌回 STRATUS runtime。 |
| 确定性控制流编排 Diagnosis、Mitigation、Undo | 部分完成 | 原 STRATUS 具备多阶段流程；当前扩展已实现 controlled executor 与 rollback；下一步是把 STRATUS 改为 read-only diagnosis + gated write。 |
| 按角色隔离只读观测与写操作权限 | 部分完成 | 在设计和 controlled execution 中已拆出安全写执行器；但原 STRATUS runtime 的 read-only write blocker 还未完全接入。 |
| 综合利用 Trace、日志和 K8s 状态 | 基本完成 | live trajectory 与 STRATUS/AIOpsLab 使用 logs、trace、kubectl state；当前 shadow prompt 主要使用日志和 K8s snapshot。 |
| 打通故障定位、修复规划与 NL2Kubectl 自动执行闭环 | 基本完成 | 原 STRATUS live 修复闭环已跑通；QLoRA 侧已到 sandbox controlled execution；live QLoRA gated execution 仍是下一阶段。 |
| 最小变更约束、高风险操作拦截 | 完成 | static safety、allowlist path、block delete/high-risk 已完成。 |
| 前后置条件校验 | 完成 | JSON Patch `test` precondition、postcondition check 已在 dry-run 和 controlled execution 中完成。 |
| kubectl dry-run | 完成 | sandbox 三故障族 server-side dry-run 3/3 pass。 |
| ActionStack 资源快照 | 完成 | controlled execution 前保存 before.json / before.yaml。 |
| 自动回滚 | 完成 sandbox 版 | 三故障族 rollback 3/3 success；live AIOpsLab Oracle 场景尚待接入。 |
| Kind 与 AIOpsLab 轨迹 | 基本完成 | Kind sandbox + AIOpsLab live trajectories 都已完成；完整 QLoRA-gated live AIOpsLab 还未做。 |
| 记录工具调用、K8s diff、回滚、Oracle | 部分到基本完成 | live trajectory 记录 Oracle/资源 diff；controlled execution 记录 rollback/ActionStack；统一 trajectory/reward exporter 已完成。 |
| Oracle 通过轨迹构造 Tool-Calling 数据 | 完成 | 基于 verified live trajectories/templates 构造 570 Tool-Calling / SFT / preference 数据。 |
| 失败纠错样本 | 部分完成 | 已有 rejected candidates / wrong patch / missing precondition 等负例；真实失败纠错 trajectory 可后续扩展。 |
| LoRA 微调 Qwen2.5-7B Planner | 完成 | QLoRA multi-fault adapter 已训练并评测。 |
| 优化修复计划生成、工具选择与参数填充 | 完成 | offline eval schema 与字段准确率 100%。 |
| LinUCB 对安全候选计划排序 | 完成 offline hard-mode 版 | 三故障族 570 episodes，LinUCB 73.68% vs random 17.04% / min-risk 33.56%，unsafe=0。 |
| 以终态 Oracle、执行成本和回滚惩罚构造奖励 | 部分到基本完成 | reward evaluator 已落盘 postcondition/执行成本/rollback reward；真实 live Oracle reward 还需下一阶段接入。 |

## 4. 严格结论

如果按“简历项目表述”的工程/算法原型标准，当前已经基本落实，核心证据链完整。

如果按“完整线上产品/完整 live AIOpsLab QLoRA 接管”的严格标准，还差两项：

1. 将 STRATUS runtime 改成 read-only diagnosis，并把写操作交给 QLoRA + Gate + Executor。
2. 在 live AIOpsLab fault injection 中接入真实 Oracle reward，并做 QLoRA-gated live repair。

## 5. 面试时推荐说法

当前最稳表述：

> 这个项目已经完成了从 live AIOpsLab 轨迹采集、Tool-Calling/SFT/preference 数据构造、Qwen2.5-7B QLoRA Planner 训练，到在线 Planner Server、9 条 live episode shadow replay、dry-run gate、Kind sandbox controlled execution、trajectory reward export 和 multi-fault LinUCB hard-mode replay的完整原型。当前 controlled execution 仍在 sandbox 环境验证，下一步是将 STRATUS 改造成 read-only diagnosis + QLoRA gated execution，并接入 live AIOpsLab Oracle reward 做持续进化。
