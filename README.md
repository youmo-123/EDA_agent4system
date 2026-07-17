# DoorAgent EDA

> 一个把"设计一颗数字芯片"这条流水线，用四个 AI Agent 自动串起来的工程化运行工具。

---

## 一、先把基础名词讲清楚

如果你从没做过芯片设计，本节把 README 后面会反复出现的术语一次讲透，
之后就不再解释。

### 1. 芯片是怎么被"写"出来的

一颗数字芯片（CPU、GPU、加速器、控制器 …）最终物理上是一堆"晶体管 +
金属连线"，但工程师并不是直接画晶体管，而是像写程序一样把电路"描述"
出来，交给一整套软件工具自动往下翻译。

从人写的代码到能流片的物理版图，大致要走这几层：

```
硬件功能想法（架构规格 / 协议文档）
      │
      ▼
┌────────────────────────────────────────────────────────┐
│ RTL 代码 (Register-Transfer Level)                     │  ←── 人写的代码（本工具的输入）
│   ・SystemVerilog / Verilog / VHDL                     │
│   ・"每个时钟沿寄存器怎么更新、信号怎么组合"           │
│   ・示例：`always @(posedge clk) q <= d;`              │
└────────────────────────────────────────────────────────┘
      │
      ▼   ← 「验证 Verification」在这里发生：证明代码符合规格
┌────────────────────────────────────────────────────────┐
│ 逻辑综合 (Logic Synthesis)                             │
│   ・工具：Yosys / DesignCompiler / Genus …             │
│   ・把 RTL 翻译成"门级网表 Netlist"                    │
│   ・网表 = AND / OR / NAND / DFF … 这些基本单元的连接  │
└────────────────────────────────────────────────────────┘
      │
      ▼
┌────────────────────────────────────────────────────────┐
│ 工艺映射 (Technology Mapping) + STA (静态时序分析)      │
│   ・工具：ABC + OpenSTA / PrimeTime …                  │
│   ・把抽象门映射到具体工艺库 (Nangate45 / TSMC N7 …)   │
│   ・算出 Area 面积 / Timing 时序 / Power 功耗          │
└────────────────────────────────────────────────────────┘
      │
      ▼
   物理实现（Place & Route）→ Tape-out（流片）
```

本工具聚焦在中间三层（RTL 编写完成 → 验证 → 综合 → PPA 优化 → 回归），
不涉及物理实现和流片。

### 2. 这些术语分别是什么

| 术语 | 含义 | 类比 |
|---|---|---|
| **RTL** (Register-Transfer Level) | 一种硬件描述抽象层，写"每个时钟节拍寄存器如何转移" | 相当于软件世界的"源代码" |
| **SystemVerilog / Verilog** | 写 RTL 用的语言（`.sv` / `.v` 文件） | 相当于 C / Rust |
| **TOP** | 一颗设计的最顶层模块名 | 相当于 `main()` 函数 |
| **SDC** (Synopsys Design Constraints) | 约束文件：告诉工具"时钟多快、输入到得多晚" | 相当于编译时的 `-O2 -march=…` |
| **Testbench (TB)** | 用来喂激励、抓输出、比对结果的验证环境 | 相当于单元测试 harness |
| **Coverage** | "验证做得够不够充分"的量化指标 | 相当于代码覆盖率，但更细：line / branch / functional / cross |
| **Assertion** | 断言：形式化写下"这个信号什么时候必须成立" | 相当于 `assert(inv)` |
| **Netlist** | 综合后的门级网表 (`.v` 但只由 cell 组成) | 相当于汇编 / IR |
| **Liberty (.lib)** | 工艺库：描述每个 cell 的面积、时延、功耗 | 相当于 CPU 指令表 |
| **STA** (Static Timing Analysis) | 静态时序分析：算最坏路径能不能满足时钟周期 | 相当于最坏情况分析 |
| **Slack** | 时序余量：正=够快，负=违反时序 | 相当于"距离 deadline 还有多久" |
| **PPA** | Power / Performance / Area 三大目标 | 就是"更快、更省、更小" |
| **Pareto** | 多目标权衡时的非支配前沿 | 面积和时序不可能同时最好，只能选前沿 |
| **EDA** (Electronic Design Automation) | 上面这些工具的统称 | 相当于"编译器 + 测试框架 + Profiler + 打包器"合集 |

### 3. 为什么这件事需要"一个工具产品"

上面每一步都是独立的开源/商业软件（Yosys、ABC、OpenSTA、cocotb、Z3、VCS、URG …），
它们的输入输出格式各不相同、命令行各写一套、失败信号也不统一。工程师日常要做的事：

- 改一版 RTL → 手动跑一遍验证 → 看覆盖率 → 手动补测试用例
- 再跑一遍综合 → 看 STA 报告 → 觉得时序不够 → 回去改 RTL
- 回来又要重跑验证保证没改坏 → 重跑综合看新 PPA
- 有 3 个候选改法就要开 3 个目录、3 套脚本、3 份报告

**DoorAgent EDA 做的事，就是把这条串起来一次全跑完，并且用 4 个 AI Agent
分别监控/推动其中每一段，让它可以在同一个 RTL 版本身份下自动多轮迭代、
自动回归、自动生成联合报告。**

---

## 二、DoorAgent EDA 是什么

**一句话：给它一份 RTL 和目标，它自动跑完"验证 → 覆盖收敛 → 综合 → PPA
优化 → 候选回归 → 报告归档"的完整链路，并保证每一步都有可复现证据。**

### 2.1 输入

```jsonc
{
  "rtl": {"files": ["inputs/rtl/design.sv"], "top": "top"},
  "constraints": "inputs/constraints/dooragent.json",   // SDC 之类
  "objectives": ["verification", "simulation-analysis", "ppa-optimization"],
  "budget": {                                            // 预算与并发上限
    "wall_time_s": 7200,
    "max_parallel_a3_evaluations": 2,
    "a3_cpu_budget": 4, "a3_memory_mb": 8192
  }
}
```

### 2.2 会自动跑的链路

```
RTL 登记与版本冻结（绑定 rtl_version_id，禁止版本混用）
  → A2: 分析 RTL 接口，生成验证环境 / 测试激励 / 断言 / 覆盖模型
  → A1: 编译 + 仿真 A2 给出的验证资产，采集仿真证据
  → A2: 用真实覆盖后端（VCS/URG + cocotb …）算出 line/branch/functional 覆盖率
  → A2: 覆盖 gap 分析，选下一策略（约束求解 / 定向 / 变异 / 请求资料）并补测
  → A3: 用 Yosys+ABC+OpenSTA 综合 → 得到 netlist + Area/Arrival/Slack
  → A3: 维护二维 Pareto 前沿；定位面积/时序热点；给出结构化 RTL 优化建议
  → Master: 把候选 patch 物化成派生 RTL 版本，A1 用 A2 既有验证资产做回归
  → 回归通过 → A3 复评 PPA；回归失败 → Master 把结构化反馈回 A3 让它改
  → Master: 最终接受 / 回滚 / 继续迭代；生成联合报告与 artifact 清单
```

节点允许**并行、回环、跳过、多轮重复**；不是一段写死顺序的脚本，是一张
带 Gate/Hook 护栏的状态图。

### 2.3 四个 Agent 的分工

对外只有一个入口 `dooragent`；内部是四个身份，各自有明确边界。

| Agent | 类比软件世界 | 具体职责 |
|---|---|---|
| **Master** | 项目经理 + CI 调度器 | 监督整个联合工作流：调度、Gate/Hook、Workspace、Artifact 校验、单写者串行化发布最终报告。**不产生任何 EDA 业务证据**。 |
| **A1 · Simulation Analysis** | 测试执行器 + Profiler | 编译、事件驱动仿真、独立功能门禁、Profile/Trace、诊断计数、覆盖热点与仿真瓶颈分析。**不算 A2 正式覆盖率、不生成 A2 测试**。 |
| **A2 · Verification Generation** | 测试用例生成器 + 覆盖率工程师 | RTL 接口分析、Testbench 骨架、覆盖模型、约束/测试生成、覆盖 gap 分析、失败最小化、断言推导。**正式 line/branch/functional 覆盖率的唯一真源**。 |
| **A3 · PPA Optimization** | 编译器优化师 + 性能工程师 | 综合（Yosys+ABC）、STA（OpenSTA）、可选门级预检（Icarus）、Strategy Catalog 搜索、Pareto 前沿维护、热点回溯、RTL 优化建议、候选复评。 |

> **关于 A1 内核**：A1 的 RTL 编译/事件驱动仿真内核为自研，目前仍在参赛
> 使用中，暂不开源。仓库内 [`scripts/a1/core/mock_simulator.py`](scripts/a1/core/mock_simulator.py)
> 只是一个契约级 Mock，用于让上游控制面、Manifest 绑定与 Artifact 契约
> 端到端跑通，不产生真实 EDA 结论。生产环境可以选：
>
> - **接入自研内核**：设置 `DOORAGENT_A1_SIMULATOR_BIN`，Runner 会通过参数
>   数组式 subprocess 调用它；接口与 Mock 一致
> - **替换为开源方案**：例如 Icarus Verilog (`iverilog`+`vvp`) 或 Verilator
>   作为默认后端，通过修改 [`configs/tool-manifests/a1/a1_compile.toml`](configs/tool-manifests/a1/a1_compile.toml)
>   与 [`configs/tool-manifests/a1/a1_simulate.toml`](configs/tool-manifests/a1/a1_simulate.toml)
>   的 `entrypoint` 指向对应包装脚本即可；上层 A1 Agent / Facade / Skill /
>   Prompt 全部无需改动
>
> 换句话说：Agent 决策层和 EDA 内核层是通过 Tool Manifest + 稳定 Schema
> 解耦的，A1 内核是否开源不影响整个产品的可运行性。

### 2.4 关键边界（区别于把 Agent 当"胶水"用的做法）

- **Agent 不直接互调**：跨 Agent 请求一律经过 Master + 只读且带 hash 的 Artifact；A2 不能读 A1 的 Workspace，反之亦然
- **Master 不做 EDA 计算**：它只做控制面动作（Workspace / 调度 / Gate / Hook / 校验 / 发布），保证任何 EDA 结论都必须来自真实工具运行的证据
- **相对路径**：所有持久化路径必须相对 `product_run_root` 或 `workspace_root`；禁止绝对路径、`..` 越根、Windows 盘符、未受控 symlink（这样整个 `runs/<workflow>/` 目录可以移到别的机器上恢复）
- **外部工具不打包不分发**：Yosys / ABC / OpenSTA / Icarus / PyVerilog / Z3 / cocotb / VCS / URG 都通过 Tool Manifest 声明版本与许可证；工具缺失时对应能力显式返回 `UNAVAILABLE / TOOL_NOT_IMPLEMENTED`，**绝不允许伪造成功报告**
- **模型密钥来自环境变量**：Provider / API Key / Base URL 通过 `ModelSettings.from_env` 加载，任何时候不会落到 Prompt / TOML / JSON / Workspace / 事件 / 日志中；日志与异常经 `secret_redactor` 三层脱敏（环境变量值 / `Authorization` header / `Bearer <token>`）
- **A3 第一版默认 `search_mode="catalog"`**（Strategy Catalog + 2D Pareto，可解释可复现）；进化搜索是可选插件，无改进/工具不可用时自动 `fallback_triggered=true`
- **每个 Artifact 都必须绑定**：`workflow_id / workflow_round_id / rtl_version_id / producer_agent_instance_id / schema_version / artifact_hash / created_at`；候选回归产物还必须绑定 `candidate_id / parent_rtl_version_id / candidate_rtl_version_id / candidate_hash`

完整设计（Facade 契约、状态机、Gate/Hook、Workspace/文件系统事务、
Backend Profile / Strategy Catalog / Artifact Manifest 等）见
[`DoorAgent-EDA-Multi-Agent-产品化方案.md`](DoorAgent-EDA-Multi-Agent-产品化方案.md)。

---

## 三、工程目录

```
ChipGenie/
├── configs/                          # 部署 / 后端 / 工具 / 算法配置（TOML）
│   ├── default.toml                  # 全局默认（预算、路径、日志、文件系统策略）
│   ├── agents.toml                   # 四个 Agent 的 Prompt / Skill / 允许 Tool
│   ├── resources.toml                # Resource Lease Scheduler 池化上限
│   ├── tools.toml                    # Tool Registry 装配
│   ├── algorithms/
│   │   ├── a3-toolchain.toml         # Backend Profile 与 Technology Library
│   │   ├── a3-strategies.toml        # A3 Strategy Catalog（稳定 strategy_id）
│   │   └── a3-search.toml            # 默认 catalog；evolutionary 可选
│   └── tool-manifests/               # 39 个 Tool Manifest（每个 Tool 一份）
│       ├── master/  (7)              # master_schedule_task 等控制面 Tool
│       ├── a1/      (9)              # a1_compile / a1_simulate 等
│       ├── a2/      (12)             # a2_run / a2_coverage_gap_analyzer 等
│       └── a3/      (11)             # a3_synth_tool / a3_evolutionary_search 等
│
├── dooragent/                        # 运行时 Python 包（对外唯一入口）
│   ├── __init__.py
│   ├── cli.py                        # dooragent run / resume / status / cancel
│   ├── bootstrap.py                  # 组装 orchestration + tooling + agents + facade
│   ├── errors.py                     # 统一错误码枚举（INVALID_REQUEST 等）
│   ├── utils.py                      # 通用工具（保留兼容）
│   │
│   ├── agents/                       # 四个 Agent 的推理与门面（唯一 Agent 层）
│   │   ├── base.py                   # BaseAgent 推理循环 + AgentContext
│   │   ├── contracts.py              # AgentTask / AgentResult / ArtifactRef
│   │   ├── master/                   # Master：agent / facade / context / policy /
│   │   │                             #         evidence（Artifact 校验）/ retention
│   │   ├── a1/                       # A1：agent / facade / context / policy
│   │   ├── a2/                       # A2：含 a2_strategy_selector builtin
│   │   └── a3/                       # A3：Strategy 选择 + evolutionary fallback 判据
│   │
│   ├── orchestration/                # 确定性控制面（Master 通过受控 Tool 调用）
│   │   ├── runtime.py                # OrchestrationRuntime（workflow_id → controller）
│   │   ├── workflow.py               # WorkflowController（bootstrap/status/cancel）
│   │   ├── scheduler.py              # Task 调度 + master_schedule_task builtin
│   │   ├── case_queue.py             # Master Case Queue（优先级 + 并发 claim）
│   │   ├── state_store.py            # CAS 状态 + 追加不可变 transition + 幂等
│   │   ├── exchange.py               # 按内容 hash 存储 blob + exchange manifest
│   │   ├── gates.py                  # Gate 1（新轮次）+ Gate 2（长线程）状态机
│   │   ├── hooks.py                  # Hook 注册 / 触发 / cooldown / escalate
│   │   ├── leases.py                 # Resource Lease Scheduler（池化 + 过期回收）
│   │   ├── sessions.py               # Agent Session 注册（attempt/iteration）
│   │   └── recovery.py               # 清理 .partial / 恢复 stale claim / 重建状态
│   │
│   ├── tooling/                      # 通用 Tool 调用框架
│   │   ├── registry.py               # Tool ID → Manifest → Runner/Adapter 路由
│   │   ├── manifest.py               # TOML manifest 加载与校验
│   │   ├── runner.py                 # subprocess Runner（超时 / 取消 / 白名单 env）
│   │   ├── adapter.py                # BaseAdapter + MockAdapter
│   │   ├── health.py                 # DECLARED_NOT_BOUND → BOUND_UNVERIFIED → HEALTHY
│   │   └── result.py                 # ToolResult / ToolStatus / 退出码映射
│   │
│   ├── runtime/                      # 运行时基础设施
│   │   ├── model_config.py           # ModelSettings.from_env（openai / mock provider）
│   │   ├── model_client.py           # ModelClient 统一模型调用入口 + health
│   │   ├── secret_redactor.py        # 环境变量 / Bearer / Header 三层脱敏
│   │   └── paths.py                  # ensure_relative_posix / resolve_under
│   │
│   ├── workspace/                    # Workspace 创建与生命周期
│   │   └── manager.py                # Primary / Child Service / A3 Candidate
│   │
│   ├── events/                       # 事件信封与文件消息通道
│   │   ├── envelope.py               # Event + 路由矩阵硬校验（A→A 禁止直发）
│   │   └── bus.py                    # write .partial → fsync → atomic rename
│   │
│   └── reports/                      # Prompt / Skill 加载与最终报告
│       └── loader.py                 # PromptLoader / SkillLoader（YAML front-matter）
│
├── scripts/                          # 各角色可独立执行的确定性脚本
│   ├── common/                       # 所有 script 共享
│   │   ├── atomic_io.py              # write_json_atomic（原子写 JSON）
│   │   ├── command.py                # 参数数组式 subprocess（禁止 Shell 拼接）
│   │   ├── schema_io.py              # jsonschema Draft 2020-12 校验
│   │   ├── artifact_io.py            # sha256 / now_iso / build_artifact_ref
│   │   └── script_cli.py             # 统一 CLI 骨架 + 退出码语义
│   │
│   ├── master/                       # 6 个控制面脚本（不做 EDA）
│   │   ├── create_workspace.py       # Primary / Child / A3 candidate Workspace
│   │   ├── render_prompt.py          # 按角色/Skill 渲染 Prompt（含脱敏）
│   │   ├── materialize_exchange.py   # 校验 + 原子发布 exchange manifest
│   │   ├── verify_artifacts.py       # 校验 producer / hash / 相对路径 / 绑定字段
│   │   ├── archive_round.py          # 冻结轮次 + archive manifest
│   │   └── publish_outputs.py        # 单写者发布 + STALE_RTL_VERSION 拒发旧版本
│   │
│   ├── a1/                           # 8 个 A1 脚本（仿真 / 分析 / 诊断）
│   │   ├── core/mock_simulator.py    # Mock 编译/仿真内核（部署时替换为真实内核）
│   │   ├── compile.py                # a1_compile      — RTL 编译
│   │   ├── simulate.py               # a1_simulate     — 事件驱动仿真
│   │   ├── coverage.py               # a1_diagnostic_coverage（明示非 A2 正式覆盖率）
│   │   ├── profile.py                # a1_profile_metrics — 事件/delta/耗时/内存
│   │   ├── trace.py                  # a1_trace_export  — VCD / FST / event trace
│   │   ├── source_map.py             # a1_source_map    — 内部对象 ↔ RTL 位置
│   │   └── analysis/
│   │       ├── bottleneck.py         # 从 profile+trace 定位仿真瓶颈
│   │       └── coverage_hotspot.py   # 把诊断计数映射回 RTL 区域
│   │
│   ├── a2/                           # 13 子脚本 + run.py / run.sh 编排器
│   │   ├── interface.py              # PyVerilog 优先 + 轻量正则回退 → design.json
│   │   ├── skeleton.py               # driver / monitor / scoreboard 骨架
│   │   ├── coverage/
│   │   │   ├── model.py              # bins / crosses / completion_goals + model_hash
│   │   │   ├── functional.py         # 功能 bin 聚合（hits / total / uncovered）
│   │   │   ├── structural.py         # line / branch 归一化
│   │   │   └── gap.py                # gap 分析 + 下一策略选择
│   │   ├── constraints.py            # z3 优先 + Python 回退
│   │   ├── tests.py                  # 固定 seed PRNG 生成确定性测试序列
│   │   ├── simulation.py             # 通过配置后端（mock / cocotb / vcs）采集
│   │   ├── reports.py                # coverage-result + run-report
│   │   ├── validate.py               # 校验 Artifact Manifest / hash / 相对路径
│   │   ├── failure/minimize.py       # delta-debugging 最小化失败用例
│   │   ├── assertions.py             # handshake / reset 断言候选
│   │   ├── run.py                    # 9 阶段编排 → artifact-manifest.json
│   │   └── run.sh                    # bash 定位 python 后 exec run.py
│   │
│   └── a3/                           # 12 个 A3 脚本（综合 / STA / 搜索 / 建议）
│       ├── synth_tool.py             # A3 综合总入口（双 CLI + 三阶段编排）
│       ├── backends/
│       │   ├── yosys_abc.py          # Yosys + ABC 综合（缺工具 → UNAVAILABLE）
│       │   ├── opensta.py            # OpenSTA STA（解析 arrival / slack）
│       │   └── icarus.py             # 可选门级预检
│       ├── equivalence.py            # Yosys equiv_simple；无法证明 → inconclusive
│       ├── netlist.py                # netlist 非空 / TOP / Liberty cell 完备性
│       ├── search/
│       │   ├── strategies.py         # 从 Strategy Catalog 选下一未评价策略
│       │   ├── pareto.py             # 二维 (area, arrival) 非支配排序
│       │   └── evolutionary.py       # 可选进化搜索 + fallback_triggered
│       ├── analysis/
│       │   ├── cost.py               # 归一化 + Pareto 筛选
│       │   └── hotspots.py           # 负 slack / 高面积 → hotspot 报告
│       ├── recommend.py              # hotspot + Pareto → 结构化 RTL 优化建议
│       └── reports/normalize.py      # 统一 synth / timing / search 报告片段
│
├── templates/                        # 只读模板资源
│   ├── prompts/                      # 27 个 Prompt md（Master / A1 / A2 / A3 / hooks）
│   ├── skills/                       # 28 个 SKILL.md（含 YAML front-matter）
│   ├── workspace/                    # Workspace 目录模板 + manifest 模板
│   ├── gate2/                        # Gate 2 反馈包模板
│   ├── reports/                      # 最终报告模板
│   └── agents/ · hooks/              # 补充说明占位
│
├── interfaces/                       # 101 个 JSON Schema（唯一权威）
│   ├── agents/     (10)              # common-task / result + 4 role-specific
│   ├── events/     ( 1)              # event.schema.json
│   ├── states/     ( 5)              # state-envelope / workflow / agent / hook / lease
│   ├── gates/      ( 4)              # gate1 / gate2-request / resolution / feedback-ack
│   ├── artifacts/  (34)              # rtl-version / verification / coverage / synth-report …
│   └── tools/      (47)              # common + 4 role 子目录
│
├── requests/
│   └── run.example.json              # 示例 dooragent run 请求
├── runs/                             # 每次 workflow 运行的物理根目录（.gitkeep 占位）
├── reference/                        # 只读参考（不进入生产决策路径）
├── bin/synth_tool                    # 可选 wrapper（部署时可能用到）
│
├── pyproject.toml                    # 可安装 Python package 与 CLI entry-point
├── submission.yaml                   # 产品交付元数据
├── .env.example                      # 环境变量示例（不含真实密钥）
├── .gitignore                        # 忽略 .env / runs 结果 / __pycache__ …
├── THIRD_PARTY.md                    # 所有外部工具版本 / 许可证 / 分发边界
├── CLAUDE.md                         # 自动化代码 Agent 硬约束
├── DoorAgent-EDA-Multi-Agent-产品化方案.md   # 完整设计文档（唯一权威）
└── README.md                         # 本文件
```

**目录到功能的对应关系（自上而下追溯任一 Tool）：**

```
用户请求 (dooragent run)
      │
      ▼
dooragent/cli.py  → dooragent/bootstrap.py  → 构造 MasterFacade
      │
      ▼
dooragent/agents/master/  ── 决策 & 路由 ──▶  A1/A2/A3 Facade
      │                                              │
      ├── 触发控制面 Tool                            │
      │      │                                       │
      │      ▼                                       ▼
      │  dooragent/orchestration/       dooragent/tooling/registry.py
      │  (调度/状态/Gate/Hook/Lease)     根据 tool_id 找到 Manifest
      │                                              │
      │                                              ▼
      │                                  configs/tool-manifests/<role>/<tool_id>.toml
      │                                              │
      │                                              ▼
      │                                  entrypoint = scripts/<role>/<name>.py
      │                                              │
      │                                              ▼
      │                                 subprocess 调用真实 Script
      │                                 (统一 --request-json/--result-json/…)
      │                                              │
      │                                              ▼
      │                                 Script 校验 interfaces/tools/**.schema.json
      │                                 调用外部 EDA 工具 (Yosys/ABC/OpenSTA/…)
      │                                 或返回 UNAVAILABLE
      │                                              │
      ▼                                              ▼
runs/<workflow>/workspaces/…/artifacts/ ◀── 原子发布 Artifact（带 hash 与 rtl_version_id）
```

---

## 四、通信机制：Agent 与 Agent、Agent 与 Tool 之间怎么"说话"

传统 EDA 流程是"人工在 shell 里手动串工具"，DoorAgent 把这条链路搬到
一个可追溯、可重放、可并发的运行时里。所有跨进程、跨 Agent 的通信都遵循
同一套硬约束，而不是让每个 Agent 用自然语言乱聊。

### 4.1 五种通信通道，各自解决不同问题

| 通道 | 位置 | 传什么 | 传输语义 |
|---|---|---|---|
| **Tool Request / Result** | Master ↔ orchestration ↔ Tool（同进程或 subprocess） | 结构化 JSON 请求 + 结构化 JSON 结果 | 同步；每个请求带 `request_id / idempotency_key`；退出码 → ToolStatus |
| **Agent Task / Result** | Master Facade ↔ A1/A2/A3 Facade | 版本化 Task 信封 + 结果信封 | 请求-响应；`schema_version / interface_version` 主版本不兼容拒绝执行 |
| **Event Bus**（文件系统消息） | 任意 → 任意（按矩阵） | Event 信封（含 `source / recipient / kind / payload`） | 异步；`write .partial → fsync → atomic rename → fsync dir` |
| **Artifact Exchange** | 生产者 Agent → Master → 消费者 Agent | 按内容 hash 存储的只读 blob + exchange manifest | 单写者原子发布；hash mismatch 直接拒收 |
| **Gate 1 / Gate 2** | Agent ↔ Master（长线程） | Gate 状态机 + Master Resolution + Agent ACK | 长事务；Gate 2 挂起只阻塞该实例，不阻塞 Master |

### 4.2 消息发布：`write .partial → fsync → atomic rename`

任何一次跨进程消息（事件、状态快照、Artifact、Case、Gate 反馈）都不允许
直接改目标文件，而是走这条不可撤销的原子链路：

```
生产者                          文件系统
   │                                │
   │  1. 写 tmp/msg.partial          │
   │─────────────────────────────▶ │
   │                                │
   │  2. fsync(fd)                   │
   │─────────────────────────────▶ │  ← 数据真的落盘
   │                                │
   │  3. os.replace(tmp, ready/msg.json)
   │─────────────────────────────▶ │  ← 目标要么完全存在、要么完全不存在
   │                                │
   │  4. fsync(dir)                  │
   │─────────────────────────────▶ │  ← 目录项落盘
   │                                │
   ▼                                ▼
  返回                        消费者可见
```

好处：**任何时刻断电/断进程，消费者要么看到旧版本、要么看到新版本，绝不会看到半截**。
崩溃后 [`recovery.cleanup_partials()`](dooragent/orchestration/recovery.py) 会
把遗留的 `*.partial` 全部删掉。

### 4.3 路由矩阵：Agent 不能私聊，一切走 Master

事件信封写在 [`dooragent/events/envelope.py`](dooragent/events/envelope.py)，
`validate_routing` 是硬校验：

```
source = A1 / A2 / A3   →   recipient 只能是 master / 本实例 observer
source = master         →   recipient 可以是 A1 / A2 / A3 / hook / observer
source = hook           →   只能提醒当前实例或升级到 master
```

违反矩阵的事件直接进入 `workflow/events/dead-letter/` 并记录
`ROUTING_POLICY_VIOLATION`；不会被任何 Agent 消费。**A2 不能读 A1 的
Workspace，反之亦然；A2 想要 A1 的仿真结果，只能让 Master 校验后
用 exchange 发过来。**

### 4.4 状态 CAS + 追加不可变 transition

所有可变状态（workflow / agent instance / hook / lease）都不是"就地改"，
而是走 Compare-And-Set：

```
调用方：state.transition(
            entity_type="workflow", entity_id="wf-1",
            expected_state_version=3,          ← 我以为版本是 3
            expected_lifecycle_state="ACTIVE", ← 我以为生命周期是 ACTIVE
            patch={"lifecycle_state": "COMPLETED"},
            transition_id="tr-abc"             ← 幂等键
        )

状态存储：
  1. 先追加不可变 transition 事件文件
     state/transitions/workflow/wf-1/000004-tr-abc.json
  2. 再原子替换快照 state/snapshots/workflow/wf-1.json
  3. 相同 transition_id 重复提交 → 幂等返回，不重复副作用
```

好处：**任何异常都能从 transition 序列重建当前快照**（`rebuild_from_transitions`），
不需要跨 Workspace 事务；`expected_state_version` 不匹配直接抛冲突而不是覆盖。

### 4.5 Artifact Exchange：按内容 hash 存储 + 版本绑定

跨 Agent 只能传 Artifact，不能传对象。发布流程（[`exchange.py`](dooragent/orchestration/exchange.py)）：

```
1. 生产者写好 artifact 文件
2. Master 调 exchange.publish([ExchangeEntry(...)]):
     a. 计算 sha256(file)
     b. 若声明了 expected_hash 但对不上 → ARTIFACT_HASH_MISMATCH，拒收
     c. blob 存到 exchange/blobs/<sha256>/<basename>
     d. manifest 写 exchange/manifests/<manifest_id>.json（原子）
3. 消费者拿到的是 manifest 里的引用（artifact://<hash>），不是路径
```

**每个 Artifact 强制绑定 7 个字段**：`workflow_id / workflow_round_id /
rtl_version_id / producer_agent_instance_id / schema_version /
artifact_hash / created_at`。候选回归产物还要绑
`candidate_id / parent_rtl_version_id / candidate_rtl_version_id /
candidate_hash`。**任何一个字段缺失，Master 的 `verify_artifacts` 直接拒**。

### 4.6 Gate 1 / Gate 2：让"长时间等外部事件"不阻塞 Master

- **Gate 1**（开新轮次）：`REQUESTED → VALIDATING → CREATING_WORKSPACES →
  SPAWNING → OPEN`；每次开轮建立新 `workflow_round_id`、新 Primary
  Workspace、新会话
- **Gate 2**（轮内长线程）：Agent 需要求助、等依赖、等 A1 门禁时打开一个
  Gate 2 Thread；Master 回复 Resolution（`CONTINUE /
  CONTINUE_WITH_CONSTRAINTS / REDIRECT / ROLLBACK / STOP_ROUND /
  REJECT_REQUEST`）；Agent ACK 后从原 attempt 恢复，`workflow_round_id`
  不变

**Master 在处理某个 Gate 2 时依然可以调度其他 Agent 实例**，因为
Master 内部是 Case Queue + Lease Scheduler，不是全局锁。

---

## 五、优势亮点

DoorAgent 与"把 LLM 当胶水直接调 EDA 工具"的做法有本质区别：

1. **四层清晰分层，避免 Agent 幻觉进入 EDA 结论**
   - `Agent` 只做开放决策（选策略、选下一个动作）
   - `Skill` 描述"何时用、要什么证据"
   - `Tool` 提供稳定 Schema 接口
   - `Script / Algorithm` 才真正执行 EDA 内核
   - LLM 只能选 Tool，不能"编造"出面积、时序、覆盖率数字

2. **单一入口 + 唯一真源**
   - 对外只有 `dooragent`；A1/A2/A3 CLI 只是内部脚本入口
   - Schema 唯一权威在 [`interfaces/`](interfaces/)（101 份 JSON Schema）
   - 每个 Tool 唯一绑定一份 Manifest；Tool ID 全局唯一

3. **可插拔后端 + 显式降级，不允许伪造成功**
   - Yosys/ABC/OpenSTA/Icarus/PyVerilog/Z3/cocotb/VCS/URG 全部通过 Manifest 接入
   - 缺工具时显式 `UNAVAILABLE / TOOL_NOT_IMPLEMENTED`，写入 diagnostics
   - A3 进化搜索工具不可用或连续无改进 → 自动 `fallback_triggered=true` 回退 catalog

4. **完全相对路径 + 崩溃可恢复**
   - 所有持久化路径相对 `product_run_root` 或 `workspace_root`
   - 整个 `runs/<workflow>/` 目录可以 tar 到别的机器上 `dooragent resume` 恢复
   - `.partial` 遗留、stale claim、Lease 过期都能自动回收

5. **多 Agent 隔离 + 版本身份严格绑定**
   - A2 不能读 A1 的 Workspace，反之亦然；跨 Agent 只走 Master + 只读 Artifact
   - 每个 Artifact 强绑 `rtl_version_id`；不同 RTL 版本的产物永远不会被误混
   - A3 候选进入回归前先物化成独立 `candidate_rtl_version_id`，防止候选窜版本

6. **原子 + CAS + 幂等，天然抗并发**
   - 事件/状态/Artifact 一律 `.partial → fsync → atomic rename`
   - 状态存储用 CAS + `expected_state_version`；`transition_id` 幂等
   - 5 worker × 50 case 并发消费 Case Queue 不会重复 claim

7. **模型密钥零落盘 + 三层脱敏**
   - Provider/Key/URL/超时/重试全部从环境变量读，`ModelSettings.__repr__` 显式屏蔽 key
   - `secret_redactor` 覆盖：环境变量值 / `Authorization` header / `Bearer <token>`
   - EDA Tool 子进程用白名单 env 启动，默认不继承模型密钥
   - Agent 子进程只拿到必要模型变量，Workspace 里不会有 `.env` 副本

8. **不写死流程顺序，只写死"护栏"**
   - Master 不规定"A1 → A2 → A3"固定顺序；A2 生成和 A3 基线可以并行
   - A2 coverage loop、A3 探索都允许 0..N 轮
   - Master 只监督：里程碑是否推进、证据是否齐全、版本是否一致、是否有信息增益

---

## 六、快速开始

```bash
# 1. 安装
pip install -e '.[dev]'

# 2. 配置模型（本地开发可用 mock provider，不出网）
cp .env.example .env
# 编辑 .env 至少填入：
#   DOORAGENT_MODEL_PROVIDER=mock          # 或 openai_compatible
#   DOORAGENT_MODEL_NAME=any-name

# 3. 创建一个 workflow
dooragent run --request requests/run.example.json --workflow-id my-run-1

# 4. 查看状态 / 列 Tool / 恢复 / 取消
dooragent status --workflow my-run-1
dooragent list-tools           # 看 39 个 Tool 各自的 health 状态
dooragent resume  --workflow my-run-1
dooragent cancel  --workflow my-run-1
```

`dooragent` 是**唯一产品入口**。A1/A2/A3 的 CLI 与 `scripts/**` 只作为
Tool Manifest 绑定的内部脚本或单元测试入口，不作为产品对外路由。

想让真正的 EDA 工具跑起来（而不是返回 UNAVAILABLE），在 `.env` 里加：

```bash
DOORAGENT_YOSYS_BIN=/usr/local/bin/yosys
DOORAGENT_OPENSTA_BIN=/usr/local/bin/sta
DOORAGENT_ICARUS_IVERILOG_BIN=/usr/local/bin/iverilog
DOORAGENT_ICARUS_VVP_BIN=/usr/local/bin/vvp
# VCS/URG 只从已授权环境调用，不入库
DOORAGENT_VCS_BIN=/tools/vcs/bin/vcs
DOORAGENT_URG_BIN=/tools/vcs/bin/urg
```

## 七、外部依赖披露

见 [`THIRD_PARTY.md`](THIRD_PARTY.md)。所有外部工具（PyVerilog、Z3、cocotb、
Yosys、ABC、OpenSTA、Icarus、Nangate45、VCS/URG …）都必须通过 Tool
Manifest 声明版本、许可证与调用边界。**缺失时对应能力显式返回 `UNAVAILABLE
/ TOOL_NOT_IMPLEMENTED`，不允许伪造成功。**
