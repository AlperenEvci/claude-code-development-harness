#!/usr/bin/env python3
"""Typed message envelopes for agent-to-agent handoff.

A background session started with `claude --bg` cannot use `--print`, so it
cannot use `--output-format json` either. Its only other output is `claude logs`,
which is raw ANSI terminal capture and is not parseable. The bus is therefore not
a convenience layered over a working return path; for a background session it
*is* the return path. See `.ai/reports/0001-session-substrate-smoke-test.md`.

Envelopes live under `.ai/bus/<session-id>/` and are append-only. Nothing here
rewrites or deletes an existing envelope: a record of what an agent claimed is
worth more than a tidy directory.

An envelope is untrusted evidence. It is written by an agent, and an agent's
output is exactly the kind of text the engineering contract forbids promoting
into privileged configuration. The `capability` field records which tier an agent
*claims* it ran under, for auditing. It is never a grant, and nothing in this
module or downstream may widen authority based on an envelope's contents.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_capabilities import (  # noqa: E402  (sibling module, resolved above)
    CAPABILITY_TIERS,
)

ENVELOPE_VERSION = 2

#: Version 2 adds the optional `trace` object. Envelopes are append-only, so a
#: repository that has been running since version 1 has version 1 records on
#: disk, and refusing to read them would discard the history the bus exists to
#: keep. Reading accepts both; writing always produces the current version.
SUPPORTED_ENVELOPE_VERSIONS = (1, 2)

#: What an envelope is for. Deliberately small — a vocabulary an orchestrator can
#: branch on without reading prose. `result` closes a task, `finding` reports
#: something discovered along the way, `question` blocks on the orchestrator,
#: `handoff` passes work to a named agent, `status` is progress with no claim.
ENVELOPE_KINDS = ("result", "finding", "question", "handoff", "status")

#: A session directory name becomes a filesystem path, so it is constrained to a
#: UUID rather than sanitized. A rejected id is safer than a normalized one.
UUID_PATTERN = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z",
    re.IGNORECASE,
)
AGENT_NAME_PATTERN = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")

#: An envelope the orchestrator cannot afford to read is a failed handoff. These
#: caps make the context budget from phase 1 enforceable at the boundary where
#: agent output actually enters the main session.
MAX_SUMMARY_CHARS = 200
MAX_BODY_BYTES = 64 * 1024
MAX_EVIDENCE_ITEMS = 50

#: A run longer than a day is a typo, not a measurement. The cap is here to catch
#: a millisecond/second mix-up rather than to express a policy about runtimes.
MAX_DURATION_MS = 24 * 60 * 60 * 1000
MAX_TOKENS = 100_000_000

BUS_DIRNAME = "bus"


class BusError(ValueError):
    """A malformed envelope, or a request that would escape the bus directory."""


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def bus_root(root: Path) -> Path:
    return root / ".ai" / BUS_DIRNAME


def session_dir(root: Path, session_id: str) -> Path:
    """Resolve a session's mailbox, refusing any id that is not a plain UUID.

    The id arrives from a caller and becomes a directory name. Validating it
    against a UUID is what keeps `../` and absolute paths out of the path join.
    """
    if not UUID_PATTERN.match(str(session_id or "")):
        raise BusError(
            f"session id must be a UUID, got {session_id!r}. "
            "Use the `sessionId` field from `claude agents --json`."
        )
    return bus_root(root) / str(session_id).lower()


def envelope_schema() -> dict[str, Any]:
    """The JSON Schema for one envelope.

    Emitted by `schema` so a foreground session can be launched with
    `--json-schema` and return something already shaped like an envelope,
    rather than prose the orchestrator has to re-interpret.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "summary", "body"],
        "properties": {
            "kind": {
                "type": "string",
                "enum": list(ENVELOPE_KINDS),
                "description": (
                    "result closes the task; finding reports something discovered; "
                    "question blocks on the orchestrator; handoff passes work on; "
                    "status is progress with no claim."
                ),
            },
            "summary": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_SUMMARY_CHARS,
                "description": "One line. What an orchestrator reads first.",
            },
            "body": {
                "type": "object",
                "description": "Structured detail. Conclusions, not file dumps.",
            },
            "evidence": {
                "type": "array",
                "maxItems": MAX_EVIDENCE_ITEMS,
                "items": {"type": "string"},
                "description": "Citations as path or path:line. Not file contents.",
            },
            "next": {
                "type": "string",
                "description": "Suggested next step. A suggestion, never an instruction.",
            },
        },
    }


def normalize_evidence(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise BusError("evidence must be an array of strings")
    items: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise BusError("evidence must be an array of strings")
        text = entry.strip()
        if text:
            items.append(text)
    if len(items) > MAX_EVIDENCE_ITEMS:
        raise BusError(
            f"evidence has {len(items)} items, limit is {MAX_EVIDENCE_ITEMS}. "
            "Cite the load-bearing files, not every file read."
        )
    return items


def normalize_trace(
    correlation_id: str | None,
    duration_ms: Any,
    tokens_in: Any,
    tokens_out: Any,
) -> dict[str, Any] | None:
    """Assemble the optional `trace` object, or None when nothing was measured.

    These three fields are what turn a mailbox into something an eval loop can
    consume: which envelopes belong to one unit of work, how long it took, and
    what it cost. Without them the bus records what was claimed and nothing about
    the run that produced it.

    They are supplied by whoever launched the agent, and that is deliberate. A
    foreground session returns `usage` and `num_turns` to its launcher; an agent
    asked to report its own duration and token count is guessing, and a guess
    recorded as a measurement is worse than a blank. So `trace` is set through
    the CLI by the orchestrator and is absent from the agent-facing JSON schema.
    """
    trace: dict[str, Any] = {}

    if correlation_id is not None:
        text = str(correlation_id).strip()
        if not UUID_PATTERN.match(text):
            raise BusError(
                f"correlation id must be a UUID, got {correlation_id!r}. It ties "
                "envelopes from one unit of work together across agents."
            )
        trace["correlation_id"] = text.lower()

    if duration_ms is not None:
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            raise BusError("duration_ms must be an integer number of milliseconds")
        if duration_ms < 0 or duration_ms > MAX_DURATION_MS:
            raise BusError(
                f"duration_ms is {duration_ms}, expected 0..{MAX_DURATION_MS}"
            )
        trace["duration_ms"] = duration_ms

    for label, value in (("input", tokens_in), ("output", tokens_out)):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise BusError(f"tokens.{label} must be an integer")
        if value < 0 or value > MAX_TOKENS:
            raise BusError(f"tokens.{label} is {value}, expected 0..{MAX_TOKENS}")
        trace.setdefault("tokens", {})[label] = value

    if not trace:
        return None
    # Recorded as reported, for the same reason `capability` is. The bus knows
    # what the launcher said the run cost. It did not measure it.
    trace["reported_by"] = "launcher"
    return trace


def build_envelope(
    *,
    session_id: str,
    sender: str,
    kind: str,
    summary: str,
    body: Any,
    capability: str | None = None,
    evidence: Any = None,
    next_step: str | None = None,
    task: str | None = None,
    envelope_id: str | None = None,
    created_at: str | None = None,
    correlation_id: str | None = None,
    duration_ms: Any = None,
    tokens_in: Any = None,
    tokens_out: Any = None,
) -> dict[str, Any]:
    """Validate the parts of an envelope and assemble it. Raises `BusError`."""
    if not UUID_PATTERN.match(str(session_id or "")):
        raise BusError(f"session id must be a UUID, got {session_id!r}")

    sender = str(sender or "").strip()
    if not AGENT_NAME_PATTERN.match(sender):
        raise BusError(
            f"sender must be a lowercase-hyphen agent name, got {sender!r}"
        )

    if kind not in ENVELOPE_KINDS:
        if kind is None:
            # `--kind` is optional only because a --body-file carrying a full
            # envelope names its own. Saying "unknown kind None" left the caller
            # guessing which of the two paths they were on.
            raise BusError(
                "no kind: pass --kind "
                f"({', '.join(ENVELOPE_KINDS)}), or a --body-file whose envelope "
                "already names one"
            )
        raise BusError(
            f"unknown kind {kind!r}; expected one of {', '.join(ENVELOPE_KINDS)}"
        )

    summary = str(summary or "").strip()
    if not summary:
        raise BusError("summary is required")
    if "\n" in summary or "\r" in summary:
        raise BusError("summary must be a single line")
    if len(summary) > MAX_SUMMARY_CHARS:
        raise BusError(
            f"summary is {len(summary)} characters, limit is {MAX_SUMMARY_CHARS}"
        )

    if not isinstance(body, dict):
        raise BusError("body must be a JSON object")
    encoded = json.dumps(body, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_BODY_BYTES:
        raise BusError(
            f"body is {len(encoded.encode('utf-8'))} bytes, limit is {MAX_BODY_BYTES}. "
            "Return conclusions and citations, not file contents."
        )

    if capability is not None and capability not in CAPABILITY_TIERS:
        raise BusError(
            f"unknown capability {capability!r}; expected one of "
            f"{', '.join(sorted(CAPABILITY_TIERS))}"
        )

    envelope: dict[str, Any] = {
        "envelope_version": ENVELOPE_VERSION,
        "id": str(envelope_id or uuid.uuid4()),
        "session_id": str(session_id).lower(),
        "from": sender,
        # A claim about how the sender was launched, recorded for audit. Never a
        # grant: nothing may widen authority because an envelope says so.
        "capability": capability,
        "kind": kind,
        "task": (str(task).strip() or None) if task else None,
        "created_at": created_at or utc_now(),
        "summary": summary,
        "body": body,
        "evidence": normalize_evidence(evidence),
        "next": (str(next_step).strip() or None) if next_step else None,
        # Absent rather than an empty object when nothing was measured: a blank
        # trace and an unmeasured one are different facts.
        "trace": normalize_trace(correlation_id, duration_ms, tokens_in, tokens_out),
    }
    return envelope


def validate_envelope(data: Any, label: str) -> list[str]:
    """Check one envelope read back from disk. Returns human-readable errors."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{label}: not a JSON object"]

    version = data.get("envelope_version")
    if version not in SUPPORTED_ENVELOPE_VERSIONS:
        errors.append(
            f"{label}: envelope_version is {version!r}, "
            f"expected one of {SUPPORTED_ENVELOPE_VERSIONS}"
        )

    expected_keys = {
        "envelope_version",
        "id",
        "session_id",
        "from",
        "capability",
        "kind",
        "task",
        "created_at",
        "summary",
        "body",
        "evidence",
        "next",
        "trace",
    }
    unknown = sorted(set(data) - expected_keys)
    if unknown:
        # An unrecognized key is how an envelope would smuggle a directive past a
        # reader that only looks at the fields it knows about.
        errors.append(f"{label}: unknown envelope keys: {', '.join(unknown)}")

    missing = sorted(key for key in ("id", "session_id", "from", "kind", "summary") if not data.get(key))
    if missing:
        errors.append(f"{label}: missing required fields: {', '.join(missing)}")

    try:
        build_envelope(
            session_id=data.get("session_id", ""),
            sender=data.get("from", ""),
            kind=data.get("kind", ""),
            summary=data.get("summary", ""),
            body=data.get("body"),
            capability=data.get("capability"),
            evidence=data.get("evidence"),
            next_step=data.get("next"),
            task=data.get("task"),
            correlation_id=(data.get("trace") or {}).get("correlation_id"),
            duration_ms=(data.get("trace") or {}).get("duration_ms"),
            tokens_in=((data.get("trace") or {}).get("tokens") or {}).get("input"),
            tokens_out=((data.get("trace") or {}).get("tokens") or {}).get("output"),
        )
    except BusError as exc:
        errors.append(f"{label}: {exc}")
    return errors


def next_sequence(directory: Path) -> int:
    """The next append position, derived from what is on disk.

    Deriving it from the directory rather than tracking it keeps the bus
    stateless: two writers cannot disagree about a counter that does not exist.
    """
    highest = 0
    if directory.is_dir():
        for path in directory.glob("*.json"):
            head = path.name.split("-", 1)[0]
            if head.isdigit():
                highest = max(highest, int(head))
    return highest + 1


def write_envelope(root: Path, envelope: dict[str, Any]) -> Path:
    directory = session_dir(root, envelope["session_id"])
    directory.mkdir(parents=True, exist_ok=True)
    seq = next_sequence(directory)
    short = envelope["id"].split("-")[0]
    target = directory / f"{seq:04d}-{envelope['kind']}-{short}.json"
    if target.exists():
        # Append-only is the point. Never overwrite a record of what was claimed.
        raise BusError(f"envelope already exists: {target}")
    text = json.dumps(envelope, indent=2, ensure_ascii=False) + "\n"
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def read_envelopes(
    root: Path,
    session_id: str | None = None,
    kinds: list[str] | None = None,
) -> list[tuple[Path, Any]]:
    base = bus_root(root)
    if not base.is_dir():
        return []
    if session_id:
        directories = [session_dir(root, session_id)]
    else:
        directories = sorted(path for path in base.iterdir() if path.is_dir())

    found: list[tuple[Path, Any]] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                found.append((path, {"__unreadable__": str(exc)}))
                continue
            if kinds and data.get("kind") not in kinds:
                continue
            found.append((path, data))
    return found


def summarize(path: Path, data: Any, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if isinstance(data, dict) and "__unreadable__" in data:
        return f"[unreadable] {rel}: {data['__unreadable__']}"
    kind = data.get("kind", "?")
    sender = data.get("from", "?")
    capability = data.get("capability") or "unstated"
    return f"[{kind}] {sender} ({capability}) - {data.get('summary', '')}\n    {rel}"


def cmd_schema(args: argparse.Namespace) -> int:
    print(json.dumps(envelope_schema(), indent=2))
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.is_dir():
        fail(f"repository root not found: {root}")

    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.is_file():
            fail(f"body file not found: {body_path}")
        try:
            body = json.loads(body_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"body file is not valid JSON: {exc}")
    elif args.body:
        try:
            body = json.loads(args.body)
        except json.JSONDecodeError as exc:
            fail(f"--body is not valid JSON: {exc}")
    else:
        body = {}

    # A foreground session launched with `--json-schema $(harness_bus.py schema)`
    # returns exactly the envelope payload shape, so it can be posted verbatim.
    if isinstance(body, dict) and set(body) <= set(envelope_schema()["properties"]):
        if "kind" in body and "summary" in body and "body" in body:
            args.kind = args.kind or body["kind"]
            args.summary = args.summary or body["summary"]
            args.evidence = args.evidence or body.get("evidence") or []
            args.next = args.next or body.get("next")
            body = body["body"]

    try:
        envelope = build_envelope(
            session_id=args.session,
            sender=args.sender,
            kind=args.kind,
            summary=args.summary,
            body=body,
            capability=args.capability,
            evidence=list(args.evidence or []),
            next_step=args.next,
            task=args.task,
            correlation_id=args.correlation,
            duration_ms=args.duration_ms,
            tokens_in=args.tokens_in,
            tokens_out=args.tokens_out,
        )
        target = write_envelope(root, envelope)
    except BusError as exc:
        fail(str(exc))

    print(target.relative_to(root).as_posix())
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.is_dir():
        fail(f"repository root not found: {root}")
    try:
        found = read_envelopes(root, args.session, args.kind or None)
    except BusError as exc:
        fail(str(exc))

    if args.correlation:
        wanted = str(args.correlation).strip().lower()
        if not UUID_PATTERN.match(wanted):
            fail(f"correlation id must be a UUID, got {args.correlation!r}")
        found = [
            (path, data)
            for path, data in found
            if isinstance(data, dict)
            and (data.get("trace") or {}).get("correlation_id") == wanted
        ]

    if args.json:
        print(json.dumps([data for _, data in found], indent=2, ensure_ascii=False))
        return 0

    if not found:
        print("no envelopes")
        return 0
    for path, data in found:
        print(summarize(path, data, root))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.is_dir():
        fail(f"repository root not found: {root}")
    try:
        found = read_envelopes(root)
    except BusError as exc:
        fail(str(exc))

    errors: list[str] = []
    for path, data in found:
        label = path.relative_to(root).as_posix()
        if isinstance(data, dict) and "__unreadable__" in data:
            errors.append(f"{label}: {data['__unreadable__']}")
            continue
        errors.extend(validate_envelope(data, label))

    if errors:
        print("BUS INVALID")
        for line in errors:
            print(f"  - {line}")
        return 1
    print(f"BUS OK ({len(found)} envelopes)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Typed message envelopes for agent handoff under .ai/bus/."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    schema = sub.add_parser(
        "schema",
        help="Print the envelope JSON Schema, for `claude -p --json-schema`.",
    )
    schema.set_defaults(func=cmd_schema)

    post = sub.add_parser("post", help="Append an envelope to a session mailbox.")
    post.add_argument("--root", default=".", help="Repository root (default: .)")
    post.add_argument("--session", required=True, help="Session UUID")
    post.add_argument("--from", dest="sender", required=True, help="Sending agent name")
    post.add_argument(
        "--kind",
        choices=list(ENVELOPE_KINDS),
        help="Required unless --body-file carries a full envelope, which names its own",
    )
    post.add_argument("--summary", help="One-line summary")
    post.add_argument("--body", help="Body as an inline JSON object")
    post.add_argument("--body-file", help="Body as a JSON file")
    post.add_argument(
        "--capability",
        choices=sorted(CAPABILITY_TIERS),
        help="Tier the sender ran under. Recorded for audit; never a grant.",
    )
    post.add_argument("--evidence", action="append", default=[], help="Repeatable citation")
    post.add_argument("--next", help="Suggested next step")
    post.add_argument("--task", help="Contract this envelope answers, e.g. a spec path")
    post.add_argument(
        "--correlation",
        help=(
            "UUID tying every envelope from one unit of work together, across "
            "agents and sessions. Reuse it for each leg of the same task."
        ),
    )
    post.add_argument(
        "--duration-ms",
        type=int,
        help="How long the run took. Supplied by whoever launched it, not by the agent.",
    )
    post.add_argument("--tokens-in", type=int, help="Input tokens the run consumed.")
    post.add_argument("--tokens-out", type=int, help="Output tokens the run produced.")
    post.set_defaults(func=cmd_post)

    read = sub.add_parser("read", help="Read envelopes, oldest first.")
    read.add_argument("--root", default=".", help="Repository root (default: .)")
    read.add_argument("--session", help="Limit to one session UUID")
    read.add_argument(
        "--kind", action="append", choices=list(ENVELOPE_KINDS), help="Repeatable filter"
    )
    read.add_argument(
        "--correlation",
        help="Limit to one unit of work, across every agent that touched it.",
    )
    read.add_argument("--json", action="store_true", help="Emit raw JSON")
    read.set_defaults(func=cmd_read)

    validate = sub.add_parser("validate", help="Check every envelope on disk.")
    validate.add_argument("--root", default=".", help="Repository root (default: .)")
    validate.set_defaults(func=cmd_validate)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
