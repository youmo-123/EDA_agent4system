# 第三方工具与依赖披露

本项目通过 Tool Manifest 接入以下外部组件；工程本身不重新实现这些工具的
内部算法，也不打包分发商业授权。缺失或未通过 health check 时对应 Tool
必须返回 `UNAVAILABLE / TOOL_NOT_IMPLEMENTED`，不允许伪造成功。

## Python 依赖

| 组件 | 用途 | 建议版本 | 许可证 | 备注 |
|---|---|---|---|---|
| PyVerilog | A2 RTL AST 解析（默认 `rtl_parser` Backend） | >=1.3 | Apache-2.0 | 缺失则接口分析返回 UNAVAILABLE |
| z3-solver | A2 约束求解与固定 seed 序列生成 | >=4.12 | MIT | 缺失则约束生成降级为随机启发式 |
| cocotb | A2 Testbench Runner 默认插件 | >=1.8 | BSD-3-Clause | 需要底层仿真器可用 |
| cocotbext-axi | A2 AXI 协议组件默认插件 | >=0.1 | MIT | 属于协议 Backend 集合 |
| jsonschema | Schema 校验 | >=4.21 | MIT | 控制面强依赖 |

## 外部 EDA 二进制

| 组件 | 用途 | 许可证 | 分发策略 |
|---|---|---|---|
| Yosys | A3 Synthesis Backend / 等价检查 | ISC | 只调用已安装二进制；不打包 |
| ABC | A3 Optimization+Mapping Backend | 学术开源 | 通常随 Yosys 或独立安装 |
| OpenSTA | A3 STA Backend | GPL-3.0 | 只调用已安装二进制 |
| Icarus Verilog | A3 Gate Precheck / A2 备选仿真 | GPL-2.0 | 只调用已安装二进制 |
| VCS + URG | A2 商业仿真与结构覆盖率（可选） | 商业授权 | 只从已授权环境调用，不打包不分发 |
| Verilator | 备选仿真参考 | LGPL-3.0 或 Artistic-2.0 | 只调用已安装二进制 |

## Technology Library

| Library | 用途 | 授权 |
|---|---|---|
| Nangate45 | 默认 open-source Technology Library | 需自行获取，不入库 |
| 用户自选 Liberty | 生产用工艺库 | 遵循供应商协议，不入库 |

## 声明

1. 所有外部工具版本、路径与 hash 必须写入运行时 Tool Manifest / 执行 Report。
2. Tool 缺失或版本不匹配必须显式失败并写入 diagnostics。
3. 商业授权工具的可执行路径只允许在部署环境中通过配置或环境变量注入。
