# Contributing

```
pip install -e ".[dev]"
pytest
ruff check .
```

- One concern per module; every package exposes its public API through `__all__`.
- Use relative imports inside the package and `from __future__ import annotations` in every module.
- New summary kinds: add a writer method, a `RunData._on_<kind>` handler, a route and a UI view.
- Try the dashboard on synthetic data: `python tests/dashboard_demo.py`.
