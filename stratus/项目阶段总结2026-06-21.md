# SafeOps-Agent / STRATUS-AIOps 项目阶段总结

## 1. 项目目标

本项目围绕 Kubernetes 场景下的自主 SRE / AIOps 安全自愈问题，基于 STRATUS 架构和 AIOpsLab benchmark，构建一个面向微服务故障诊断、修复规划、安全执行和回滚的多智能体系统。系统目标不是简单让 LLM 生成 kubectl 命令，而是将 LLM Planner 的输出约束为结构化 MitigationPlan，并在执行前加入 Schema 校验、静态安全检查、JSON Patch precondition、kubectl dry-run、ActionStack 资源快照、postcondition 检查和 rollback 机制，从而形成可审计、可回滚、低风险的 Kubernetes 自愈闭环。

当前项目已经完成从离线数据集构造、QLoRA Planner 训练、离线评测、A800 在线推理服务、ARM 侧 shadow replay、dry-run gate，到 Kind sandbox controlled execution with rollback 的完整阶段性链路。

---

## 2. Live AIOpsLab / STRATUS 故障轨迹

项目首先在 STRATUS / AIOpsLab 环境中复现并采集 Kubernetes live mitigation 轨迹，覆盖三类配置型故障族：

### 2.1 Service targetPort mismatch

- 故障对象：Service/user-service
- 根因：Service 的 targetPort 指向错误端口 9999，而后端容器实际监听 9090
- 修复动作：JSON Patch `/spec/ports/0/targetPort: 9999 -> 9090`
- live 结果：3-run success

### 2.2 Deployment scaled to zero

- 故障对象：Deployment/user-service
- 根因：Deployment replicas=0，导致没有可用 Pod，Service endpoints 为空
- 修复动作：JSON Patch `/spec/replicas: 0 -> 1`
- live 结果：3 次 evaluation success，另有 1 次 infra setup failure，不计为 Agent 修复失败

### 2.3 Deployment nodeSelector points to nonexistent node

- 故障对象：Deployment/user-service
- 根因：nodeSelector 指向不存在的 `extra-node`，导致 Pod Pending / unschedulable
- 修复动作：remove `/spec/template/spec/nodeSelector`
- live 结果：3 次 evaluation success

这三类故障构成后续 multi-fault Planner 数据集、shadow replay 和 gated execution 原型的基础。

---

## 3. Multi-fault MitigationPlan 数据集

基于 verified live trajectories 和参数化扩增模板，构造三故障族 MitigationPlan 数据集：

- SFT samples: 570
- Tool-Calling samples: 570
- Preference pairs: 570
- Train / Val / Test: 462 / 53 / 55

fault type 分布：

- `service_target_port_mismatch`: 244
- `deployment_scaled_to_zero`: 163
- `deployment_node_selector_nonexistent_node`: 163

所有样本均通过 MitigationPlan Schema 校验，preference pairs 也通过相应 Schema 校验。需要注意的是，数据集中多数样本来自 verified live templates 的参数化扩增，不能表述为额外真实 live episode。

---

## 4. QLoRA Planner 训练与离线评测

在 A800-SXM4-40GB 上，基于 Qwen2.5-7B-Instruct 进行 4-bit QLoRA 微调，得到 multi-fault Planner adapter：

- Adapter: `qwen25-7b-multifault-qlora`
- Adapter size: 155MB
- Train samples: 462
- Eval samples: 53
- Train runtime: 851.8s
- Train loss: 0.05695
- Eval loss: 0.01112

离线测试集共 55 条样本，结果如下：

### Base Qwen2.5-7B-Instruct

- JSON 合法率: 1.0
- Schema 通过率: 0.0
- fault_type / operation / resource / patch path / patch value / risk 字段准确率: 0.0

### Multi-fault QLoRA Planner

- JSON 合法率: 1.0
- Schema 通过率: 1.0
- fault_type_acc: 1.0
- operation_acc: 1.0
- resource_kind_acc: 1.0
- resource_namespace_acc: 1.0
- resource_name_acc: 1.0
- patch_path_acc: 1.0
- patch_value_acc: 1.0
- risk_acc: 1.0
- unsafe_rate: 0.0

该结果说明 Base 模型虽然能够输出 JSON，但无法稳定遵循 MitigationPlan Schema；QLoRA 后模型学会了三故障族的结构化修复计划格式和关键 patch 参数。

---

## 5. LinUCB Offline Candidate Ranking

在 targetPort 故障族上，基于 preference pairs 构造安全候选计划集合，并进行 LinUCB offline replay。候选包括正确 JSON Patch、错误 patch value、缺失 precondition、rollout restart、merge patch 和 delete service 等。系统先通过静态策略拦截 delete/create/high-risk 操作，再用 22 维计划特征进行 LinUCB 排序。

offline replay 结果：

- random_safe selected_correct_rate: 21.31%
- min_risk selected_correct_rate: 34.02%
- LinUCB selected_correct_rate: 97.95%
- unsafe_selected_rate: 0.0

这部分证明了在安全候选集合中，轻量 bandit/ranking 模块可以显著提升候选修复计划选择质量。当前 gated execution 原型先采用单 plan gate，后续可以接入 LinUCB 做多候选排序。

---

## 6. A800 Online Planner Server

为将 QLoRA Planner 接入运行时，项目将 multi-fault QLoRA Planner 封装为 A800 上的 FastAPI 在线推理服务：

- GET `/health`: 返回模型、adapter、CUDA/GPU 状态
- POST `/plan`: 输入 Kubernetes 故障 observation prompt，输出 MitigationPlan JSON
- Base model: Qwen2.5-7B-Instruct
- Adapter: qwen25-7b-multifault-qlora
- ARM 通过 SSH tunnel 访问 A800 服务

scale 和 assign demo 均返回 `schema_valid=true` 的结构化修复计划：

- scale: `/spec/replicas: 0 -> 1`
- assign: remove `/spec/template/spec/nodeSelector`

该服务只负责 Planner 推理，不执行 kubectl，不修改 Kubernetes，是后续 shadow mode 和 gated execution 的接口层。

---

## 7. ARM Shadow Replay on 9 Live Episodes

在 A800 Planner Server 基础上，ARM 侧实现 shadow-mode replay 脚本。该脚本读取真实 live episode 的 run.log / kubectl snapshot，构造 observation prompt，通过 SSH tunnel 调用 A800 `/plan`，并在 ARM 本地进行：

- server response check
- MitigationPlan Schema 二次校验
- fault_type canonicalization
- static safety check
- canonical repair agreement check

覆盖三故障族共 9 条 live-success episode：

- targetPort: 3
- scale: 3
- assign: 3

shadow replay summary：

- total_expected: 9
- total_loaded: 9
- server_ok: 9
- server_schema_valid: 9
- schema_valid_local: 9
- static_safe: 9
- agreement: 9
- shadow_only: 9
- executed: 0

这说明 QLoRA Planner 已经能够作为在线推理组件接入 live STRATUS/AIOpsLab workflow，并在不执行 kubectl 的前提下，对真实 live episodes 生成可校验、静态安全、与 canonical repair 一致的 MitigationPlan。

---

## 8. Dry-run Gate Prototype

在 shadow mode 之后，项目实现第一层 gated execution：dry-run gate。该模块读取 shadow plan，执行：

1. static safety check
2. MitigationPlan -> `kubectl patch --dry-run=server`
3. live resource JSON Patch test precondition check
4. Kubernetes API Server server-side dry-run validation
5. 输出 `shadow_dry_run_report.json`

### 8.1 Historical replay 9 episodes

由于 historical replay episode 对应的 live Kubernetes resources 已被清理，server-side dry-run 被安全跳过：

- total_loaded: 9
- static_safe: 9
- dry_run_requested: 9
- dry_run_executed: 0
- real_executed: 0
- skip reason: `live_precondition_mismatch_or_resource_unavailable`

这说明 gate 没有在资源缺失时盲目发 patch，符合安全设计。

### 8.2 Sandbox fault-state dry-run

随后在 Kind 中创建最小 `test-social-network` sandbox，分别构造三类故障态资源：

- targetPort: Service targetPort=9999
- scale: Deployment replicas=0
- assign: Deployment nodeSelector `kubernetes.io/hostname=extra-node`

server-side dry-run 结果：

- total_loaded: 3
- targetPort / scale / assign 各 1 条
- static_safe: 3
- dry_run_requested: 3
- dry_run_executed: 3
- dry_run_passed: 3
- real_executed: 0

该阶段证明 QLoRA-generated MitigationPlan 不仅能通过静态安全检查，还能在资源和前置条件存在时通过 Kubernetes API Server 的 server-side dry-run 校验。

---

## 9. Controlled Execution Sandbox Prototype

在 dry-run gate 通过后，项目进一步实现 sandbox-only controlled execution。该阶段首次执行真实 `kubectl patch`，但严格限制在 Kind 的最小 sandbox 环境中，并加入完整安全闭环：

1. 读取 canonical MitigationPlan
2. static safety check
3. JSON Patch test precondition check
4. ActionStack resource snapshot
5. 执行真实 kubectl patch
6. postcondition check
7. rollback patch generation
8. rollback execution
9. rollback result check

覆盖三故障族各 1 条：

- targetPort
- scale
- assign

controlled execution summary：

- total_expected: 3
- total_loaded: 3
- by_family: targetPort=1, scale=1, assign=1
- static_safe: 3
- precondition_matches: 3
- execute_real_requested: 3
- real_executed: 3
- patch_succeeded: 3
- postcondition_passed: 3
- rollback_executed: 3
- rollback_succeeded: 3

该阶段说明系统已经完成从 QLoRA Planner 输出到真实 Kubernetes patch，再到 postcondition 验证与 rollback 的最小闭环。

---

## 10. 当前完整路线

目前项目已经形成如下证据链：

```text
offline dataset
→ QLoRA training
→ offline eval
→ A800 online Planner Server
→ ARM shadow replay on 9 live episodes
→ dry-run gate
→ sandbox server-side dry-run pass
→ sandbox controlled execution with rollback
```

这是一个从离线学习到在线推理、从只读 shadow 到安全执行闭环的完整阶段性系统原型。

---

## 11. 当前边界与限制

当前结果仍需明确边界：

1. Multi-fault 数据集中多数样本来自 verified live templates 的参数化扩增，不等同于额外真实 live episodes。
2. QLoRA offline eval 的 100% 结果是离线 Planner Schema / 参数填充能力验证，不代表完整 live STRATUS 端到端成功率。
3. Shadow replay 调用真实 live episode 的日志和 snapshot，但不执行 kubectl。
4. Controlled execution 当前只在 Kind sandbox 的最小资源上验证，不等同于完整 AIOpsLab workload 的 Oracle pass。
5. 下一阶段需要将 gate 接入真实 AIOpsLab fault injection 流程，统计 success rate、first-attempt success、TTM、steps、rollback count 和 Oracle pass。

---

## 12. 下一阶段计划：Live AIOpsLab Controlled Execution

后续计划进入 live AIOpsLab controlled execution，目标是将当前 sandbox gate 接入真实故障注入流程：

1. AIOpsLab 注入真实故障
2. STRATUS 采集 observation
3. QLoRA Planner Server 生成 MitigationPlan
4. static safety gate
5. JSON Patch precondition
6. kubectl server-side dry-run
7. ActionStack snapshot
8. 执行真实 kubectl patch
9. postcondition check
10. AIOpsLab Oracle validation
11. 失败 rollback，成功记录 trajectory

建议从最简单的 `deployment_scaled_to_zero` 开始，因为该故障的 patch 和 postcondition 最容易验证：

- precondition: `/spec/replicas == 0`
- action: `/spec/replicas -> 1`
- postcondition: `/spec/replicas == 1` and pods become ready
- rollback: `/spec/replicas -> 0`

目标是将当前结果从 “sandbox controlled execution” 推进到 “live AIOpsLab gated execution”。

---

## 13. 简历/面试可用表述

基于 STRATUS 架构扩展面向 Kubernetes 的多智能体自主 SRE 系统，围绕 Service targetPort、Deployment replicas、nodeSelector 三类故障采集 live AIOpsLab mitigation 轨迹，并构造 570 条 multi-fault MitigationPlan SFT / Tool-Calling / preference 数据。使用 A800 对 Qwen2.5-7B-Instruct 进行 4-bit QLoRA 微调，使 Base 模型在测试集上 Schema 通过率从 0% 提升至 100%，三故障族 patch path/value、resource、operation 与 risk 字段准确率均达到 100%。进一步将 QLoRA Planner 封装为 A800 在线推理服务，通过 ARM shadow replay 在 9 条 live-success episode 上实现 server/schema/static-safety/agreement 9/9 通过；实现 dry-run gate 与 sandbox controlled execution，在 Kind 中完成三故障族真实 kubectl patch、postcondition 验证与 rollback 闭环。
