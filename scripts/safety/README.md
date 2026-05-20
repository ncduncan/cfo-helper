# Safety — denylist scanner

Two layers of defense against accidentally committing private content to the
public repo.

## Layer 1 — pre-commit hook (local)

Installed via [pre-commit](https://pre-commit.com/):

```
pre-commit install
```

Configured in [.pre-commit-config.yaml](../../.pre-commit-config.yaml). Runs
[`denylist_check.py --staged`](denylist_check.py) on every `git commit`. Reads:

- The always-on baseline literals + credential regexes in `denylist_check.py`
  (names of the original maintainer, ex-tenant identifiers, AWS/GitHub/Slack
  token shapes, private-key blocks).
- Your `profile/.denylist` if present — one literal per line, `#` for comments.
  This is where you list customer names, executive names, internal codenames,
  product names, anything you want the hook to refuse.

If a staged file matches, the commit is blocked and the matching `file:line`
locations are printed.

## Layer 2 — GitHub Actions (CI)

[`.github/workflows/safety-check.yml`](../../.github/workflows/safety-check.yml)
runs on every push and PR. Calls `denylist_check.py --ci`, which scans every
tracked file in the repo against the baseline only (CI cannot see the
gitignored `profile/.denylist`).

This catches the case where the local hook was skipped (`--no-verify`),
wasn't installed, or where a fork inherits the baseline.

## Adding to the denylist

For your own private strings, edit `profile/.denylist`:

```
# customers
Acme Corp
Globex Industries
# executives
Jane Doe
# internal codenames
project-aurora
```

To make the framework stricter for everyone (e.g., a credential pattern that
should always be blocked), add to `BASELINE_LITERALS` or `BASELINE_PATTERNS`
in `denylist_check.py` and open a PR.

## Bypassing (don't)

The hook can be bypassed with `git commit --no-verify`. The CI check cannot
be bypassed without disabling the workflow. If you're hitting a false
positive, fix the scanner or add the path to `SKIP_DIRS` / `SKIP_SUFFIXES`
rather than bypassing.
