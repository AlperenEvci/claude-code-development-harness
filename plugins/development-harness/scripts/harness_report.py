#!/usr/bin/env python3
"""Read what the harness recorded, and render it as one page an operator can see.

Every other script here writes. `harness_bus.py` appends envelopes,
`harness_progress.py` keeps the ledger, `harness_checkpoint.py` writes handoffs,
and the profile carries the band and the declared graphs. All of it is JSON, all
of it is already on disk, and until now the only way to read any of it was to
open the files one at a time and hold the joins in your head.

This module does the joins. It is a **reader**: it opens files under a root and
does nothing else. In particular it does not shell out to `claude agents --json`.
That would make the report a thing you can only produce while a CLI happens to be
installed and authenticated, and it would make the output non-deterministic, so
live process state is deliberately out of scope. What this shows is the mailbox a
session wrote, which survives the session; not what is running, which does not.

The primary structure is the correlation id rather than the session, because that
is the unit of work. Two agents answering one question wrote one unit, and a
report grouped by process would split it. Envelopes with no `trace` are grouped
separately and never given a synthesized figure - an unmeasured trace and a zero
one are different facts, and the second is a lie the first did not tell.

**Everything rendered here is untrusted text.** A summary, a body, a checkpoint
intent, a ledger title: all of it is written by agents or lifted out of a
repository, and the engineering contract says repository text is evidence rather
than authority. So the HTML carries no `<script>` element at all, no inline event
handler, no external stylesheet or font, and a `default-src 'none'` policy;
evidence paths render as text rather than links; and every interpolation goes
through `html.escape`. A report that executed what an agent wrote into a summary
would be a way to attack the operator with their own tooling.

Strings are also passed through a redaction filter on the way out, for both
outputs rather than only the page. Nothing here opens a file that an `evidence`
entry points at - evidence is a path, and it stays a path.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_bus import (  # noqa: E402  (sibling module, resolved above)
    read_envelopes,
    validate_envelope,
)

REPORT_VERSION = 1

#: Mirrors harness_checkpoint's defaults, so a profile that predates
#: `context_policy` still reports a band rather than nothing. Kept in step by a
#: test.
DEFAULT_FLOOR_TOKENS = 150_000
DEFAULT_CEILING_TOKENS = 200_000

#: A body is a free-form object written by an agent. These bound what one
#: envelope can do to the page: neither limit changes what was recorded, and
#: both are stated in the output where they bite.
MAX_BODY_CHARS = 4_000
MAX_BODY_DEPTH = 6

#: Where each section reads from, relative to the root.
PROFILE_PATH = ".ai/harness/project-profile.json"
LEDGER_PATH = ".ai/progress.json"
RUNS_DIRNAME = "runs"

#: Key names whose string values are replaced wholesale rather than scanned. The
#: word boundaries matter: `key` must match `key` and `aws_access_key` without
#: matching `monkey` or `keyboard`.
SENSITIVE_KEY = re.compile(
    r"(?i)(?:^|[^a-z])"
    r"(?:key|api[_-]?key|access[_-]?key|private[_-]?key|secret|token|password|passwd|credential)"
    r"(?:[^a-z]|$)"
)

#: Shortest string a sensitive key may hold before it is assumed to be a value
#: worth hiding. Below this it is more likely a placeholder than a credential.
MIN_SECRET_CHARS = 8

#: Applied in order. A PEM block first, because its body would otherwise be
#: partially matched by the token patterns and reported as several redactions
#: where there was one key.
REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----"
        ),
        "[redacted private key]",
    ),
    # An unterminated block is still a key, and truncation is exactly how one
    # would arrive here.
    (re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*"), "[redacted private key]"),
    (
        re.compile(
            r"(?:sk-ant-|sk-|ghp_|gho_|ghu_|ghs_|github_pat_|xoxb-|xoxp-|xoxa-|AKIA)"
            r"[A-Za-z0-9_\-]{16,}"
        ),
        "[redacted]",
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer [redacted]"),
    (re.compile(r"(?i)\bauthorization\s*[:=]\s*\S+"), "Authorization: [redacted]"),
)

EXIT_REFUSED = 2


class ReportError(ValueError):
    """A report that cannot be produced as asked."""


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(EXIT_REFUSED)


def now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------


def redact_text(value: str) -> str:
    """Replace known secret shapes in one string."""
    text = value
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def sensitive_key(key: Any) -> bool:
    return isinstance(key, str) and bool(SENSITIVE_KEY.search(key))


def redact(value: Any, under_sensitive_key: bool = False) -> Any:
    """Redact a whole JSON-shaped value, recursively.

    Applied to the model rather than to the page, so `--json` is redacted on the
    same terms `--out` is. A report that only cleaned the human-readable output
    would leak through the machine-readable one.
    """
    if isinstance(value, str):
        if under_sensitive_key and len(value) > MIN_SECRET_CHARS:
            return "[redacted]"
        return redact_text(value)
    if isinstance(value, dict):
        return {
            key: redact(item, sensitive_key(key)) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def load_json(path: Path) -> tuple[Any, str | None]:
    """Read one JSON file, returning its error rather than raising."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, None
    except (OSError, json.JSONDecodeError) as error:
        return None, str(error)


def load_profile(root: Path) -> dict[str, Any]:
    path = root / PROFILE_PATH
    data, error = load_json(path)
    if error is not None:
        return {"present": False, "error": error, "path": PROFILE_PATH}
    if not isinstance(data, dict):
        return {"present": False, "path": PROFILE_PATH}

    policy = data.get("context_policy")
    policy = policy if isinstance(policy, dict) else {}
    band = policy.get("working_band")
    band = band if isinstance(band, dict) else {}
    floor = band.get("floor_tokens")
    ceiling = band.get("ceiling_tokens")

    return {
        "present": True,
        "path": PROFILE_PATH,
        "project_name": data.get("project_name"),
        "harness_tier": data.get("harness_tier"),
        "transport": data.get("transport"),
        "generator_version": data.get("generator_version"),
        "context_policy": {
            "floor_tokens": floor if isinstance(floor, int) else DEFAULT_FLOOR_TOKENS,
            "ceiling_tokens": (
                ceiling if isinstance(ceiling, int) else DEFAULT_CEILING_TOKENS
            ),
            "on_ceiling": policy.get("on_ceiling"),
            "declared": bool(band),
        },
        "graphs": data.get("graphs") if isinstance(data.get("graphs"), list) else [],
    }


def envelope_entry(path: Path, data: Any, root: Path) -> dict[str, Any]:
    """One envelope, flattened for the view, with its own validation errors."""
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        relative = path.name

    if isinstance(data, dict) and "__unreadable__" in data:
        return {
            "path": relative,
            "readable": False,
            "errors": [f"unreadable: {data['__unreadable__']}"],
            "kind": None,
            "created_at": None,
            "trace": None,
        }

    errors = validate_envelope(data, relative)
    record = data if isinstance(data, dict) else {}
    trace = record.get("trace")
    trace = trace if isinstance(trace, dict) else None

    body = record.get("body")
    body_text, body_truncated, body_flag = format_body(body)

    return {
        "path": relative,
        "readable": True,
        "errors": errors,
        "id": record.get("id"),
        "session_id": record.get("session_id"),
        "from": record.get("from"),
        "capability": record.get("capability"),
        "kind": record.get("kind"),
        "task": record.get("task"),
        "created_at": record.get("created_at"),
        "summary": record.get("summary"),
        "body_text": body_text,
        "body_truncated": body_truncated,
        "body_flag": body_flag,
        "evidence": (
            record.get("evidence") if isinstance(record.get("evidence"), list) else []
        ),
        "next": record.get("next"),
        "trace": trace,
    }


def bound_depth(value: Any, depth: int = 0) -> Any:
    if depth >= MAX_BODY_DEPTH:
        if isinstance(value, dict):
            return "{...}"
        if isinstance(value, list):
            return "[...]"
        return value
    if isinstance(value, dict):
        return {key: bound_depth(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [bound_depth(item, depth + 1) for item in value]
    return value


def format_body(body: Any) -> tuple[str, int, str | None]:
    """Render a body as bounded pretty JSON.

    Returns the text, the number of characters dropped, and a flag when the body
    was not the object the schema says it must be.
    """
    if body is None:
        return "", 0, None

    flag = None
    if not isinstance(body, dict):
        flag = f"body is {type(body).__name__}, not an object"

    try:
        text = json.dumps(bound_depth(body), indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as error:  # pragma: no cover - defensive
        return f"[unrenderable body: {error}]", 0, flag

    if len(text) > MAX_BODY_CHARS:
        dropped = len(text) - MAX_BODY_CHARS
        return text[:MAX_BODY_CHARS], dropped, flag
    return text, 0, flag


def group_work_units(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group envelopes by correlation id; unlinked ones land in their own group.

    Grouping by correlation rather than by session is the point: one unit of work
    may span several sessions, and a view organised by process would split it.
    """
    groups: dict[str | None, list[dict[str, Any]]] = {}
    for entry in entries:
        trace = entry.get("trace") or {}
        correlation = trace.get("correlation_id")
        correlation = correlation if isinstance(correlation, str) else None
        groups.setdefault(correlation, []).append(entry)

    units: list[dict[str, Any]] = []
    for correlation, members in groups.items():
        members.sort(key=lambda item: (str(item.get("created_at") or ""), item["path"]))

        durations = [
            (item.get("trace") or {}).get("duration_ms")
            for item in members
            if isinstance((item.get("trace") or {}).get("duration_ms"), int)
        ]
        tokens_in = 0
        tokens_out = 0
        measured_tokens = False
        for item in members:
            tokens = (item.get("trace") or {}).get("tokens")
            if isinstance(tokens, dict):
                if isinstance(tokens.get("input"), int):
                    tokens_in += tokens["input"]
                    measured_tokens = True
                if isinstance(tokens.get("output"), int):
                    tokens_out += tokens["output"]
                    measured_tokens = True

        stamps = [str(item.get("created_at")) for item in members if item.get("created_at")]
        sessions: list[str] = []
        for item in members:
            session = item.get("session_id")
            if isinstance(session, str) and session not in sessions:
                sessions.append(session)

        kinds: dict[str, int] = {}
        for item in members:
            kind = item.get("kind")
            if isinstance(kind, str):
                kinds[kind] = kinds.get(kind, 0) + 1

        units.append(
            {
                "correlation_id": correlation,
                "linked": correlation is not None,
                "sessions": sessions,
                "envelope_count": len(members),
                "kinds": kinds,
                "started_at": min(stamps) if stamps else None,
                "ended_at": max(stamps) if stamps else None,
                # Absent rather than zero when nothing measured it.
                "duration_ms": sum(durations) if durations else None,
                "tokens": (
                    {"input": tokens_in, "output": tokens_out}
                    if measured_tokens
                    else None
                ),
                "invalid_count": sum(1 for item in members if item["errors"]),
                "envelopes": members,
            }
        )

    # Linked units first, oldest first; the unlinked bucket last, because it is a
    # leftover rather than a unit of work.
    units.sort(
        key=lambda unit: (
            not unit["linked"],
            unit["started_at"] or "",
            unit["correlation_id"] or "",
        )
    )
    return units


def load_ledger(root: Path) -> dict[str, Any]:
    path = root / LEDGER_PATH
    data, error = load_json(path)
    if error is not None:
        return {"present": False, "error": error, "items": [], "path": LEDGER_PATH}
    if not isinstance(data, dict):
        return {"present": False, "items": [], "path": LEDGER_PATH}

    items = data.get("items")
    items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    return {
        "present": True,
        "path": LEDGER_PATH,
        "updated_at": data.get("updated_at"),
        "total": len(items),
        "unproven": sum(1 for item in items if not item.get("passes")),
        "items": items,
    }


def load_checkpoints(root: Path) -> list[dict[str, Any]]:
    base = root / ".ai" / RUNS_DIRNAME
    if not base.is_dir():
        return []

    found: list[dict[str, Any]] = []
    for directory in sorted(base.iterdir(), reverse=True):
        if not directory.is_dir():
            continue
        path = directory / "checkpoint.json"
        if not path.is_file():
            continue
        data, error = load_json(path)
        relative = f".ai/{RUNS_DIRNAME}/{directory.name}/checkpoint.json"
        if error is not None or not isinstance(data, dict):
            found.append({"path": relative, "readable": False, "error": error})
            continue
        record = dict(data)
        record["path"] = relative
        record["readable"] = True
        found.append(record)
    return found


def graph_view(raw: Any, index: int) -> dict[str, Any]:
    """Lay one declared graph out in dependency levels, defensively.

    `harness_graph.py` already normalizes and rejects a malformed graph, but it is
    not one of the scripts installed into a harnessed repository, so this cannot
    import it. That turns out to be the right shape anyway: a validator must
    refuse a cycle, and a view must still draw the graph that has one. So the
    layering here reports what it could not order instead of raising.
    """
    errors: list[str] = []
    if not isinstance(raw, dict):
        return {
            "name": f"graph[{index}]",
            "description": None,
            "nodes": [],
            "levels": [],
            "unordered": [],
            "errors": ["graph is not an object"],
        }

    name = raw.get("name") if isinstance(raw.get("name"), str) else f"graph[{index}]"
    nodes: list[dict[str, Any]] = []
    for position, node in enumerate(raw.get("nodes") or []):
        if not isinstance(node, dict):
            errors.append(f"nodes[{position}] is not an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"nodes[{position}] has no id")
            continue
        depends = node.get("depends_on")
        depends = [dep for dep in depends if isinstance(dep, str)] if isinstance(depends, list) else []
        nodes.append(
            {
                "id": node_id,
                "depends_on": depends,
                "phase": node.get("phase"),
                "label": node.get("label") or node_id,
            }
        )

    known = {node["id"] for node in nodes}
    for node in nodes:
        for dep in node["depends_on"]:
            if dep not in known:
                errors.append(f"{node['id']} depends on unknown node: {dep}")

    remaining = {
        node["id"]: {dep for dep in node["depends_on"] if dep in known} for node in nodes
    }
    levels: list[list[str]] = []
    while remaining:
        ready = sorted(node for node, deps in remaining.items() if not deps)
        if not ready:
            break
        levels.append(ready)
        for node_id in ready:
            del remaining[node_id]
        for deps in remaining.values():
            deps.difference_update(ready)

    unordered = sorted(remaining)
    if unordered:
        errors.append(
            "dependency cycle or unresolvable order among: " + ", ".join(unordered)
        )

    return {
        "name": name,
        "description": raw.get("description"),
        "nodes": nodes,
        "levels": levels,
        "unordered": unordered,
        "errors": errors,
    }


def latest_context(checkpoints: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The most recent checkpoint that actually carries a token figure."""
    for record in checkpoints:
        if not record.get("readable"):
            continue
        context = record.get("context")
        if isinstance(context, dict) and isinstance(
            context.get("reported_used_tokens"), int
        ):
            return {
                "reported_used_tokens": context["reported_used_tokens"],
                "zone": context.get("zone"),
                "measured_by": context.get("measured_by", "caller-reported"),
                "created_at": record.get("created_at"),
                "path": record.get("path"),
            }
    return None


def build_model(root: Path) -> dict[str, Any]:
    """Assemble the whole view. Reads files; runs nothing."""
    profile = load_profile(root)
    entries = [
        envelope_entry(path, data, root) for path, data in read_envelopes(root)
    ]
    checkpoints = load_checkpoints(root)

    model = {
        "report_version": REPORT_VERSION,
        "generated_at": now_text(),
        # The directory name only. An absolute path names the operator's machine
        # and belongs in no artifact that gets shared.
        "repository": root.name,
        "profile": profile,
        "work_units": group_work_units(entries),
        "envelope_total": len(entries),
        "ledger": load_ledger(root),
        "checkpoints": checkpoints,
        "context": latest_context(checkpoints),
        "graphs": [
            graph_view(raw, index) for index, raw in enumerate(profile.get("graphs") or [])
        ],
        "sources": {
            "profile": (root / PROFILE_PATH).is_file(),
            "bus": (root / ".ai" / "bus").is_dir(),
            "ledger": (root / LEDGER_PATH).is_file(),
            "runs": (root / ".ai" / RUNS_DIRNAME).is_dir(),
        },
    }
    return redact(model)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def esc(value: Any) -> str:
    """The only way text reaches the page."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


STYLE = """
:root {
  color-scheme: light dark;
  --bg: #fbfbfa; --fg: #1c1c1a; --muted: #6b6b66; --line: #e2e2dd;
  --card: #ffffff; --accent: #3f6f52; --warn: #8a4b2a; --bar: #dcdcd6;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14140f; --fg: #eceae2; --muted: #9a9a90; --line: #2e2e28;
    --card: #1c1c17; --accent: #7fb894; --warn: #d99a6c; --bar: #2e2e28;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.25rem 4rem; background: var(--bg); color: var(--fg);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 62rem; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 .3rem; }
h2 { font-size: 1.15rem; margin: 2.5rem 0 .75rem; padding-bottom: .35rem;
     border-bottom: 1px solid var(--line); }
h3 { font-size: .98rem; margin: 0 0 .4rem; }
p { margin: .4rem 0; }
.muted { color: var(--muted); font-size: .85rem; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 8px;
        padding: .9rem 1.1rem; margin: .75rem 0; }
.row { display: flex; flex-wrap: wrap; gap: .5rem 1rem; align-items: baseline; }
.tag { display: inline-block; padding: .05rem .5rem; border-radius: 999px;
       border: 1px solid var(--line); font-size: .75rem; color: var(--muted); }
.kind { border-color: var(--accent); color: var(--accent); }
.flag { border-color: var(--warn); color: var(--warn); }
.bar { height: .55rem; background: var(--bar); border-radius: 999px; overflow: hidden;
       margin: .5rem 0 .25rem; }
.bar > span { display: block; height: 100%; background: var(--accent); }
.bar.over > span { background: var(--warn); }
pre { background: var(--bg); border: 1px solid var(--line); border-radius: 6px;
      padding: .6rem .7rem; overflow-x: auto; font-size: .8rem; margin: .5rem 0 0; }
ul { margin: .35rem 0; padding-left: 1.2rem; }
li { margin: .15rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .87rem; }
th, td { text-align: left; padding: .4rem .5rem; border-bottom: 1px solid var(--line);
         vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: .78rem;
     text-transform: uppercase; letter-spacing: .03em; }
.levels { display: flex; gap: .75rem; overflow-x: auto; padding-bottom: .4rem; }
.level { min-width: 9rem; border: 1px dashed var(--line); border-radius: 6px;
         padding: .5rem; }
.node { background: var(--card); border: 1px solid var(--line); border-radius: 5px;
        padding: .25rem .45rem; margin: .25rem 0; font-size: .82rem; }
.empty { color: var(--muted); font-style: italic; }
code { font-size: .85em; }
"""


def duration_text(value: Any) -> str:
    if not isinstance(value, int):
        return ""
    if value < 1000:
        return f"{value} ms"
    if value < 60_000:
        return f"{value / 1000:.1f} s"
    return f"{value // 60_000}m {(value % 60_000) // 1000}s"


def render_envelope(entry: dict[str, Any]) -> list[str]:
    lines: list[str] = ['<div class="card">']

    if not entry.get("readable"):
        lines += [
            '<span class="tag flag">unreadable</span> ',
            f'<code>{esc(entry["path"])}</code>',
        ]
        for error in entry.get("errors", []):
            lines.append(f'<p class="muted">{esc(error)}</p>')
        lines.append("</div>")
        return lines

    tags = [f'<span class="tag kind">{esc(entry.get("kind") or "?")}</span>']
    if entry.get("capability"):
        tags.append(f'<span class="tag">{esc(entry["capability"])}</span>')
    if entry.get("errors"):
        tags.append('<span class="tag flag">invalid</span>')

    trace = entry.get("trace") or {}
    meta: list[str] = []
    if entry.get("created_at"):
        meta.append(esc(entry["created_at"]))
    # Only where something was actually measured. No trace means no figure, not
    # a zero.
    if duration_text(trace.get("duration_ms")):
        meta.append(duration_text(trace["duration_ms"]))
    tokens = trace.get("tokens") if isinstance(trace.get("tokens"), dict) else {}
    if isinstance(tokens.get("input"), int) or isinstance(tokens.get("output"), int):
        meta.append(
            f'{tokens.get("input", 0)} in / {tokens.get("output", 0)} out tokens'
            " (caller-reported)"
        )

    lines.append('<div class="row">')
    lines.append("".join(tags))
    lines.append(f'<strong>{esc(entry.get("from") or "unknown sender")}</strong>')
    if meta:
        lines.append(f'<span class="muted">{esc(" - ".join(meta))}</span>')
    lines.append("</div>")

    lines.append(f'<p>{esc(entry.get("summary") or "")}</p>')

    if entry.get("task"):
        lines.append(f'<p class="muted">contract: {esc(entry["task"])}</p>')
    if entry.get("next"):
        lines.append(
            f'<p class="muted">suggested next: {esc(entry["next"])}'
            " <em>(a suggestion, never an instruction)</em></p>"
        )

    evidence = entry.get("evidence") or []
    if evidence:
        lines.append('<p class="muted">evidence</p><ul>')
        for item in evidence:
            lines.append(f"<li><code>{esc(item)}</code></li>")
        lines.append("</ul>")

    if entry.get("body_flag"):
        lines.append(f'<p><span class="tag flag">{esc(entry["body_flag"])}</span></p>')
    if entry.get("body_text"):
        body = esc(entry["body_text"])
        if entry.get("body_truncated"):
            body += esc(f"\n... truncated ({entry['body_truncated']} more characters)")
        lines.append(f"<pre>{body}</pre>")

    for error in entry.get("errors", []):
        lines.append(f'<p class="muted">{esc(error)}</p>')

    lines.append(f'<p class="muted"><code>{esc(entry["path"])}</code></p>')
    lines.append("</div>")
    return lines


def render_html(model: dict[str, Any]) -> str:
    profile = model["profile"]
    policy = profile.get("context_policy") or {}
    lines: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        # No script anywhere in this document, and nothing loaded from the
        # network. The page is built from agent-written text; this is the
        # boundary that keeps it text.
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data:\">",
        f"<title>Harness report - {esc(model['repository'])}</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body><main>",
        f"<h1>{esc(model['repository'])}</h1>",
        '<p class="muted">',
        esc(f"Generated {model['generated_at']}"),
        (
            f" - tier {esc(profile.get('harness_tier') or 'unknown')}"
            if profile.get("present")
            else " - no project profile found"
        ),
        "</p>",
        '<p class="muted">A view of what the harness recorded: mailboxes, the ledger,'
        " checkpoints, and the declared graphs. It reads files only, so it shows what"
        " sessions wrote rather than what is running now.</p>",
    ]

    # --- Context budget -------------------------------------------------
    lines.append('<h2 id="context">Context budget</h2>')
    floor = policy.get("floor_tokens", DEFAULT_FLOOR_TOKENS)
    ceiling = policy.get("ceiling_tokens", DEFAULT_CEILING_TOKENS)
    lines.append('<div class="card">')
    lines.append(
        f'<p>Working band <strong>{esc(f"{floor:,}")}</strong> to '
        f'<strong>{esc(f"{ceiling:,}")}</strong> tokens'
        + (
            f', on ceiling: <code>{esc(policy["on_ceiling"])}</code>'
            if policy.get("on_ceiling")
            else ""
        )
        + (
            ""
            if policy.get("declared")
            else ' <span class="tag">defaulted; the profile declares no band</span>'
        )
        + "</p>"
    )
    context = model.get("context")
    if context:
        used = context["reported_used_tokens"]
        pct = min(100, int(used * 100 / ceiling)) if ceiling else 0
        over = " over" if context.get("zone") == "over-ceiling" else ""
        lines.append(f'<div class="bar{over}"><span style="width:{pct}%"></span></div>')
        lines.append(
            f'<p class="muted">{esc(f"{used:,}")} tokens reported'
            f' - zone <strong>{esc(context.get("zone") or "unknown")}</strong>'
            f' - {esc(context.get("measured_by") or "caller-reported")},'
            " nothing here measured it</p>"
        )
        lines.append(f'<p class="muted"><code>{esc(context["path"])}</code></p>')
    else:
        lines.append(
            '<p class="empty">No checkpoint carries a reported token count.</p>'
        )
    lines.append("</div>")

    # --- Work units -----------------------------------------------------
    units = model["work_units"]
    lines.append('<h2 id="work">Work units</h2>')
    if not units:
        lines.append('<p class="empty">No envelopes under <code>.ai/bus/</code>.</p>')
    for unit in units:
        title = (
            f"correlation {unit['correlation_id']}"
            if unit["linked"]
            else "unlinked envelopes"
        )
        lines.append('<div class="card">')
        lines.append(f"<h3>{esc(title)}</h3>")
        facts = [f"{unit['envelope_count']} envelope(s)"]
        if unit["sessions"]:
            facts.append(f"{len(unit['sessions'])} session(s)")
        if unit["started_at"]:
            facts.append(f"from {unit['started_at']}")
        if unit["ended_at"] and unit["ended_at"] != unit["started_at"]:
            facts.append(f"to {unit['ended_at']}")
        if unit["duration_ms"] is not None:
            facts.append(f"{duration_text(unit['duration_ms'])} measured")
        if unit["tokens"]:
            facts.append(
                f"{unit['tokens']['input']} in / {unit['tokens']['output']} out tokens"
            )
        if unit["invalid_count"]:
            facts.append(f"{unit['invalid_count']} invalid")
        lines.append(f'<p class="muted">{esc(" - ".join(facts))}</p>')
        if not unit["linked"]:
            lines.append(
                '<p class="muted">These carry no <code>trace</code>. Nothing measured'
                " them, so no duration or token figure is shown.</p>"
            )
        for entry in unit["envelopes"]:
            lines += render_envelope(entry)
        lines.append("</div>")

    # --- Ledger ---------------------------------------------------------
    ledger = model["ledger"]
    lines.append('<h2 id="ledger">Progress ledger</h2>')
    if not ledger.get("present"):
        lines.append(
            f'<p class="empty">No ledger at <code>{esc(LEDGER_PATH)}</code>.</p>'
        )
    else:
        lines.append(
            f'<p class="muted">{ledger["unproven"]} of {ledger["total"]} unproven'
            f' - updated {esc(ledger.get("updated_at"))}</p>'
        )
        lines.append(
            "<table><thead><tr><th>State</th><th>Item</th><th>Verify</th>"
            "<th>Evidence</th></tr></thead><tbody>"
        )
        for item in ledger["items"]:
            state = "passing" if item.get("passes") else "unproven"
            css = "tag" if item.get("passes") else "tag flag"
            lines.append(
                f'<tr><td><span class="{css}">{esc(state)}</span></td>'
                f'<td><strong>{esc(item.get("id"))}</strong><br>'
                f'<span class="muted">{esc(item.get("title"))}</span></td>'
                f'<td><code>{esc(item.get("verify") or "")}</code></td>'
                f'<td class="muted">{esc(item.get("evidence") or "")}</td></tr>'
            )
        lines.append("</tbody></table>")

    # --- Checkpoints ----------------------------------------------------
    lines.append('<h2 id="checkpoints">Checkpoints</h2>')
    checkpoints = model["checkpoints"]
    if not checkpoints:
        lines.append('<p class="empty">No checkpoints under <code>.ai/runs/</code>.</p>')
    for record in checkpoints:
        lines.append('<div class="card">')
        if not record.get("readable"):
            lines.append(
                f'<span class="tag flag">unreadable</span> '
                f'<code>{esc(record["path"])}</code>'
            )
            lines.append("</div>")
            continue
        lines.append(f'<h3>{esc(record.get("intent"))}</h3>')
        lines.append(f'<p class="muted">{esc(record.get("created_at"))}</p>')
        steps = record.get("next_steps") or []
        if steps:
            lines.append("<p>Next steps</p><ul>")
            for step in steps:
                lines.append(f"<li>{esc(step)}</li>")
            lines.append("</ul>")
        artifacts = record.get("artifacts") or []
        if artifacts:
            lines.append('<p class="muted">Artifacts (paths only)</p><ul>')
            for artifact in artifacts:
                lines.append(f"<li><code>{esc(artifact)}</code></li>")
            lines.append("</ul>")
        if record.get("note"):
            lines.append(f'<p class="muted">{esc(record["note"])}</p>')
        lines.append(f'<p class="muted"><code>{esc(record["path"])}</code></p>')
        lines.append("</div>")

    # --- Graphs ---------------------------------------------------------
    lines.append('<h2 id="graphs">Work graphs</h2>')
    graphs = model["graphs"]
    if not graphs:
        lines.append('<p class="empty">The profile declares no graphs.</p>')
    for graph in graphs:
        lines.append('<div class="card">')
        lines.append(f'<h3>{esc(graph["name"])}</h3>')
        if graph.get("description"):
            lines.append(f'<p class="muted">{esc(graph["description"])}</p>')
        if graph["levels"]:
            lines.append('<div class="levels">')
            for index, level in enumerate(graph["levels"]):
                lines.append(f'<div class="level"><span class="tag">level {index}</span>')
                for node_id in level:
                    lines.append(f'<div class="node">{esc(node_id)}</div>')
                lines.append("</div>")
            lines.append("</div>")
        if graph["unordered"]:
            lines.append('<div class="levels"><div class="level">')
            lines.append('<span class="tag flag">unordered</span>')
            for node_id in graph["unordered"]:
                lines.append(f'<div class="node">{esc(node_id)}</div>')
            lines.append("</div></div>")
        for error in graph["errors"]:
            lines.append(f'<p><span class="tag flag">{esc(error)}</span></p>')
        lines.append("</div>")

    lines += ["</main></body>", "</html>", ""]
    return "\n".join(lines)


def render_text(model: dict[str, Any]) -> str:
    profile = model["profile"]
    ledger = model["ledger"]
    out = [
        f"{model['repository']} - harness report {model['generated_at']}",
        f"tier: {profile.get('harness_tier') or 'unknown'}",
        "",
        f"work units: {len(model['work_units'])} "
        f"({model['envelope_total']} envelope(s))",
    ]
    for unit in model["work_units"]:
        label = unit["correlation_id"] or "unlinked"
        out.append(f"  {label}: {unit['envelope_count']} envelope(s)")
        for entry in unit["envelopes"]:
            kind = entry.get("kind") or "?"
            sender = entry.get("from") or "?"
            summary = entry.get("summary") or ""
            flag = " [invalid]" if entry.get("errors") else ""
            out.append(f"    [{kind}] {sender}{flag} - {summary}")

    if ledger.get("present"):
        out += ["", f"ledger: {ledger['unproven']} of {ledger['total']} unproven"]
    else:
        out += ["", "ledger: none"]

    context = model.get("context")
    if context:
        out.append(
            f"context: {context['reported_used_tokens']} tokens reported "
            f"({context.get('zone')}), caller-reported"
        )
    else:
        out.append("context: no reported token count")

    out.append(f"checkpoints: {len(model['checkpoints'])}")
    out.append(f"graphs: {len(model['graphs'])}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def refuse_symlinks(path: Path, root: Path) -> None:
    """Refuse to write through a symlink, the way the rest of the harness does.

    A symlinked output path would place the file somewhere the operator did not
    choose, and this one is meant to be handed to other people.
    """
    current = path
    while True:
        if current.is_symlink():
            raise ReportError(f"refusing to write through a symlink: {current}")
        if current == root or current.parent == current:
            return
        current = current.parent


def write_output(path: Path, text: str, root: Path, force: bool) -> None:
    if path.exists() and not force:
        raise ReportError(
            f"{path} already exists. Pass --force to overwrite it; this tool never "
            "overwrites silently."
        )
    refuse_symlinks(path.parent, root)
    if path.is_symlink():
        raise ReportError(f"refusing to write through a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Render what the harness recorded: work units, the ledger, checkpoints, "
            "the context budget, and the declared graphs. Reads files only."
        )
    )
    parser.add_argument("--root", default=".", help="Repository root (default: .)")
    parser.add_argument(
        "--json", action="store_true", help="Emit the whole model as JSON."
    )
    parser.add_argument(
        "--out",
        help="Write a self-contained HTML report to this path instead of stdout.",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite the --out path if it exists."
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        fail(f"not a directory: {args.root}")

    try:
        model = build_model(root)
        if args.out:
            write_output(Path(args.out).resolve(), render_html(model), root, args.force)
            print(f"wrote {args.out}")
        elif args.json:
            print(json.dumps(model, indent=2, ensure_ascii=False))
        else:
            sys.stdout.write(render_text(model))
    except ReportError as error:
        fail(str(error))

    raise SystemExit(0)


if __name__ == "__main__":
    main()
