# 面试备考手册：面向 Kubernetes 的多智能体自主 SRE 系统 原理与问答

> **适用对象**：简历项目是《面向 Kubernetes 的多智能体自主 SRE 系统》（基于 STRATUS 架构 + CrewAI + QLoRA Planner + 分层 Gate + LinUCB），正在面试「Agent Infra」岗位。
>
> **面试官手里只有简历，看不到代码**。考察四个维度：**编码能力 / AI 使用 / agent 理解 / 场景项目实践**。所以全书所有「面试问答」都是**概念性、设计性、基于简历措辞**的回答——不贴代码、不背 file:line。
>
> **怎么用这份手册**：第 0 章先建心智地基（用比喻记住整个项目是什么 + 诚实讲法）；第 1–6 章是六大技术主题，每章「直觉→原理→场景→雷区→问答」一条龙；第 7–10 章按四个考察维度给出面试问答（agent 理解 / 编码能力 / AI 使用 / 场景项目实践）；第 11 章是整体策略 + 雷区速查表；附录 A 是一页速查卡。
>
> **一个最重要的原则贯穿全书**：面试官不在乎你是不是大牛，在乎你**懂不懂自己做的这个东西的原理和权衡**。所以全书反复强调「**诚实讲事实 + 主动讲权衡 + 主动讲改进点**」——这比不懂装懂强一万倍。这个项目里有几处「简历写得比较满、实际是原型/沙箱验证」的地方，主动承认 + 给出生产级改进路线，反而是 agent infra 岗最加分的姿态。

---

## 完整目录

- [第 0 章 开篇：先建立认知](#第-0-章-开篇先建立认知)
  - [0.1 这个项目到底是什么：三句话 + 三个比喻](#01-这个项目到底是什么三句话--三个比喻)
  - [0.2 为什么不是「让 LLM 直接生成 kubectl」](#02-为什么不是让-llm-直接生成-kubectl)
  - [0.3 简历与代码的诚实讲法 + 4 大雷区预警](#03-简历与代码的诚实讲法--4-大雷区预警)
- [第 1 章 整体架构：确定性控制流 Diagnosis→Mitigation→Undo](#第-1-章-整体架构确定性控制流-diagnosismitigationundo)
- [第 2 章 结构化 MitigationPlan + Tool Use + 隔离与权限](#第-2-章-结构化-mitigationplan--tool-use--隔离与权限)
- [第 3 章 QLoRA Mitigation Planner（数据 / LoRA 原理 / 离线评测）](#第-3-章-qlora-mitigation-planner)
- [第 4 章 LinUCB 安全候选计划排序（Contextual Bandit）](#第-4-章-linucb-安全候选计划排序)
- [第 5 章 分层 Gate 执行链 + ActionStack 回滚闭环](#第-5-章-分层-gate-执行链--actionstack-回滚闭环)
- [第 6 章 评估：AIOpsLab / Oracle / Trajectory-Reward](#第-6-章-评估aiopslab--oracle--trajectory-reward)
- [第 7 章 agent 理解 + 系统设计题（考察维度：agent 理解）](#第-7-章-agent-理解--系统设计题)
- [第 8 章 编码能力题（考察维度：编码能力）](#第-8-章-编码能力题)
- [第 9 章 AI / LLM 使用经验题（考察维度：AI 使用）](#第-9-章-ai--llm-使用经验题)
- [第 10 章 场景项目实践深问（考察维度：场景项目实践）](#第-10-章-场景项目实践深问)
- [第 11 章 面试整体策略 + 雷区清单速查](#第-11-章-面试整体策略--雷区清单速查)
- [附录 A 一页速查表](#附录-a-一页速查表)

---

## 第 0 章 开篇：先建立认知

这一章是全书「心智地基」。用生活类比把整个项目装进脑子，后面六章都是在这上面长出来的细节。

### 0.1 这个项目到底是什么：三句话 + 三个比喻

**三句话讲清**：
1. 这是一个**让 LLM 给 Kubernetes 故障开「处方」、并安全地把处方执行掉、不行还能回滚**的多智能体系统。
2. 它不直接让 LLM 敲 kubectl 命令（黑盒、不可审、不可回滚），而是先把 LLM 的输出约束成一份**结构化的修复计划 MitigationPlan**（像手术方案），再过一道道**安全闸门**才真正动手改集群。
3. 它基于 STRATUS（NeurIPS 2025 的多智能体云可靠性系统）架构扩展，用 QLoRA 微调了一个专门填这种「修复工单」的小模型 Planner，并用 LinUCB 在多个候选方案里挑最安全的。

**三个比喻记住全项目**：

- **比喻①：有安全意识的值班 SRE + 三道安检 + 拍照存档。** 普通 LLM agent 像「上来就敲命令的实习生」，这个系统像「严谨的值班 SRE」：先写手术方案（MitigationPlan）→ 过安检（静态检查 / dry-run 彩排 / 前置条件核对）→ 动手前给资源拍照（ActionStack 快照）→ 动完验证（postcondition）→ 不行就按照片还原（rollback）。
- **比喻②：医院分诊三个角色。** Diagnosis 是「只查不治的诊断医生」（读 trace/log/集群状态，下诊断），Mitigation 是「按方案动刀的主刀医生」（执行结构化修复），Undo 是「出事按照片复原的抢救/复原」（回滚）。**角色按职责分工具、分权限**——这就是简历里「按角色隔离只读观测与写操作权限」的来源。
- **比喻③：火箭发射的分级倒计时。** shadow replay（只模拟、不动手）→ dry-run gate（彩排、不上天）→ controlled execution（真发射、但带逃生塔和回滚）。**风险一步一步放大，每一步都有 bail-out**。

### 0.2 为什么不是「让 LLM 直接生成 kubectl」

这是全书最高频的考点之一，必须能脱口而出。

**直接生成 kubectl 的三个致命问题**（对比「结构化 MitigationPlan」）：

| 维度 | 直接生成 kubectl 命令 | 结构化 MitigationPlan（本项目） |
|---|---|---|
| 可审计 | 一行命令字符串，黑盒 | 结构化 JSON：fault_type / resource / patch / precondition / postcondition / risk，可逐字段审 |
| 可校验 | 没法在执行前判断对不对 | JSON Patch `test` 做前置条件、postcondition 做后置校验、dry-run 做服务端预演 |
| 可回滚 | 改完不知道改了啥，回滚无从下手 | ActionStack 存 before 快照，失败按 inverse patch 回滚 |
| 最小变更 | LLM 可能大改资源 | 约束成 JSON Patch（只改必要字段），最小变更 |
| 安全 | 高危命令（delete namespace）可能被生成 | 高风险操作拦截 + risk 分级 + 白名单 |

**一句话**：把 LLM 的输出从「自由文本命令」升级成「结构化、可校验、可回滚的计划」，本质是把**不确定性约束进确定性骨架**——这正是 agent infra 最核心的工程思想（LLM 负责「想」，确定性控制流负责「兜底」）。

### 0.3 简历与代码的诚实讲法 + 4 大雷区预警

> ⚠️ **最重要的诚实原则**：这个项目是**真实跑通的原型**，但有几处「简历写得比较满、实际还在沙箱/离线阶段」。**主动指出边界 + 给改进路线 = agent infra 岗最加分的姿态**。被追问到穿帮，比主动承认糟一万倍。

**全书最该背的 4 大雷区**（每条在对应章节会重点讲）：

> **🚨 雷区一：「按角色隔离只读观测与写操作权限」。** 简历听起来像 Diagnosis 被强制只读。实际：隔离主要靠 CrewAI 的 sequential 串行编排 + 工具按角色分发 + verb 白名单 + dry-run + ActionStack。论文 STRATUS 的 A-Lock（读写锁）和「分布式资源级互斥」在当前实现里**没完整落地**（论文自己也承认当前是 one-instance-per-system）。诚实讲法：**「设计上 Diagnosis 只读、Mitigation 写，靠 sequential 串行 + 白名单 + dry-run 约束；论文的 A-Lock 和分布式锁是已识别的下一步（拆 ReadOnly/Write 工具 + 只读 ServiceAccount + K8s Lease + resourceVersion CAS）」**。
>
> **🚨 雷区二：QLoRA 的「100%」。** 简历说微调后 schema 通过率从 0→100%、字段准确率 100%。实际：这是**离线测试集上 Planner 的 schema 遵循 / 参数填充能力**，不是 live 端到端修复成功率；数据集 570 条多为 verified live 模板的参数化扩增，不是额外真实 episode。诚实讲法：**「100% 是离线 schema/字段填充指标，证明 QLoRA 让小模型学会了结构化工单格式；live 端到端成功率是下一阶段接入 Oracle 才统计的」**。
>
> **🚨 雷区三：「端到端闭环验证」的范围。** 简历说完成端到端闭环。实际：controlled execution（真 patch + postcondition + rollback）只在 **Kind 沙箱的最小资源**上验证了三故障族 3/3；**完整 live AIOpsLab Oracle 接管还没做**（shadow/dry-run 都是只读或预演）。诚实讲法：**「从离线数据→QLoRA→在线服务→shadow→dry-run→沙箱 controlled execution 是完整原型链路；live QLoRA-gated repair（接真实 Oracle reward）是下一步」**。
>
> **🚨 雷区四：LinUCB 的「73.68%」。** 简历说 LinUCB 在沙箱 episode 排序。实际：这是 **offline replay**（在生成的候选集上回放），不是 online bandit 在线更新；reward 也是用 Oracle 终态 + 执行成本 + 回滚惩罚**构造**的，不是 live 反馈。诚实讲法：**「73.68% 是 offline hard-mode replay 结果，证明在安全候选集上 bandit 显著优于 random/min-risk；online bandit 更新和 live reward 是下一步」**。

带着这 4 个认知进入技术主题。第 1 章先讲整体架构。

---

## 第 1 章 整体架构：确定性控制流 Diagnosis→Mitigation→Undo

> 💡 **一句话秒懂**：把整个自愈系统看成「三个分工角色 + 一条串行流水线 + 一堆 NL2* 工具」，骨架就是 STRATUS 的确定性控制流。

### 🧠 小白直觉

把它想象成**一家带严格分工和质检的急诊医院**：

1. **分诊台（Diagnosis）**：病人（告警/故障）进来，诊断医生**只查不治**——查 trace、查日志、查集群状态，判断「根因是什么」。对应简历「故障定位」。
2. **手术室（Mitigation）**：主刀医生拿到诊断，**按结构化方案动刀**（不是凭感觉，是按 MitigationPlan 这个手术单执行 patch/scale）。对应简历「修复规划与 NL2Kubectl 自动执行」。
3. **复苏室（Undo）**：万一手术出问题（postcondition 没过 / 集群更糟），按术前拍的照片（ActionStack 快照）**还原**。对应简历「Undo」。

**关键**：这三个角色**串行执行、按职责拿不同工具、写操作有闸门**——这就是「确定性控制流编排」。它不是让一个 LLM 自由发挥，而是把流程**焊死成可控的图**。

### 📐 原理详解

**STRATUS 的动作分类（论文 §3）**——这是隔离与控制流的理论根基：

- `Aread`：只读动作（`kubectl get/describe/logs`），不改集群状态。
- `Awrite`：写动作（`kubectl apply/patch/scale`），改状态。
- `Aundo`：回滚动作（Undo agent 专用，内部用 Awrite 把状态还原到快照）。

**角色权限**：Detection/Diagnosis 设计上只 `Aread`；Mitigation 用 `Awrite + Aread`（读是为了 check 前后置条件）；Undo 用 `Aundo`。

**A-Lock（论文 Assumption A1）= readers-writer lock**：多个读 agent 可并发，最多一个写 agent 排他。覆盖一个 bounded transaction（最多 K=20 步）。

> 🚨 **诚实圆场（雷区一在此）**：A-Lock 在本项目实现里**没完整落地**。实际靠的是 CrewAI `Process.sequential`（单 Crew 内 task 串行）+ 工具按角色分发 + verb 白名单（默认关）+ dry-run + ActionStack。详见第 2 章。

**NL2* 工具族**：agent 不直接写 kubectl/PromQL，而是用自然语言调工具——`NL2Kubectl`（自然语言→kubectl）、`NL2Metrics`（→PromQL）、`NL2Traces`（→Jaeger）、`NL2Logs`（→LogQL），每个工具内部：LLM 生成查询 → linter 校验 → 执行。这把「自然语言推理」和「精确查询执行」解耦。

**为什么用 CrewAI 的 sequential 而不是自由 ReAct**：运维排障流程相对固定（诊断→修复→回滚），决策点可枚举，适合「确定性编排 + 局部 LLM 决策」的半自主模式，而不是让 LLM 每步自由决定（难调试、易跑偏、不可回滚）。这是 agent infra 选型的核心权衡（第 7.1 题详讲）。

### 🛠️ Agent Infra 场景视角

面试官真正关心的：你懂**「确定性骨架 + 局部智能」的工程权衡**——LLM 用在「理解故障、生成计划、填参数」这些需要语义的地方，而流程编排、安全闸门、回滚这些**绝不能交给 LLM 自由发挥**的部分用确定性代码焊死。这正是 agent infra 岗的核心方法论。

### 🎤 面试问答

**Q：用两句话讲清楚你这个系统的架构。**
A：它是一个基于 STRATUS 的 Kubernetes 自愈多智能体系统。三个角色按确定性控制流串行：Diagnosis（只读诊断，用 trace/log/集群状态定位根因）→ Mitigation（把 LLM 输出约束成结构化 MitigationPlan，过安全闸门后执行 kubectl 写）→ Undo（失败按 ActionStack 资源快照回滚）。核心思想是把 LLM 的不确定性约束进可审计、可校验、可回滚的确定性骨架。

**Q：为什么用多 agent 串行，而不是一个强大的 agent 全包？**
A：三个理由：① **职责隔离与权限**——诊断应该只读、修复才写，物理上分开工具和（理想中的）权限，缩小 blast radius；② **可观测可调试**——每个阶段产出结构化结果（诊断报告 / MitigationPlan / 回滚报告），任一阶段可单独测试和审计；③ **可回滚**——把「修复」和「回滚」分成独立角色，回滚逻辑确定化、不依赖 LLM。代价是延迟更高、链路更长，但对 SRE 这种「安全 > 速度」的场景值得。

---

## 第 2 章 结构化 MitigationPlan + Tool Use + 隔离与权限

> 💡 **一句话秒懂**：这是全书最重要的一章——「结构化计划」是可审/可校验/可回滚的根，「隔离与权限」是面试官最爱深挖的安全点。

### 🧠 小白直觉

**MitigationPlan = 标准化手术工单。** 想象医生不口述命令（「随便处理一下那个服务」），而是填一张**标准工单**：故障类型、根因资源、要做的 patch（改哪个字段的什么值）、前置条件、后置条件、风险等级。工单能被**护士审核**（schema 校验）、**彩排**（dry-run）、**事后核对**（postcondition）。

**隔离与权限 = 角色分工 + 门禁。** 诊断医生只能进档案室（读），主刀医生才能进手术室（写）。门禁分三层（理想）：① 工具层（诊断只发只读工具）② 代码层（verb 白名单）③ 集群层（RBAC，ServiceAccount 物理上没写权限）。

### 📐 原理详解

**MitigationPlan 的结构**（结构化合同的字段）：
- `fault_type`：故障类型（如 `service_target_port_mismatch`）。
- `root_cause`：根因资源（kind/namespace/name）。
- `actions[]`：动作列表，每个含 `operation`（json_patch/scale/...）、`resource`、`patch[]`、`risk`、`preconditions`、`postconditions`、`rollback` 策略。
- 用 Pydantic 严格校验（`extra=forbid`），格式错直接拒。

**JSON Patch（RFC 6902）是「最小变更」的核心**：
- `test`：前置条件——「只有当 `/spec/replicas == 0` 时才执行」（patch 前核对状态，避免误改）。
- `replace`/`add`/`remove`：实际变更——「`/spec/replicas` replace 成 1」。
- **inverse patch**：回滚——把 replace 反过来（1→0）。

> 公式直觉：JSON Patch 的 `test` op 是**乐观并发的前置断言**——执行前确认状态符合预期，类似数据库的 compare-and-swap。这和 Kubernetes 的 `resourceVersion` OCC 是互补的两条防线。

**Tool Use / Function Calling 原理**（agent infra 基石）：把工具的 schema（名字/描述/参数 JSON Schema）塞进 prompt，LLM 输出「调用意图」（工具名+参数），**框架**解析后实际执行，结果作为 observation 喂回。关键：**LLM 不直接执行，只输出意图**。本项目里 NL2* 工具就是这个模式——LLM 输出自然语言查询意图，工具内部生成并执行 kubectl/PromQL。

**隔离与权限的三层防御（defense-in-depth，理想设计）**：
1. **工具层**：拆 `ReadOnlyKubectlTool`（只 get/describe/logs）和 `WriteKubectlTool`（apply/patch/scale），Diagnosis 只发只读。
2. **代码层**：verb 白名单 + 命令形状校验（拦 pipe/重定向/复合命令）+ `--dry-run=server` 预演 + 高风险操作拦截。
3. **集群层（RBAC）**：Diagnosis 的 ServiceAccount 只给 `get/list/watch`，即使代码层被绕过，apiserver 也 403。

### ⚠️ 雷区（诚实圆场——这是面试官最爱戳的点）

> 🚨 **雷区一：read-only 没被「强制」。** 简历说「按角色隔离只读观测与写操作权限」。诚实现状：Diagnosis 和 Mitigation 在工具分发上有区分（Mitigation 多了 mitigation/wait 工具），但都共用核心的 NL2Kubectl；真正区分读写的开关 `forbid_unsafe_commands` 默认是关的；隔离主要靠 **sequential 串行 + verb 白名单 + dry-run**。论文的 A-Lock（读写锁）和分布式锁没完整落地。
>
> **圆法（背熟）**：「设计上 Diagnosis 只读、Mitigation 写，靠 sequential 串行 + 工具分发 + 白名单 + dry-run 约束写操作。论文的 A-Lock 读写锁和分布式资源级互斥是已识别的下一步——落地路线是：拆 ReadOnly/Write 两个工具从根上做 tool-level 隔离、给 Diagnosis 绑只读 ServiceAccount 让 K8s RBAC 兜底、用 K8s Lease + resourceVersion CAS 把 A-Lock 实现成 resource-scoped 分布式锁。」
>
> **为什么主动承认反而加分**：agent infra 岗招的就是能发现「prompt 不是权限系统、需要 RBAC 兜底、需要分布式锁」的人。你把「为什么 prompt-level 隔离不够、要 defense-in-depth」讲透，比硬吹「我有完整的读写锁」强一个量级——后者面试官一句「两个 STRATUS 进程同时写同一 Deployment 怎么办」就穿帮。

> 🚨 **雷区二：「高风险操作拦截」别吹过头。** 现状是 verb 白名单默认关 + dry-run 分支会拦住 kubectl 报错的命令 + 命令形状校验。`delete namespace` 这类只在很窄的路径有拦截。圆法：「实现了 verb 白名单 + 命令形状校验 + server dry-run 三道 gate；高风险拦截目前配置可配、生产应 default-on，并下沉到 K8s RBAC / AdmissionPolicy 做硬墙。」

### 🎤 面试问答（隔离与权限专题——面试官高频深挖）

**Q1：你的简历写「按角色隔离只读观测与写操作权限」，能讲讲为什么需要这个隔离、你是怎么设计的吗？**
A：先讲**为什么需要**——三个理由：① 一个本该只做诊断的 agent 如果能改集群，blast radius 不可控；② 多个 agent 并发写同一资源会冲突，需要写互斥（类似数据库读写锁）；③ 职责单一便于审计和回滚。再讲**怎么设计**——角色分工（Diagnosis 读 / Mitigation 写 / Undo 回滚）+ 工具按角色分发 + 确定性串行编排避免并发 + 写操作过白名单/dry-run/前置条件闸门。最后**诚实讲边界 + 改进**：理想的硬隔离应该 tool-level（ReadOnly vs Write 工具）+ K8s RBAC（只读 ServiceAccount 物理兜底）+ 分布式资源锁（K8s Lease + resourceVersion CAS），这些是我明确的下一步。

**Q2（深挖）：prompt 里告诉 Diagnosis「你只能读」算权限隔离吗？**
A：不算，prompt 不是权限系统——LLM 可能不听话、可能被 prompt injection 绕过。真正的权限要**强制（enforce）**：最硬的是 K8s RBAC（Diagnosis 的 ServiceAccount 只授 get/list/watch，apiserver 层直接 403，绕不过）；其次是 tool-level（只给只读工具，物理上没有写动词）；prompt/白名单只是**建议性**的第一道。我的项目目前主要靠串行 + 白名单 + dry-run，RBAC 硬墙是已识别要补的关键层。

**Q3（深挖）：如果两个 STRATUS 实例同时写同一个 Deployment，你的代码里有什么阻止冲突？**
A：诚实讲，当前实现里没有跨进程互斥——隔离靠单实例串行（论文也假设 one-instance-per-system）。生产级正确做法是**资源级分布式锁**：lock key 落到资源 `(kind, namespace, name)` 而不是进程；用 K8s Lease（coordination.k8s.io/v1，etcd 强一致）+ TTL（持有者崩溃自动释放防死锁）做排他写锁；再叠加 K8s 原生的 `resourceVersion` 乐观并发兜底（apply 带版本号，冲突 409）。这对应论文 §3.2 提出但未实现的 Coordination Controller。这是我知道没做、但有明确路线的部分。

**Q4（深挖）：agent 能自主调工具时，怎么防危险操作和越权？**
A：多层防御：① 工具层 RBAC——每个工具声明所需权限，高危操作（delete/drain/scale 到 0）分级，高危走 human-in-the-loop 二次确认；② 输出层校验——agent 生成的命令/计划执行前过 schema + 白名单 + dry-run + 沙箱；③ prompt injection 防护——不可信输入（用户消息、检索到的文档）当 data 不当 instruction，用 delimiter 隔离；④ 审计——每次工具调用、每次越权尝试落日志；⑤ 最小权限——service account 只给最小权限；⑥ K8s RBAC 兜底硬墙。SRE 场景特别：force delete pod / drain node 这类永远建议人执行而非 agent 自动执行。

---

## 第 3 章 QLoRA Mitigation Planner

> 💡 **一句话秒懂**：给一个「会说人话但不会填标准工单」的开源小模型，做一次专项训练，让它学会把故障描述填成合格的 MitigationPlan。

### 🧠 小白直觉

想象新来的实习生 Qwen2.5-7B：聪明、会说人话，但你让他填一张**严格的标准修复工单**（MitigationPlan），他要么漏字段、要么格式不对、要么乱编。Base 模型测试：JSON 能输出，但 schema 通过率 0%（不会按工单格式填）。

**QLoRA 微调** = 给他做一次「填工单」的岗前培训。训练后他学会了三故障族（targetPort / scale=0 / nodeSelector）的工单格式和关键 patch 参数，schema 通过率 0%→100%。

**为什么不直接用大模型（GPT-4/Claude）**：① 成本与延迟——在线推理每次修复都调大模型 API 贵且慢；② 私有部署——运维场景不能把集群故障数据发外部 API；③ 可控——小模型微调后行为更可预测。**QLoRA 让 7B 小模型在「填结构化工单」这个窄任务上达到专用能力**。

### 📐 原理详解（含公式，逐符号解释）

**LoRA（Low-Rank Adaptation）**：不全量微调（7B 参数全更新太贵），而是**冻结原权重，只训练一个低秩增量**。

> 公式：`W = W₀ + ΔW = W₀ + B·A`
> - `W₀`：冻结的原始权重（不更新）
> - `A`：`r × d` 的降维矩阵（把 d 维降到 r 维，r 远小于 d，如 r=8/16）
> - `B`：`d × r` 的升维矩阵
> - `ΔW = B·A`：秩为 r 的更新量
> - 直觉：微调所需的权重变化「本征秩」很低，用一个低秩近似就够了——只训练 A、B 两个小矩阵（参数量从 d² 降到 2·d·r），省显存、省时间。

**QLoRA = Quantization + LoRA**：把冻结的 `W₀` **4-bit 量化**（NF4：Normal Float 4-bit，专为正态分布权重设计的量化格式），原本 7B 模型要 ~14GB（fp16），4-bit 后 ~3.5GB，单张 A800-40G 就能训。LoRA 增量部分（A、B）仍用高精度（bf16）训练，保证梯度质量。结果：**adapter 只有 ~155MB**，可热插拔。

**为什么 schema 通过率能 0→100%**：Base 模型没见过 MitigationPlan 这种私有 schema，只会输出泛泛 JSON；微调后它学到了「这个任务的输出格式和字段约束」。**注意**（雷区二）：100% 是**离线** schema/字段填充指标，证明的是「学会格式 + 关键参数」，不是 live 端到端成功率。

**数据构造**：基于 live AIOpsLab verified 轨迹 + 参数化扩增模板，构造 570 条（SFT / Tool-Calling / preference 各 570，train/val/test = 462/53/55）。三故障族分布：targetPort 244 / scale 163 / assign 163。**所有样本过 MitigationPlan schema 校验**。

### ⚠️ 雷区（诚实圆场）

> 🚨 **雷区二在此：100% 的边界。** 别说「微调后修复成功率 100%」。正确说法：「离线测试集上 schema 通过率 0→100%、fault_type/operation/resource/patch_path/patch_value/risk 字段准确率 100%，证明 QLoRA 让 7B 小模型学会了三故障族的结构化工单格式和关键 patch 参数；这是 Planner 的 schema/参数填充能力，不等于完整 live 端到端修复成功率。」
>
> 🚨 **数据扩增别吹成真实 episode。** 570 条多为 verified live 模板的参数化扩增（改名字/端口/namespace），不是额外采集的真实 live 轨迹。圆法：「核心 verified 轨迹是 live 采集的，数据集在此基础上做参数化扩增扩充规模；扩增样本不等于额外真实 episode。」

### 🎤 面试问答

**Q：为什么用 LoRA 而不是全量微调？为什么 QLoRA？**
A：全量微调 7B 要更新所有参数，显存和时间成本高，还容易灾难性遗忘。LoRA 冻结原权重、只训低秩增量 `ΔW = B·A`，参数量降一两个数量级，单卡能训、adapter 小（155MB）可热插拔。QLoRA 进一步把冻结权重量化到 4-bit（NF4），7B 模型 ~3.5GB 显存就能训，LoRA 增量仍用高精度保证梯度质量。代价：表达能力上限略低于全量微调，但对「学会一个窄任务的输出格式」足够。

**Q：你的训练数据怎么来的？570 条够吗？**
A：基于 live AIOpsLab 采集的 verified 成功轨迹（三故障族），加参数化扩增模板（换资源名/端口/namespace）扩到 570 条，按 462/53/55 划分。诚实讲：核心轨迹是真实的，扩增是为了扩充 schema 多样性、不等于额外真实 episode；570 条对这个窄任务（三故障族填工单）够用，扩到更多故障族需要更多真实轨迹。

---

## 第 4 章 LinUCB 安全候选计划排序

> 💡 **一句话秒懂**：Planner 可能生成好几个「看起来都行」的修复方案，用一个多臂老虎机（bandit）在安全候选里学「哪个最可能对、最安全」。

### 🧠 小白直觉

想象餐厅试菜选厨师：有几个候选菜（候选计划），你不知道哪个最好，每次试一个、根据反馈（好不好吃 = Oracle 终态 + 执行成本 + 回滚惩罚）学习。**LinUCB = 会看「菜的特征」（context）的试菜策略**——不仅看历史平均好评，还结合这道菜的食材特征（计划的 22 维特征）预测。

**关键设计**：先把**不安全的候选直接静态拦截**（delete/create 这类不进候选池），只在**安全候选集**里用 bandit 排序。这样保证 unsafe_rate = 0。

### 📐 原理详解（含公式）

**Contextual Bandit（上下文老虎子）**：每个候选计划是一个「臂 arm」，每次选一个执行、拿到 reward，目标是累积 reward 最大。和监督学习不同——你只能观察到「选了的那个」的 reward（部分反馈）。

**LinUCB**：线性模型假设 reward 与特征线性相关，用 **置信上界（UCB）** 平衡「exploit（选历史最优）」和「explore（试不确定的）」。

> 公式（简化）：对每个臂，`UCB = θᵀx + α·√(xᵀA⁻¹x)`
> - `x`：候选计划的 22 维特征（fault_type 编码 / patch 路径 / risk / 是否有 precondition 等）
> - `θ`：学到的权重（`A⁻¹` 是特征协方差矩阵的逆）
> - `α`：探索强度，α 大更爱探索
> - 第一项 `θᵀx`：exploit（预测 reward 高的）
> - 第二项 `α·√(...)`：explore（不确定性大的，多给机会）

**候选集构造**（每个 canonical plan 合成一组安全候选）：
- `chosen_json_patch`：正确 patch，reward +1.0
- `missing_test_precondition`：缺前置条件，+0.45
- `wrong_patch_value`：错误值，-0.80
- `rollout_restart_decoy`：诱饵（重启而非修根因），0.0
- `merge_patch_decoy`：-0.25
- `rejected_delete`：delete，-1.0，**被 safety 静态拦截，不进候选池**

**Reward 设计**：`终态 Oracle（修没修好）+ 执行成本（步数/token）+ 回滚惩罚（要不要回滚）`。这对应简历「以终态 Oracle、执行成本和回滚惩罚构造奖励」。

**结果（hard-mode offline replay）**：LinUCB 73.68% vs random 17.04% vs min-risk 33.56%，unsafe = 0。

### ⚠️ 雷区（诚实圆场）

> 🚨 **雷区四在此：offline replay 不是 online bandit。** 别说「系统在线学习排序」。正确说法：「这是 **offline replay**——在生成的安全候选集上回放，验证 bandit 排序质量；reward 是用 Oracle 终态 + 执行成本 + 回滚惩罚**构造**的，不是 live 在线反馈。online bandit 更新（真正边跑边学）和 live reward 接入是下一步。」
>
> 🚨 **22 维特征是手工设计的，不是端到端学的。** 圆法：「特征工程做的，覆盖 fault_type/patch 路径/risk/前置条件等；端到端学特征（如把 plan 编码成 embedding）是可扩展方向。」

### 🎤 面试问答

**Q：为什么用 LinUCB 而不是 RL（如 PPO）或直接用 LLM 打分？**
A：权衡三点：① **样本效率**——RL 要大量在线交互，运维场景失败代价高、样本贵；LinUCB 是线性 bandit，小样本就能学，且支持 offline replay。② **安全可约束**——我先用静态规则把不安全候选（delete/create）踢出池子，bandit 只在安全集里选，保证 unsafe=0；RL 很难硬保证安全约束。③ **可解释**——LinUCB 的权重和 UCB 可解释（哪些特征重要），LLM 打分是黑盒。代价：LinUCB 假设 reward 线性可分，复杂非线性关系不如 RL；但对「在已知安全候选里排序」够用。

**Q：reward 怎么设计？为什么这三个分量？**
A：`Oracle 终态（修没修好，主导项）+ 执行成本（步数/token，惩罚绕路）+ 回滚惩罚（要回滚说明改错了，重罚）`。设计思想是既要「修对」又要「少折腾、别改错」——只看 Oracle 会鼓励激进修改，加成本和回滚惩罚引导「最小、最安全、一次成功」的方案。

---

## 第 5 章 分层 Gate 执行链 + ActionStack 回滚闭环

> 💡 **一句话秒懂**：风险一步一步放大——先只看不动手（shadow）→ 彩排（dry-run）→ 真动手但带逃生塔（controlled execution + rollback）。

### 🧠 小白直觉

**分层 Gate = 火箭发射分级倒计时**：
1. **shadow replay（只模拟）**：拿真实故障的日志/快照，让 Planner 生成计划，**只校验不执行**——验证「Planner 能不能生成合法、安全、和 canonical 一致的计划」。
2. **dry-run gate（彩排）**：把计划转成 `kubectl patch --dry-run=server`，让 K8s API server **服务端预演但不真改**——验证「计划在资源和前置条件存在时能通过服务端校验」。
3. **controlled execution（真发射 + 逃生塔）**：真执行 kubectl patch，但前置条件核对 → 拍 before 快照 → patch → postcondition 校验 → 失败按 inverse patch 回滚。

每一步都有 bail-out，风险逐步放大，**绝不直接从 Planner 跳到真改集群**。

**ActionStack = 装修前拍照。** 动手前给每个要改的资源拍照（before.json/yaml），改完出问题按照片还原（declarative reconciliation）。这是简历「基于资源快照的 ActionStack」「失败变更自动回滚」的来源。

### 📐 原理详解

**controlled execution 的闭环步骤**（确定性代码，非 LLM）：
1. 读 MitigationPlan。
2. 静态安全检查（verb/kind/path 白名单、单 action、有 test 前置条件）。
3. JSON Patch `test` 前置条件核对（live 状态是否符合预期）。
4. ActionStack 资源快照（存 before.json/yaml）。
5. 执行真实 kubectl patch。
6. postcondition 校验（patch 后状态是否符合预期）。
7. 失败则生成 inverse patch 回滚。
8. 回滚结果校验。

**回滚的数学**：inverse patch——对每个 `replace/add`，用 before 快照里的原值生成反向 op；对 `remove`，反向是 `add`。利用 K8s 声明式 reconciliation：把资源 apply 回快照状态即还原。

**前置/后置条件**（简历「资源级前后置条件校验」）：
- 前置：JSON Patch `test` op——执行前确认 `/spec/replicas == 0`，避免误改已经正常的资源。
- 后置：patch 后确认 `/spec/replicas == 1`，验证修复生效。

### ⚠️ 雷区（诚实圆场）

> 🚨 **雷区三在此：controlled execution 只在沙箱。** 别说「系统已在生产环境端到端验证」。正确说法：「controlled execution（真 patch + postcondition + rollback）在 **Kind 沙箱最小资源**上验证了三故障族 3/3（patch/postcondition/rollback 全成功）；这是**原型验证**，不是完整 live AIOpsLab Oracle 接管。完整链路（离线数据→QLoRA→在线服务→shadow→dry-run→沙箱 controlled execution）是跑通的，live QLoRA-gated repair 是下一步。」
>
> 🚨 **回滚的局限要会讲（体现深度）。** snapshot-based 回滚只还原 K8s 资源声明式状态，**不还原外部副作用**（write 触发的外部 API/数据库写、不可逆的 PV 删除）。圆法：「我了解 snapshot 回滚的边界——它依赖 K8s 声明式 reconciliation 还原资源对象，对外部副作用和不可逆操作无能为力，这正是论文 §4 承认 perfect undo 很难的原因；生产级需要 compensation logic（saga 补偿）+ 对不可逆操作执行前拒绝或转可恢复（如删文件→移 backup volume）。」

### 🎤 面试问答

**Q：你的 dry-run 是什么？能完全保证安全吗？**
A：用的是 `kubectl --dry-run=server`，让 API server 走完整 admission chain 预演但不持久化。它能在执行前抓到 schema 错误、权限不足、前置条件不满足。**但不能保证完全无副作用**——`--dry-run=server` 会调用 mutating admission webhook，对带副作用的 webhook（配额记账、外发通知）dry-run 阶段已产生真实副作用（除非 webhook 声明 `sideEffects: NoneOnDryRun`）。所以 dry-run 是「有限副作用预演」，不是零成本。

**Q：回滚失败怎么办？**
A：诚实讲：当前原型的回滚是「执行 inverse patch 然后校验」，如果回滚命令本身失败，理想应 fail-closed（检测失败 + 幂等重试 + 升级告警人工介入），而不是假装成功。生产级回滚要：① 检查 returncode 不静默吞；② 用 server-side apply（带 resourceVersion CAS）解 reconcile race；③ 不可逆操作执行前就拒绝；④ 外部副作用用 compensation。这正是我知道要加固的部分。

---

## 第 6 章 评估：AIOpsLab / Oracle / Trajectory-Reward

> 💡 **一句话秒懂**：怎么知道这个自愈系统到底行不行？用 AIOpsLab 的 Oracle（标准答案裁判）+ 可追溯的轨迹/奖励记录。

### 🧠 小白直觉

**Oracle = 阅卷老师。** AIOpsLab 是微软的 AIOps benchmark，每个故障注入任务都有一个 **Oracle**——它判断「agent 是不是真的把故障修好了」（不只是命令执行成功，而是业务可用性恢复 + 集群健康）。

**Trajectory / Reward 导出 = 考试录像 + 评分卡。** 把整个修复过程的每一步（工具调用、k8s 资源 diff、回滚动作、Oracle 结果）结构化记录下来，既能回溯定责（bad case 怎么发生的），又能做算法数据（成功的轨迹蒸馏成训练数据、reward event 喂给 bandit/RL）。

### 📐 原理详解

**AIOpsLab 评估流程**：故障注入 → 负载回放 → agent 执行 → 环境复位 → 指标汇总 → Oracle 判定（pass/fail）。指标包括 success rate、first-attempt success、TTM（time-to-mitigate）、steps、rollback count。

**三种 reward**（trajectory/reward 导出器产出）：
1. `planning_proxy_reward`：shadow 阶段的规划质量代理 reward（server/schema/静态安全/agreement 信号）——**不是最终执行 reward**。
2. `dry_run_gate_reward`：静态安全 + 服务端 dry-run 的 gate reward——**不是真实变更 reward**。
3. `controlled_execution_reward`：执行阶段 reward（静态安全 + 前置条件 + 真实 patch + postcondition + 执行成本 + 回滚惩罚）——**最接近真实、最适合未来 bandit/RL 的 reward**。

### ⚠️ 雷区（诚实圆场）

> 🚨 **「以终态 Oracle 构造奖励」的边界。** 简历说「以终态 Oracle、执行成本和回滚惩罚构造奖励」。诚实现状：reward evaluator 已经**落盘**了 postcondition/执行成本/rollback reward（controlled execution reward），但**真实 live Oracle reward 还没接进在线学习闭环**（LinUCB 用的是 offline 构造的 reward）。圆法：「reward 框架已经搭好并落盘了三种 reward；真实 live Oracle reward 接入在线 bandit/RL 更新是下一步。」

### 🎤 面试问答

**Q：怎么评估这个 agent 系统？你的指标是什么？**
A：分三层：① **任务层**——AIOpsLab Oracle 判 success rate / first-attempt success / TTM / steps / rollback count；② **过程层**——trajectory 记录每步工具调用、k8s diff、回滚，能回溯 bad case；③ **算法层**——reward event（planning proxy / dry-run gate / controlled execution）供 bandit/RL。诚实讲：当前完整 Oracle 端到端主要在沙箱三故障族验证，live Oracle 接入是下一步。

**Q：Oracle 是什么？为什么需要它？**
A：Oracle 是 AIOpsLab 提供的「标准裁判」——它不只看命令有没有执行成功，而是验证**业务可用性恢复 + 集群健康**（比如 scale 回来后 pod 真的 ready、targetPort 改对后服务真的通）。需要它是因为 agent 可能「命令执行成功但没真正修好」（比如重启了 pod 但根因没解决），只有 Oracle 级判定才算真修复。

---

## 第 7 章 agent 理解 + 系统设计题

> 考察维度：**agent 理解**。这一章是 agent infra 岗核心——编排选型、可观测、容错、成本延迟、多 agent、function calling、安全、评估。每题「问答 + 为什么考」。考的是**系统思维和权衡**，围绕自己项目把权衡讲透。

### 7.1 如果让你从零设计一个 AI Agent 编排框架，LangGraph（StateGraph）/ 纯 ReAct / CrewAI / AutoGen 你怎么选？权衡维度是什么？

**A：** 四步权衡：① **自主度需求**——任务路径是否可预见。SRE 排障流程相对固定（诊断→修复→回滚），决策点可枚举，适合「确定性编排 + 局部 LLM 决策」（CrewAI sequential / LangGraph StateGraph）；开放域研究（路径不可预见）才用纯 ReAct。② **可控性/可调试**——生产 agent 必须可观测、可限成本、可回滚；图结构本身就是 trace，条件边显式可单测；ReAct 自由循环难调试、易跑偏烧钱。③ **多角色协作**——任务能清晰拆给不同专长角色（诊断/修复/回滚）且并行收益大，用 CrewAI/AutoGen 多 agent；单流程闭环用图更轻。④ **生态运维**——checkpointing 断点续跑、human-in-the-loop。我项目选 CrewAI sequential 正是因为 SRE 要可控 + 可观测 + 可限成本 + 可回滚。

> 🎯 **为什么考**：考你懂不同编排范式的本质差异和选型依据，而不是只会一个框架。

### 7.2 生产级 Agent 的可观测性（observability）你怎么设计？观测哪些维度？

**A：** 五个维度：① **Trace**——每次请求一棵 span 树，每个 agent/工具/LLM 调用一个 span，记输入/输出/耗时/token/cost。② **LLM 层**——每次 LLM 调用的 prompt/completion token、模型名、延迟。③ **Agent 层**——决策路径、重试次数、自纠正触发率、工具调用成功率、回滚次数。④ **业务层**——Oracle pass rate、first-attempt success、幻觉/错误处置率。⑤ **系统层**——P50/P95/P99 延迟、错误率、限流、下游（Planner server/kubectl/API server）健康度。选型：2026 标准是 OpenTelemetry + GenAI Semantic Conventions（标准化 LLM/agent/MCP tool 埋点），后端接 LangSmith/Langfuse（调试）或 Datadog/Jaeger（生产）。关键：token 是 AI 算力基本单位，cost 和延迟都挂在 token 上，必须每 span 归因。我项目的 trajectory/reward 导出是雏形，生产接 OTel GenAI conventions。

> 🎯 **为什么考**：agent infra 岗核心日常。考你懂 trace/span、懂 GenAI 语义约定、懂 token 维度成本归因，而不是只会 print。

### 7.3 Agent 调用 LLM/工具会失败（超时、限流、非法 JSON、幻觉、dry-run 失败），容错与重试策略是什么？怎么避免重试风暴？

**A：** 分层防护：① **重试上限 + 兜底**——像 MAX_RETRIES，达上限强制兜底（可用性优先于质量），防死循环。② **退避**——对下游 API 用指数退避 + 抖动（exponential backoff + jitter），避免重试同步打爆下游。③ **熔断**——错误率超阈值熔断，fallback 降级（Planner server 挂了退 base 模型 / rerank 挂了用规则）。④ **解析容错**——LLM 返回非法 JSON 先剥 markdown 再解析，失败走保守降级（我项目 schema 校验失败直接拒，安全取向）。⑤ **幂等**——重试不改外部状态，靠 precondition/resourceVersion 防重复执行。⑥ **超时**——每个工具调用设超时。⑦ **死信队列**——彻底失败落 DLQ 人工处理。避免重试风暴的关键：**重试预算 + 退避 + 熔断**三件套。

> 🎯 **为什么考**：agent 失败模式比传统服务多得多（LLM 不确定性），考你有没有生产级容错思维。

### 7.4 Agent 系统的成本和延迟怎么优化？一次请求最坏调十几次 LLM，怎么控？

**A：** 先测量再优化。延迟：分阶段计时找 P95 瓶颈。优化：① **模型分级**——诊断/路由/校验用便宜小模型，只在关键生成用大模型；我项目用 QLoRA 7B Planner 就是为了把「生成修复计划」这个高频操作从大模型 API 降到可私有部署的小模型。② **批量化**——多次小判断合并成一次。③ **早停与预算**——MAX_RETRIES 限死；dry-run/precondition 不过直接终止不再往下。④ **缓存**——高频 query 的结果按 hash 缓存（注意 TTL 和权限隔离）。⑤ **路由前置**——能早判断的早判断省后续调用。⑥ **流式降首字延迟**。成本：识别长尾（5% 请求烧 50% token），长 context 截断/摘要。关键是「关键路径用强模型，辅助判断用小模型 + 缓存 + 预算」。

> 🎯 **为什么考**：最现实的工程约束。考你懂 LLM 调用是主要成本/延迟来源，且知道具体优化旋钮。

### 7.5 什么时候该用多 agent？多 agent 怎么通信避免混乱？单 agent vs 多 agent 各适用什么？

**A：** 用多 agent 的判据：① 任务能清晰拆成不同专长角色（诊断/修复/回滚）；② 各子任务可并行（并行收益大于通信开销）；③ 单 agent 上下文/工具太多导致 prompt 膨胀、注意力稀释。如果任务是线性闭环、决策点可枚举（像我项目），职责分工 + 串行编排更可控。多 agent 通信避免混乱：① 清晰的消息协议（结构化 message，不是自由文本）；② 共享黑板（shared state）或显式 handoff，而非网状自由对话；③ 每个 agent 职责单一、上下文隔离；④ 有 supervisor 做路由汇总；⑤ 限制轮次防发散。我项目是「多角色 agent + 确定性串行」（Diagnosis/Mitigation/Undo 分工，靠 sequential 编排和 shared state 传递），不是自由对话式多 agent。

> 🎯 **为什么考**：考你懂多 agent 不是银弹、懂通信复杂度，不会盲目堆架构。

### 7.6 Tool use / Function calling 原理是什么？Agent 怎么知道调哪个工具、传什么参数？和你项目怎么对应？

**A：** Function calling：把工具 schema（名字/描述/参数 JSON Schema）塞进 prompt，LLM 生成时可选输出一个结构化 tool_call（工具名+参数），**框架**解析后实际执行，结果作为 observation 喂回 LLM——这就是 ReAct 的 Thought-Action-Observation 循环，或 OpenAI function calling 原生实现。关键：**LLM 只输出意图，框架安全执行**。我项目对应：NL2Kubectl/NL2Traces/NL2Logs 这些就是工具，LLM 输出「查询意图」（自然语言），工具内部生成并执行 kubectl/PromQL；MitigationPlan 本身也可以看作一个「结构化工具调用」（plan 即 action 意图）。升级方向：把 kubectl 操作包成带 schema 的 native tool，让 agent 在权限边界内自主选——但要配 RBAC + 白名单兜底。

> 🎯 **为什么考**：function calling 是 agent infra 基石。考你懂原理（LLM 输出意图、框架执行）、懂安全边界、懂与项目的对应。

### 7.7 Agent 的安全与权限怎么保证？尤其 agent 能自主调工具/检索时，怎么防越权和危险操作？

**A：** 多层防御（这是本项目隔离设计的核心）：① **工具层 RBAC/ABAC**——拆 ReadOnly/Write 工具，Diagnosis 只发只读；高危操作（delete/drain/scale 到 0）分级，走 human-in-the-loop。② **代码层校验**——生成的命令/计划执行前过 schema + verb 白名单 + dry-run + 沙箱。③ **集群层 RBAC 兜底**——ServiceAccount 最小权限，Diagnosis 只授 get/list/watch，apiserver 层 403 硬墙（应用层绕不过）。④ **prompt injection 防护**——不可信输入（用户消息、检索文档、trace 日志）当 data 不当 instruction，delimiter 隔离。⑤ **审计**——每次工具调用、每次越权尝试落日志。⑥ **乐观并发兜底**——resourceVersion CAS 防 lost-update。SRE 特别：force delete / drain node 永远建议人执行。诚实讲：我项目目前主要靠①② + 串行，③④的硬墙是已识别要补的关键层。

> 🎯 **为什么考**：安全是红线。考你懂 tool-level/RBAC/prompt injection/human-in-the-loop/最小权限，而不是只会跑 demo。

### 7.8 怎么评估一个 agent 系统？离线 vs 在线？LLM-as-judge 有什么坑？

**A：** 分离线/在线：**离线**——固定测试集跑，统计 success rate / first-attempt success / TTM / steps / rollback（我项目用 AIOpsLab Oracle）；trajectory 回放做 bad case 分析。**在线**——采样跑 faithfulness/Oracle 通过率、工具成功率、P95 延迟，设基线告警。LLM-as-judge 的坑：① self-judge 偏松（裁判和生成器同模型）；② position/verbosity bias；③ 不可复现（temp=0 也有波动）；④ 裁判自身幻觉。提升：裁判用更强/不同家族模型、self-consistency 多次投票、rubric 细化、golden set 定期校准、关键场景人工复核。我项目用 Oracle（确定性裁判）而非纯 LLM-as-judge 评修复成功率，更可靠；reward 评估用了构造 reward + 可接 Oracle。

> 🎯 **为什么考**：考你懂 agent 评估的难点（无标准答案、轨迹长、部分可观察）、懂离线/在线、懂 LLM-as-judge 的坑。

---

## 第 8 章 编码能力题

> 考察维度：**编码能力**。agent infra 的编码题不是 leetcode，是 **agent 原语的实现与设计**。每题给思路 + 简短 Python 草图 + 加分点。面试时讲清思路比写全代码重要。

### 8.1 实现一个带 retry + 错误处理的 tool-use 循环

**思路**：ReAct 循环（thought→action→observation），带 max_iter 防死循环、指数退避 + 抖动重试、解析失败降级。

```python
def agent_loop(query, tools, llm, max_iter=10, max_retries=3):
    messages = [{"role": "user", "content": query}]
    for _ in range(max_iter):
        for attempt in range(max_retries):
            try:
                resp = llm(messages, tools=tool_schemas(tools))  # 可能抛超时/限流
                break
            except (Timeout, RateLimit) as e:
                if attempt == max_retries - 1: raise
                time.sleep((2**attempt) + random.random())      # 指数退避 + jitter
        if not resp.tool_calls: return resp.content             # 无工具调用=结束
        messages.append(resp)
        for call in resp.tool_calls:
            result = tools[call.name](**call.args)              # 框架执行，非 LLM
            messages.append({"role":"tool","tool_call_id":call.id,"content":str(result)})
    return "达到最大步数，兜底返回"
```
**加分点**：max_iter 防死循环、退避+抖动防重试风暴、LLM 只输出意图框架执行、解析失败兜底。

### 8.2 鲁棒解析 LLM 不可靠的 JSON 输出（如 MitigationPlan）

**思路**：四道防线——prompt 约束 → 剥 markdown → json_repair 容错 → Pydantic schema 校验失败则重试/拒绝。

```python
def parse_plan(raw: str, retry_llm=None):
    raw = strip_code_fence(raw)                  # 去掉 ```json 包裹
    try:
        data = json.loads(raw)
    except JSONDecodeError:
        data = json_repair.loads(raw)            # 容错修复残缺 JSON
    try:
        return MitigationPlan(**data)            # Pydantic 严格校验，extra=forbid
    except ValidationError:
        if retry_llm: return parse_plan(retry_llm("重新输出合法 JSON"), None)
        raise                                     # 安全取向：拒绝而非放行
```
**加分点**：structured output / response_format 优先于手写解析；校验失败 fail-closed（安全场景拒比放好）。

### 8.3 设计 agent 的上下文管理 / compaction

**思路**：长对话超 token 预算时，把早期消息摘要压缩，保留近期 + 关键事实。分层记忆：短期窗口 + 长期摘要 + 按需检索。
**加分点**：token 预算反推（top_k × chunk_size < 窗口 − 预留）；「lost in the middle」把重要的放开头尾；摘要触发条件（按 token 阈值或轮数）；压缩可能丢信息，关键事实单独存。运维场景：trace/log 量大要截断/摘要再进 context。

### 8.4 实现 tool 调用的限流 / 退避包装

**思路**：装饰器封装 tool，带 rate limiter（token bucket）+ 重试 + 熔断。

```python
def resilient(rate=10, burst=20):                # 10 req/s, burst 20
    limiter = TokenBucket(rate, burst)
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **kw):
            limiter.acquire()
            for attempt in range(3):
                try: return fn(*a, **kw)
                except RateLimit: time.sleep(2**attempt + random.random())
                except CircuitOpen: return fallback(*a, **kw)
            raise
        return wrap
    return deco
```
**加分点**：token bucket 限流、退避抖动、熔断降级、幂等（重试不改外部状态）。

### 8.5 设计一个幂等的 kubectl patch tool（precondition + resourceVersion CAS）

**思路**：patch 前带 JSON Patch `test` 前置条件 + apply 带 resourceVersion，冲突（409）重试，保证幂等。

```python
def safe_patch(kind, name, ns, ops, max_retry=3):
    for _ in range(max_retry):
        obj = kubectl_get(kind, name, ns)                    # 拿当前状态 + resourceVersion
        rv = obj["metadata"]["resourceVersion"]
        try:
            return kubectl_patch(kind, name, ns, ops, resource_version=rv)  # CAS
        except Conflict:                                     # 409 = 别人改了，重读重试
            continue
    raise
```
**加分点**：`test` op 前置条件（乐观断言）、resourceVersion CAS（乐观锁）、409 重试、幂等（重复执行结果一致）。

### 8.6 实现一个简单的 supervisor 多 agent fan-out

**思路**：supervisor 把任务拆给多个子 agent 并行，汇总结果。

```python
async def supervisor(task, sub_agents):
    subtasks = await planner.decompose(task)                 # 拆子任务
    async def run(sub):
        return await sub.run(subtask=subtasks[sub.name])
    results = await asyncio.gather(*[run(a) for a in sub_agents])
    return await planner.synthesize(task, results)           # 汇总
```
**加分点**：并行 gather、子 agent 上下文隔离、结构化 handoff（非自由对话）、限制并发数、部分失败处理（gather return_exceptions）。

---

## 第 9 章 AI / LLM 使用经验题

> 考察维度：**AI 使用**。考你「会不会用 LLM / AI 编码工具」的工程经验：输出不稳定、选模型、temperature、few-shot vs fine-tune、LLM-as-judge、长上下文、agentic coding 工作流。直接落到项目细节作答。

### 9.1 LLM 输出不稳定、不按格式返回（JSON 包在 ```json 里、字段缺失），你怎么处理？

**A：** 四道防线：① **prompt 约束**——明确「只返回 JSON，不要其他文字」+ 正反例。② **解析容错**——剥 markdown 代码块再 json.loads，失败用 json_repair 修复残缺 JSON。③ **保守降级**——解析失败不崩溃，安全场景 fail-closed（schema 校验失败拒，触发重试而非放行）。④ **结构化输出**——优先用原生 structured output / function calling / JSON mode（`response_format`）或 Pydantic schema，从机制上逼合法 JSON。我项目 MitigationPlan 用 Pydantic 严格校验就是这个思路。生产倾向：能用 structured output 就别靠 prompt + 手写解析。

### 9.2 怎么选模型？什么场景大模型、什么场景小模型？

**A：** 按任务难度和成本分级：① 简单判断（路由、相关性 yes/no、前置条件核对）——小模型（haiku/qwen-turbo/QLoRA 7B），快便宜够用。② 复杂生成（最终修复计划、根因诊断）——大模型（claude-sonnet/gpt-4o/qwen-plus），质量优先。③ 裁判——用比生成器更强或不同家族模型，降 self-judge 偏松。我项目用 QLoRA 微调 7B 做 Mitigation Planner，正是把「生成结构化修复计划」这个高频窄任务从大模型 API 降到可私有部署的小模型——成本、延迟、数据隐私都赢。选型还看：上下文窗口、function calling 支持、流式、价格、数据合规。

### 9.3 temperature 怎么设？

**A：** 看任务：要确定性的（schema 生成、grading、前置条件判断、可复现评估）用低/0；要多样性的（自然语言回答生成）0.3–0.7；创意类 0.7–1.0。我项目 Planner 做结构化输出倾向低温（要稳定遵循 schema）。注意：即使 temp=0，不同 provider/批次仍有微小非确定性，别说「100% 确定」。

### 9.4 Few-shot vs fine-tuning 怎么选？你项目为什么选 QLoRA fine-tune？

**A：** Few-shot 适用：格式难描述、迭代快、不锁模型版本。Fine-tune 适用：要极度稳定/低延迟、大量领域知识、示例太多撑爆上下文。我项目选 QLoRA 的原因：① schema 遵循要极度稳定（Base 模型 few-shot 后仍 0% schema 通过率）；② 私有部署不能调外部大模型 API；③ 三故障族是窄任务、570 条数据够训。如果任务格式简单、迭代频繁，few-shot 更轻。

### 9.5 LLM-as-judge 有哪些坑？怎么提升裁判可靠性？

**A：** 坑：① self-judge 偏松（同模型）；② position/verbosity bias；③ 判错（误杀/漏网）；④ 不可复现；⑤ 裁判自身幻觉。提升：裁判用更强/不同家族模型、self-consistency 投票、rubric 细化、golden set 校准、关键场景人工复核、声明级（claim-level）而非整段判断（粒度越细越准）。我项目评修复成功率用 Oracle（确定性裁判）比纯 LLM-as-judge 可靠；reward 评估用构造 reward + Oracle。

### 9.6 长上下文（long context）怎么管理？trace/log/k8s 状态塞不进去或注意力衰减怎么办？

**A：** ① **检索裁剪**——只把最相关的 top-k 塞进去（别无脑全塞）。② **重排置顶**——重要的放开头尾（lost in the middle）。③ **压缩/摘要**——长 trace/log 先摘要再塞，细节按需二次检索。④ **分层**——近期上下文 + 长期摘要 + 按需检索。⑤ **token 预算**——按窗口反推。运维场景特别：kubectl describe / logs 动辄很大，要截断/摘要/按相关性过滤后再进 context。注意：长上下文模型（128K/200K）≠「塞越多越好」，注意力衰减、成本线性涨、延迟增加。

### 9.7 你平时怎么用 Claude Code / Cursor 这类 AI 编码工具？怎么保证质量？（agentic coding 经验）

**A：** 我的 agentic coding 工作流：① **spec/plan 先行**——先让 AI 出方案、我审，再动手（不直接让它改代码）。② **context engineering**——把相关文件/规则/约束（CLAUDE.md、项目规范）放进上下文，无关的剔除，控制 context 噪声。③ **review 把关**——AI 生成后我逐段 review，重点看边界条件、错误处理、安全；跑测试验证而非盲信。④ **让 AI 别重犯错**——把踩过的坑写进规则文件/测试，下次自动约束。⑤ **什么时候不用**——安全敏感（鉴权/密钥/删数据）、不确定性高、需要领域深度判断时，自己写或深度 review。⑥ **成本/上下文纪律**——长任务及时清理上下文、用 subagent 隔离。核心观点：AI 是放大器——好的工程判断 + AI 高效，但「无监督放手」必出问题；关键是**人守住 review 和测试这两关**。

> 🎯 **为什么考**：2026 agent infra 岗越来越看重「会不会用 AI 工具做工程」，考的是成熟的工作流（spec-driven、context engineering、review 把关），而不是「我让 AI 写完了」。

---

## 第 10 章 场景项目实践深问

> 考察维度：**场景项目实践**。面试官只看简历、逐条追问。这一章把简历 4 条描述 + 整体 arc + 难点/失败 都覆盖。**诚实圆场贯穿**。

### 10.1 用 2 分钟讲清楚这个项目（overall arc）

**A：** 这是一个基于 STRATUS 的 Kubernetes 自愈多智能体系统，目标不是让 LLM 直接敲 kubectl，而是把修复约束成可审计、可回滚的结构化闭环。我做了完整原型链路：① 在 AIOpsLab 上采集三故障族（targetPort/scale=0/nodeSelector）的 live 修复轨迹；② 构造 570 条结构化 MitigationPlan 数据，QLoRA 微调 Qwen2.5-7B 做 Planner，schema 通过率 0→100%；③ 封装成在线 Planner 服务；④ 分层 gate 执行链——shadow 旁路推理 → dry-run 预演 → 沙箱 controlled execution（真 patch + postcondition + ActionStack 回滚），三故障族 3/3 通过；⑤ 用 LinUCB 在安全候选集上排序（offline 73.68% vs random 17%）；⑥ trajectory/reward 导出做评估。下一步是把 gate 接入 live AIOpsLab Oracle 做真正的 QLoRA-gated repair。

### 10.2 你简历第一条：为什么用多 agent 编排 Diagnosis/Mitigation/Undo？（对应 bullet 1）

**A：** 三个理由：① **职责与权限隔离**——诊断只读、修复写、回滚还原，分开缩小 blast radius；② **确定性控制流可观测可回滚**——每阶段产出结构化结果，可单测可审计，回滚逻辑确定化不依赖 LLM；③ **综合利用多种数据**——Diagnosis 融合 trace（Jaeger）+ 日志 + 集群状态定位根因，Mitigation 把诊断转成结构化计划用 NL2Kubectl 执行。代价是延迟高、链路长，但 SRE 场景安全优先于速度。

### 10.3 你简历写「按角色隔离只读观测与写操作权限」，具体怎么做的、为什么需要？（对应 bullet 1，**隔离高频题**）

**A：** **为什么需要**：① 本该只诊断的 agent 能改集群，blast radius 不可控；② 多 agent 并发写同一资源会冲突，需要写互斥；③ 职责单一便于审计回滚。**怎么做的**：角色分工（Diagnosis 读 / Mitigation 写 / Undo 回滚）+ 工具按角色分发 + CrewAI sequential 串行编排避免并发 + 写操作过白名单/dry-run/前置条件闸门。**诚实讲边界**：理想的硬隔离应 tool-level（ReadOnly vs Write 工具）+ K8s RBAC（只读 ServiceAccount 物理兜底）+ 分布式资源锁（K8s Lease + resourceVersion CAS），这些是我明确的下一步。Prompt-level 的「你只能读」不是真权限，需要 RBAC 硬墙兜底——这是 agent infra 必须懂的 defense-in-depth。

### 10.4 你简历第二条：最小变更约束、前置后置条件、自动回滚怎么保证安全？（对应 bullet 2）

**A：** **最小变更**：把修复约束成 JSON Patch（RFC 6902），只改必要字段，不整资源覆盖。**前置条件**：JSON Patch `test` op——执行前确认状态符合预期（如 `/spec/replicas == 0` 才 scale），避免误改已正常的资源。**后置条件**：patch 后校验状态符合预期（`/spec/replicas == 1`），验证修复生效。**dry-run**：`--dry-run=server` 让 API server 预演不真改，提前抓 schema/权限/前置错误。**ActionStack 回滚**：动手前存 before 快照，postcondition 不过或更糟就按 inverse patch 还原（declarative reconciliation）。**安全重试与终止**：重试有预算，到上限终止兜底。诚实讲：这套在沙箱三故障族 3/3 验证；snapshot 回滚只还原 K8s 资源状态、不还原外部副作用，这是论文 §4 承认 perfect undo 难的边界，生产要加 compensation。

### 10.5 你简历第三条：故障注入→负载回放→执行→复位→指标这条 pipeline 怎么串的？Oracle 是什么？（对应 bullet 3）

**A：** 基于 Kind + AIOpsLab + DeathStarBench 微服务场景：① **故障注入**——AIOpsLab 注入三故障族（targetPort 改错 / scale 到 0 / nodeSelector 指向不存在节点）；② **负载回放**——跑 workload 模拟真实流量；③ **agent 执行**——Diagnosis→Mitigation→Undo 跑修复；④ **环境复位**——每个 episode 后复位集群；⑤ **指标汇总**——统一记录工具调用、k8s 资源 diff、回滚动作、Oracle 结果，形成可追溯 trajectory。**Oracle**：AIOpsLab 的标准裁判，不只看命令执行成功，而是验证业务可用性恢复 + 集群健康（pod ready、服务真的通），只有 Oracle pass 才算真修复。诚实讲：完整 Oracle 端到端主要在沙箱三故障族验证，live 接入是下一步。

### 10.6 你简历第四条：QLoRA Planner 相比直接用大模型有什么优势？怎么训的？100% 怎么理解？（对应 bullet 4，**高频深挖**）

**A：** **优势**：① 成本延迟——在线每次修复都调大模型 API 贵且慢，QLoRA 7B 可私有部署；② 数据隐私——运维故障数据不能发外部；③ 可控——小模型微调后行为更可预测。**怎么训**：基于 live verified 轨迹 + 参数化扩增构造 570 条 MitigationPlan 数据（SFT/Tool-Calling/preference），4-bit QLoRA 微调 Qwen2.5-7B（LoRA 低秩增量 + NF4 量化，adapter 仅 155MB），train/val/test=462/53/55。**100% 的诚实边界**：这是**离线测试集**的 schema 通过率（0→100%）和字段准确率（fault_type/operation/resource/patch_path/patch_value/risk 均 100%），证明 QLoRA 让小模型学会了三故障族的结构化工单格式和关键参数；**不等于 live 端到端修复成功率**。数据集多为模板扩增、不等于额外真实 episode。live 成功率要接 Oracle 才统计。

### 10.7 你简历第四条：为什么用 LinUCB？候选集和 reward 怎么设计？73.68% 怎么解读？（对应 bullet 4）

**A：** **为什么 LinUCB**：样本效率高（小样本能学、支持 offline replay）、安全可约束（先静态踢掉 delete 等不安全候选，bandit 只在安全集里选，unsafe=0）、可解释（权重/UCB 可解释）。**候选集**：每个 canonical plan 合成一组安全候选——正确 patch（+1.0）/ 缺前置条件（+0.45）/ 错误值（-0.8）/ 重启诱饵（0）/ merge 诱饵（-0.25）/ delete（-1.0，被 safety 拦截不进池）。**reward**：Oracle 终态 + 执行成本 + 回滚惩罚，引导「修对 + 少折腾 + 别改错」。**73.68% 的诚实边界**：这是 **offline hard-mode replay**（在生成候选集上回放），LinUCB 显著优于 random（17%）和 min-risk（34%）；**不是 online bandit**，reward 是构造的不是 live 反馈。online 更新 + live reward 是下一步。

### 10.8 这个项目最大的技术挑战是什么？系统失败过吗，你学到了什么？

**A：** 最大的挑战是**在「让 LLM 自主」和「保证安全可回滚」之间找平衡**——LLM 生成自由命令不可审不可回滚，直接上线风险太高。我的解法是把 LLM 输出约束成结构化 MitigationPlan + 分层 gate 逐步放大风险。**失败/教训**：早期发现「prompt 告诉 agent 只读」根本不是权限隔离——agent 照样可能生成写命令，这让我意识到必须 defense-in-depth（tool-level + RBAC 硬墙 + 分布式锁），prompt 只是第一道建议性防线。另一个教训是离线指标（schema 100%）容易给人虚假信心，必须用 Oracle 级端到端验证才算真成功。这些教训让我把「诚实标注边界 + 给改进路线」当成工程习惯。

---

## 第 11 章 面试整体策略 + 雷区清单速查

### 一、最重要的心态：诚实 + 会抽象 + 主动讲权衡 = 有深度

你有一个**真实跑通的原型**。面试官不在乎你是不是大牛，在乎你**懂不懂原理和权衡**。两个致命错误：① 不懂装懂被追问穿帮；② 懂一点但讲不出「为什么这么选、代价是什么」。

正确姿势是**「诚实讲事实 + 主动讲权衡 + 主动讲改进点」**。例：
- 别说「我有完整的分布式读写锁」（没完整落地）→ 说「隔离靠 sequential 串行 + 白名单 + dry-run，论文的 A-Lock 和分布式锁是已识别的下一步，落地路线是 RBAC + K8s Lease + resourceVersion CAS」。后者反而显深度。
- 别说「微调后修复成功率 100%」→ 说「100% 是离线 schema/字段准确率，证明小模型学会结构化格式，不等于 live 端到端成功率」。

**主动指出局限 + 给改进方向 = agent infra 岗最加分的品质**——这个岗位招的就是能发现并修复 agent 系统问题的人。

### 二、简历雷区怎么圆（核心：机制真实 + 主动标边界）

| 风险点（简历措辞） | 怎么圆（诚实讲法） |
|---|---|
| 🚨「按角色隔离只读与写权限」 | 靠 sequential 串行 + 工具分发 + 白名单 + dry-run 约束；论文 A-Lock 读写锁/分布式锁未完整落地。下一步：拆 ReadOnly/Write 工具 + 只读 ServiceAccount（RBAC 兜底）+ K8s Lease + resourceVersion CAS。prompt 不是权限系统，要 defense-in-depth。 |
| 🚨「高风险操作拦截」 | 实现了 verb 白名单 + 命令形状校验 + server dry-run 三道 gate；拦截默认可配、生产应 default-on；硬墙应下沉到 K8s RBAC/AdmissionPolicy。 |
| 🚨 QLoRA「100%」 | 离线测试集 schema 通过率 0→100% + 字段准确率 100%，证明学会结构化工单格式；**不等于 live 端到端成功率**。数据集多为模板扩增，非额外真实 episode。 |
| 🚨「端到端闭环验证」 | 完整原型链路跑通（离线→QLoRA→服务→shadow→dry-run→沙箱 controlled execution）；controlled execution 三故障族沙箱 3/3；**live AIOpsLab Oracle 接管是下一步**。 |
| 🚨 LinUCB「73.68%」+「构造奖励」 | offline hard-mode replay 结果（vs random 17%/min-risk 34%，unsafe=0）；**不是 online bandit**；reward 用 Oracle 终态+成本+回滚惩罚**构造**，非 live 反馈。online 更新+live reward 是下一步。 |
| 🚨「自动回滚」 | 沙箱验证了 ActionStack 快照 + inverse patch 回滚（3/3）；snapshot 回滚只还原 K8s 资源状态，**不还原外部副作用/不可逆操作**（论文 §4 承认 perfect undo 难）；生产要 compensation + 不可逆操作执行前拒绝。 |
| 🚨「以终态 Oracle 构造奖励」 | reward 框架已搭好并落盘三种 reward（planning proxy/dry-run gate/controlled execution）；**真实 live Oracle reward 未接在线学习闭环**。 |

### 三、Agent Infra 岗最看重什么（按优先级）

① **系统思维**（编排选型/可观测/容错/成本延迟的权衡，而非只会调 API）② **工程诚实**（懂边界、懂局限、懂改进点）③ **Agent 原理**（确定性编排 vs ReAct、function calling、LLM-as-judge 的坑、隔离与权限）④ **生产化意识**（trace/token 归因/重试预算/熔断/降级/安全 ACL/RBAC）⑤ 具体框架经验（CrewAI/QLoRA/LinUCB）。

面试官宁可要「把自己项目原理讲得极透、懂所有权衡」的人，也不要「简历堆满大词但讲不清为什么」的人。

### 四、面试前突击清单

**必背的数字**（答不上来露馅）：
- 三故障族：service_target_port_mismatch / deployment_scaled_to_zero / deployment_nodeSelector_nonexistent_node
- 数据：570 条（SFT/Tool-Calling/preference 各 570），train/val/test=462/53/55
- QLoRA：Qwen2.5-7B-Instruct，4-bit NF4，adapter ~155MB，train loss 0.057 / eval loss 0.011
- 离线：Base schema 0% → QLoRA schema 100%、字段准确率 100%、unsafe 0
- LinUCB：22 维特征，hard-mode LinUCB 73.68% vs random 17.04% vs min-risk 33.56%，unsafe 0
- 沙箱 controlled execution：三故障族 3/3（patch/postcondition/rollback）
- shadow replay：9 条 live episode，server/schema/静态安全/agreement 9/9

**必会的 3 个比喻**（讲深度的杀手锏）：
- 结构化 MitigationPlan = 标准手术工单（可审/可校验/可回滚）vs 直接生成命令 = 黑盒
- 分层 gate = 火箭发射分级倒计时（shadow→dry-run→controlled execution，风险逐步放大）
- ActionStack 回滚 = 装修前拍照、装砸了按照片还原

**必准备的 3 个「主动讲局限」**：
- read-only 没被强制（靠串行+白名单+dry-run，RBAC 硬墙是下一步）
- 100% 是离线 schema 指标（不等于 live 成功率）
- controlled execution 只在沙箱（live Oracle 接管是下一步）

**最后一条**：面试是双向交流不是考试。遇到不会的，说「这块我没深入研究过，但基于我对 X 的理解，我猜大概是 Y，回去查 Z 确认」——比硬编强一万倍。agent infra 岗要能持续学习的人，不是全知的人。

---

## 附录 A 一页速查表

### A.1 项目一句话定位
基于 STRATUS 的 K8s 自愈多智能体系统；把 LLM 输出约束成结构化 MitigationPlan，过分层 gate（shadow→dry-run→controlled execution）+ ActionStack 回滚，形成可审计/可校验/可回滚闭环。QLoRA 微调 7B Planner，LinUCB 排序安全候选。

### A.2 三角色 + 动作分类
| 角色 | 动作 | 职责 |
|---|---|---|
| Detection/Diagnosis | Aread（只读） | trace/log/集群状态定位根因 |
| Mitigation | Awrite + Aread | 结构化 MitigationPlan → kubectl 写 |
| Undo | Aundo | 按 ActionStack 快照回滚 |

### A.3 分层 Gate 执行链
| 阶段 | 做什么 | 风险 |
|---|---|---|
| shadow replay | 旁路推理，只校验不执行 | 零 |
| dry-run gate | kubectl --dry-run=server 预演 | 零持久化（webhook 副作用除外） |
| controlled execution | 真 patch + postcondition + ActionStack 回滚 | 真改，但有快照回滚兜底 |

### A.4 关键公式/原理
```text
LoRA:   W = W₀ + ΔW = W₀ + B·A      （冻结原权重，只训低秩增量 A∈r×d, B∈d×r）
QLoRA:  W₀ 4-bit NF4 量化, LoRA 增量 bf16 高精度训练  → 7B ~3.5GB 可训, adapter ~155MB
LinUCB: UCB = θᵀx + α·√(xᵀA⁻¹x)    （exploit + explore；先静态踢掉不安全候选，unsafe=0）
JSON Patch:  test(前置条件) → replace/add/remove(变更) → inverse patch(回滚)
OCC兜底:     resourceVersion CAS, apply 带版本号, 冲突 409 重试
```

### A.5 诚实边界速查（被追问大方承认 + 给路线）
| 指标/说法 | 真实边界 |
|---|---|
| schema 100% | 离线 schema/字段准确率，非 live 端到端成功率 |
| 73.68% | offline hard-mode replay，非 online bandit |
| read-only 隔离 | 靠串行+白名单+dry-run，RBAC 硬墙+A-Lock 是下一步 |
| 端到端闭环 | controlled execution 沙箱 3/3，live Oracle 接管是下一步 |
| 自动回滚 | 沙箱验证；snapshot 不还原外部副作用，需 compensation |
| 构造奖励 | reward 框架落盘，live Oracle reward 未接在线闭环 |

### A.6 隔离与权限 defense-in-depth（高频题，背熟）
1. **工具层**：拆 ReadOnly/Write 工具，Diagnosis 只发只读。
2. **代码层**：verb 白名单 + 命令形状校验 + dry-run + 前置条件。
3. **集群层 RBAC**：只读 ServiceAccount（get/list/watch），apiserver 403 硬墙。
4. **并发**：K8s Lease（resource-scoped key + TTL）+ resourceVersion CAS。
5. **prompt injection**：不可信输入当 data 不当 instruction。
6. **审计 + 最小权限 + human-in-the-loop**（高危操作）。

**口径**：「prompt 不是权限系统；隔离要 tool-level + RBAC 硬墙 + 分布式锁 defense-in-depth；当前主要靠①②+串行，③④是已识别的下一步。」
