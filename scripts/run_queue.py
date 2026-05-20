"""Forge queue runner — drained by Claude Code in VS Code via /run-queue.

Five modes, picked by argv::

    python -m scripts.run_queue
        Default. List pending items and remind the operator that the
        executor is the agent, not this script.

    python -m scripts.run_queue --list
        Same as default; explicit form.

    python -m scripts.run_queue --claim <queue_id>
        Atomically flip status pending -> claimed, recompute upstream_hash,
        and on match print the absolute bundle path to stdout (exit 0).
        On staleness, flip the item to failed with error="upstream changed"
        and exit 2.

    python -m scripts.run_queue --complete <queue_id> --deliverable <path>...
        Flip status claimed -> done. Append the deliverable paths to the
        task step's deliverable_paths, then flip the task step to
        status=complete.

    python -m scripts.run_queue --fail <queue_id> --error <msg>
        Flip status -> failed with a human-readable error string.

The script never invokes the model. The slash command body
(``.claude/commands/run-queue.md``) drives the agent to read the bundle,
do the work, and call back into this script via ``--complete`` or
``--fail``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

from web import bundles, db
from web.models import QueueItem


REPO_ROOT = bundles.REPO_ROOT


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _pending_items() -> list[dict[str, Any]]:
    return [r for r in db.rows("queue") if r.get("status") == "pending"]


def _validate_item_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Round-trip through QueueItem to enforce schema."""
    return QueueItem.model_validate(row).model_dump(mode="json")


# --- modes -------------------------------------------------------------------


def _mode_list(stdout) -> int:
    pending = _pending_items()
    if not pending:
        print("(queue is empty — no pending items)", file=stdout)
        print(
            "When the dashboard appends work it lands here. The Forge slash "
            "command (/run-queue) is how an agent in VS Code picks it up.",
            file=stdout,
        )
        return 0

    print(f"{len(pending)} pending queue item(s):", file=stdout)
    for r in pending:
        print(
            f"  {r['id']}  task={r['task_id']}  step={r['step_id']}  "
            f"agent_role={r.get('agent_role') or '-'}  "
            f"bundle={r['bundle_path']}",
            file=stdout,
        )
    print(
        "\nThis script does not invoke the model. Open VS Code in the repo "
        "and run the `/run-queue` Claude Code slash command to drain.",
        file=stdout,
    )
    return 0


def _mode_claim(queue_id: str, stdout, stderr) -> int:
    row = db.find("queue", queue_id)
    if row is None:
        print(f"queue item not found: {queue_id!r}", file=stderr)
        return 1
    if row.get("status") != "pending":
        print(
            f"cannot claim: status is {row.get('status')!r} (need 'pending')",
            file=stderr,
        )
        return 1

    try:
        # Re-read REPO_ROOT in case a test monkeypatched it after import.
        current_hash = bundles.compute_upstream_hash(
            row["task_id"], row["step_id"]
        )
    except (KeyError, ValueError) as exc:
        patch = {
            "status": "failed",
            "error": f"cannot recompute upstream: {exc}",
            "completed_at": _now_iso(),
        }
        _validate_item_dict({**row, **patch})
        db.update("queue", queue_id, patch)
        print(f"failed: {exc}", file=stderr)
        return 2

    stored = row.get("upstream_hash")
    if stored is not None and stored != current_hash:
        patch = {
            "status": "failed",
            "error": "upstream changed",
            "completed_at": _now_iso(),
        }
        _validate_item_dict({**row, **patch})
        db.update("queue", queue_id, patch)
        print(
            f"failed: upstream changed (stored={stored}, now={current_hash})",
            file=stderr,
        )
        return 2

    patch = {
        "status": "claimed",
        "claimed_at": _now_iso(),
        "upstream_hash": current_hash,
    }
    _validate_item_dict({**row, **patch})
    db.update("queue", queue_id, patch)

    bundle_abs = bundles.REPO_ROOT / row["bundle_path"]
    print(str(bundle_abs), file=stdout)
    return 0


def _mode_complete(
    queue_id: str, deliverables: list[str], stdout, stderr
) -> int:
    row = db.find("queue", queue_id)
    if row is None:
        print(f"queue item not found: {queue_id!r}", file=stderr)
        return 1
    if row.get("status") not in ("claimed", "pending"):
        print(
            f"cannot complete: status is {row.get('status')!r} "
            f"(need 'claimed' or 'pending')",
            file=stderr,
        )
        return 1

    now = _now_iso()
    patch = {
        "status": "done",
        "completed_at": now,
        "result_path": deliverables[0] if deliverables else None,
    }
    _validate_item_dict({**row, **patch})
    db.update("queue", queue_id, patch)

    task_id = row["task_id"]
    step_id = row["step_id"]
    task = db.find("tasks", task_id)
    if task is None:
        print(
            f"queue item completed, but task {task_id!r} not found "
            f"(deliverables not attached)",
            file=stderr,
        )
        return 0

    def _mutate(doc: dict[str, Any]) -> dict[str, Any]:
        for t in doc["rows"]:
            if t.get("id") != task_id:
                continue
            for s in t.get("steps", []):
                if s.get("step_id") != step_id:
                    continue
                existing = list(s.get("deliverable_paths") or [])
                for p in deliverables:
                    if p not in existing:
                        existing.append(p)
                s["deliverable_paths"] = existing
                s["status"] = "complete"
                s["completed_at"] = now
            return doc
        return doc

    db.write("tasks", _mutate)

    # After flipping the step to complete, fire downstream successors.
    try:
        from web import tasks_helpers

        tasks_helpers.maybe_queue_successors(task_id)
        tasks_helpers.recompute_task_status(task_id)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"warning: post-complete hooks raised: {exc}",
            file=stderr,
        )

    print(f"queue item {queue_id} complete; step {step_id} flipped to complete",
          file=stdout)
    return 0


def _mode_fail(queue_id: str, error: str, stdout, stderr) -> int:
    row = db.find("queue", queue_id)
    if row is None:
        print(f"queue item not found: {queue_id!r}", file=stderr)
        return 1
    if row.get("status") in ("done", "failed"):
        print(
            f"cannot fail: status is already {row.get('status')!r}",
            file=stderr,
        )
        return 1
    patch = {
        "status": "failed",
        "completed_at": _now_iso(),
        "error": error,
    }
    _validate_item_dict({**row, **patch})
    db.update("queue", queue_id, patch)
    print(f"queue item {queue_id} marked failed: {error}", file=stdout)
    return 0


# --- entrypoint --------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.run_queue",
        description="Drain the Forge queue (consumed by VS Code /run-queue).",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--list",
        action="store_true",
        help="List pending queue items (default).",
    )
    g.add_argument(
        "--claim",
        metavar="QUEUE_ID",
        help="Atomically claim an item; prints bundle path on success.",
    )
    g.add_argument(
        "--complete",
        metavar="QUEUE_ID",
        help="Mark an item done and attach deliverables.",
    )
    g.add_argument(
        "--fail",
        metavar="QUEUE_ID",
        help="Mark an item failed.",
    )
    p.add_argument(
        "--deliverable",
        action="append",
        default=[],
        help=(
            "Deliverable path relative to the repo (repeatable). "
            "Used only with --complete."
        ),
    )
    p.add_argument(
        "--error",
        default="",
        help="Error message. Used only with --fail.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    stdout = sys.stdout
    stderr = sys.stderr

    if args.claim:
        return _mode_claim(args.claim, stdout, stderr)
    if args.complete:
        if not args.deliverable:
            print(
                "--complete requires at least one --deliverable",
                file=stderr,
            )
            return 1
        return _mode_complete(
            args.complete, list(args.deliverable), stdout, stderr
        )
    if args.fail:
        if not args.error:
            print("--fail requires --error", file=stderr)
            return 1
        return _mode_fail(args.fail, args.error, stdout, stderr)

    return _mode_list(stdout)


if __name__ == "__main__":
    raise SystemExit(main())
