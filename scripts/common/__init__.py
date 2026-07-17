"""scripts.common：所有 scripts/*.py 共享的最小工具库。

- atomic_io: 原子写 JSON（write .partial → fsync → atomic rename → fsync dir）
- command: 参数化的 subprocess 启动，禁止 Shell 拼接
- schema_io: 加载与校验 JSON Schema（jsonschema Draft 2020-12）
- artifact_io: 相对路径 artifact 引用；hash/写读
"""
