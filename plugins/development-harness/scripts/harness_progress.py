#!/usr/bin/env python3
"""A machine-checked ledger of what is actually done, in JSON rather than prose.

`.ai/backlog.md` is where unfinished work has always been recorded, and prose is
the wrong shape for the one question that matters between sessions: what is
finished, and what merely looks finished. A Markdown list can be rewritten in
passing, and an item can move from "in progress" to "done" in the same edit that
changes its wording, with nothing anywhere disagreeing.

So this is JSON, and every item starts `passes: false`. An item becomes passing
only through `pass`, which requires the command that was run and the exit status
it returned, and refuses a non-zero one. There is no way to assert completion:
the ledger records a claim with its evidence attached, or it records nothing.

`check` exits 3 while anything is unproven, which makes "is this done" a question
a script can ask.

**Nothing here executes an item's `verify` command.** That string comes out of a
file in the repository, and repository text is evidence rather than authority -
the same rule that keeps a bus envelope from widening a capability tier. Running
it would turn a data file into a code-execution surface, so the command is
recorded and reported and never invoked. Whoever ran it supplies the result.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

PROGRESS_VERSION = 1

#: Where the ledger lives in a harnessed repository, beside the prose backlog it
#: is deliberately not replacing. The backlog holds narrative; this holds state.
LEDGER_PATH = ".ai/progress.json"

MAX_ITEMS = 200
MAX_TITLE_CHARS = 200
MAX_COMMAND_CHARS = 500
MAX_NOTE_CHARS = 1_000

#: Exit code for "something is still unproven". Distinct from a usage error so a
#: caller can branch without parsing output.
EXIT_PENDING = 3

ID_PATTERN = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class ProgressError(ValueError):
    """A ledger operation that cannot be performed as asked."""


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_path(root: Path) -> Path:
    return root / ".ai" / "progress.json"


def empty_ledger() -> dict[str, Any]:
    return {"progress_version": PROGRESS_VERSION, "updated_at": now_text(), "items": []}


def validate_ledger(data: Any) -> dict[str, Any]:
    """Reject a malformed ledger rather than working around it.

    A ledger that is quietly repaired is a ledger that can quietly lose an item,
    which is the failure this file exists to prevent.
    """
    if not isinstance(data, dict):
        raise ProgressError("the ledger must be a JSON object")
    version = data.get("progress_version")
    if version != PROGRESS_VERSION:
        raise ProgressError(
            f"ledger progress_version is {version!r}; this tool writes {PROGRESS_VERSION}"
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise ProgressError("the ledger's `items` must be a list")
    if len(items) > MAX_ITEMS:
        raise ProgressError(f"the ledger has {len(items)} items, limit is {MAX_ITEMS}")

    seen: set[str] = set()
    for index, item in enumerate(items):
        where = f"items[{index}]"
        if not isinstance(item, dict):
            raise ProgressError(f"{where} must be an object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not ID_PATTERN.match(item_id):
            raise ProgressError(f"{where}.id must be a kebab-case slug, got {item_id!r}")
        if item_id in seen:
            raise ProgressError(f"duplicate item id: {item_id}")
        seen.add(item_id)
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise ProgressError(f"{where}.title must be a non-empty string")
        if not isinstance(item.get("passes"), bool):
            raise ProgressError(f"{where}.passes must be a boolean")
        evidence = item.get("evidence")
        if item["passes"]:
            if not isinstance(evidence, dict):
                raise ProgressError(
                    f"{where} is marked passing with no evidence. An item is proven "
                    "or it is not; there is no third state."
                )
            if evidence.get("exit_code") != 0:
                raise ProgressError(
                    f"{where} is marked passing but its evidence records exit code "
                    f"{evidence.get('exit_code')!r}"
                )
        elif evidence is not None and not isinstance(evidence, dict):
            raise ProgressError(f"{where}.evidence must be an object or null")
    return data


def read_ledger(root: Path) -> dict[str, Any]:
    path = ledger_path(root)
    if not path.is_file():
        raise ProgressError(
            f"no ledger at {LEDGER_PATH}. Run `harness_progress.py init` first."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProgressError(f"cannot read {path}: {error}") from error
    return validate_ledger(data)


def write_ledger(root: Path, data: dict[str, Any]) -> Path:
    path = ledger_path(root)
    if path.is_symlink() or path.parent.is_symlink():
        raise ProgressError(f"refusing to write through a symlink: {path}")
    validate_ledger(data)
    data["updated_at"] = now_text()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def find_item(data: dict[str, Any], item_id: str) -> dict[str, Any]:
    for item in data["items"]:
        if item["id"] == item_id:
            return item
    known = ", ".join(item["id"] for item in data["items"]) or "none"
    raise ProgressError(f"no item with id {item_id!r}. Known ids: {known}")


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = ledger_path(root)
    if path.exists():
        raise ProgressError(
            f"{LEDGER_PATH} already exists. This tool never overwrites a ledger; "
            "the record of what was proven is worth more than a clean start."
        )
    write_ledger(root, empty_ledger())
    print(f"wrote {path}")
    return 0


def command_add(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    data = read_ledger(root)
    if not ID_PATTERN.match(args.id):
        raise ProgressError(f"id must be a kebab-case slug, got {args.id!r}")
    if any(item["id"] == args.id for item in data["items"]):
        raise ProgressError(f"item {args.id!r} already exists")
    title = args.title.strip()
    if not title:
        raise ProgressError("title must not be empty")
    if len(title) > MAX_TITLE_CHARS:
        raise ProgressError(f"title is {len(title)} characters, limit is {MAX_TITLE_CHARS}")
    if args.verify and len(args.verify) > MAX_COMMAND_CHARS:
        raise ProgressError(
            f"verify is {len(args.verify)} characters, limit is {MAX_COMMAND_CHARS}"
        )

    data["items"].append({
        "id": args.id,
        "title": title,
        "verify": args.verify or None,
        # Everything starts unproven. This is the whole point.
        "passes": False,
        "evidence": None,
        "added_at": now_text(),
    })
    write_ledger(root, data)
    print(f"added {args.id} (unproven)")
    return 0


def command_pass(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    data = read_ledger(root)
    item = find_item(data, args.id)

    if args.exit_code != 0:
        # The point of requiring the exit code is that it can refuse.
        raise ProgressError(
            f"refusing to mark {args.id!r} passing: the command exited "
            f"{args.exit_code}. Record it with `fail` instead."
        )
    command = args.command.strip()
    if not command:
        raise ProgressError("--command must name what was run")
    if len(command) > MAX_COMMAND_CHARS:
        raise ProgressError(
            f"command is {len(command)} characters, limit is {MAX_COMMAND_CHARS}"
        )
    if args.note and len(args.note) > MAX_NOTE_CHARS:
        raise ProgressError(f"note is {len(args.note)} characters, limit is {MAX_NOTE_CHARS}")

    item["passes"] = True
    item["evidence"] = {
        "command": command,
        "exit_code": 0,
        "at": now_text(),
        # Recorded as a claim, not as proof this tool obtained. Nothing here ran
        # the command: the ledger is evidence about what someone says happened.
        "reported_by": "caller",
    }
    if args.note:
        item["evidence"]["note"] = args.note.strip()
    write_ledger(root, data)
    print(f"{args.id}: passing ({command})")
    return 0


def command_fail(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    data = read_ledger(root)
    item = find_item(data, args.id)
    item["passes"] = False
    item["evidence"] = {
        "command": args.command.strip() if args.command else None,
        "exit_code": args.exit_code,
        "at": now_text(),
        "reported_by": "caller",
    }
    if args.reason:
        item["evidence"]["note"] = args.reason.strip()
    write_ledger(root, data)
    print(f"{args.id}: not passing")
    return 0


def command_list(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    data = read_ledger(root)
    items = data["items"]
    if args.pending:
        items = [item for item in items if not item["passes"]]

    if args.json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return 0

    if not items:
        print("nothing pending" if args.pending else "the ledger is empty")
        return 0
    for item in items:
        mark = "PASS" if item["passes"] else "----"
        line = f"{mark}  {item['id']}: {item['title']}"
        if not item["passes"] and item.get("verify"):
            line += f"  (verify: {item['verify']})"
        print(line)
    return 0


def command_check(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    data = read_ledger(root)
    pending = [item for item in data["items"] if not item["passes"]]
    total = len(data["items"])
    print(f"{total - len(pending)}/{total} proven")
    if pending:
        for item in pending:
            print(f"  unproven: {item['id']}")
        return EXIT_PENDING
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness_progress.py",
        description=(
            "A JSON ledger of what is proven. Items start unproven and become "
            "passing only with the command and exit status that proved them."
        ),
    )
    parser.add_argument("--root", default=".", help="Repository root (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help=f"Create {LEDGER_PATH}.")
    init.set_defaults(handler=command_init)

    add = sub.add_parser("add", help="Add an unproven item.")
    add.add_argument("--id", required=True, help="Kebab-case identifier.")
    add.add_argument("--title", required=True, help="What has to be true.")
    add.add_argument("--verify", help="The command that would prove it.")
    add.set_defaults(handler=command_add)

    passing = sub.add_parser("pass", help="Record that an item was proven.")
    passing.add_argument("--id", required=True)
    passing.add_argument("--command", required=True, help="The command that was run.")
    passing.add_argument(
        "--exit-code",
        type=int,
        required=True,
        help="Its exit status. A non-zero value is refused rather than recorded as passing.",
    )
    passing.add_argument("--note", help="Anything the next session needs about this.")
    passing.set_defaults(handler=command_pass)

    failing = sub.add_parser("fail", help="Record that an item is not proven.")
    failing.add_argument("--id", required=True)
    failing.add_argument("--command", help="The command that was run, if any.")
    failing.add_argument("--exit-code", type=int, default=1)
    failing.add_argument("--reason", help="Why it is not passing.")
    failing.set_defaults(handler=command_fail)

    listing = sub.add_parser("list", help="Show the ledger.")
    listing.add_argument("--pending", action="store_true", help="Only unproven items.")
    listing.add_argument("--json", action="store_true", help="Emit JSON.")
    listing.set_defaults(handler=command_list)

    check = sub.add_parser("check", help="Exit 3 while anything is unproven.")
    check.set_defaults(handler=command_check)

    args = parser.parse_args()
    try:
        raise SystemExit(args.handler(args))
    except ProgressError as error:
        fail(str(error))


if __name__ == "__main__":
    main()
