"""DoorAgent 顶层包。

对外产品入口只有：
    dooragent run --request <request.json>
    dooragent resume --workflow <workflow_id>
    dooragent status --workflow <workflow_id>
    dooragent cancel --workflow <workflow_id>

其余 A1/A2/A3 CLI 只作为 Tool Manifest 绑定的内部脚本入口或单元测试入口，
不作为产品路由。
"""

__version__ = "0.1.0"
