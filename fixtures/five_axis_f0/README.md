# Five-Axis Math F0 fixture

F0 的 JSON 单一真相位于 `src/axiom/five_axis/fixtures/`，并作为 package data 随 wheel 发布；本目录不复制 payload，避免两套内容 ID 漂移。

F0 只验证 manifest、M0–M5 envelope、能力依赖、数值环境声明和显式 Artifact Adapter。它不执行 M1–M5 数值求解，也不产生几何、运动学、碰撞或设备可执行正向声明。

Python 使用：

```python
from axiom import evaluate_run, f0_example_run_spec

bundle = evaluate_run(f0_example_run_spec())
print(bundle.model_dump_json(indent=2, by_alias=True, exclude_none=True))
```

也可以启动 `axiom serve`，在网页顶部切换到 **Five-Axis Lab** 后验证同一 F0 契约。
