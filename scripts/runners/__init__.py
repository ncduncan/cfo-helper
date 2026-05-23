"""Per-task-type runner modules.

Each sub-module owns the runner functions for one task type.
``scripts.dispatch`` re-exports all public symbols so
``task_types/*.yaml`` deterministic_runner strings keep resolving.
"""
