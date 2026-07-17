"""scripts.a1.core：A1 自研仿真/覆盖内核接口。

真实 A1 编译器/仿真器由外部工程实现；本目录提供 Mock 内核用于骨架测试与
CI 通过，实际接入时替换为真实实现或通过 DOORAGENT_A1_SIMULATOR_BIN 指向
外部二进制。
"""
