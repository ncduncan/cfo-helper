"""TPS Lean metric computation.

Two modules; both deterministic, both pure functions over inputs.

- :mod:`scripts.lean.metrics` — retrospective metrics. Handoff count per
  template, cycle-time percentiles, value-add ratio, queue dwell from the
  historical record (completed tasks + completed queue items).
- :mod:`scripts.lean.wip_flow` — current-state metrics. WIP per assignee,
  queue depth, push signals, bottleneck score, batch coefficient,
  context-switching, against the live in-progress slice of the db.

Both modules read live state through :func:`web.db.rows`, which takes the
filelock so a concurrent dashboard write cannot produce a partial snapshot.
When ``profile/`` does not exist (fresh clone), live-data metrics are
returned as the sentinel string ``"not_applicable"`` — not ``None``, not
``0`` — so downstream consumers can distinguish "no data" from "zero".
"""

NOT_APPLICABLE = "not_applicable"
