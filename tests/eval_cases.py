"""Parse and validate `claude plugin eval` case files without a YAML dependency.

`claude plugin eval` is in early access and enabled per organization, so on most
machines - including CI - the runner refuses to execute and the eval suite gets no
coverage at all. That is the worst state for a set of files to be in: authored, shipped,
and never parsed by anything. This module closes that gap. It reads every `case.yaml`
and checks it against the schema the runner enforces, so a typo in a grader type or an
unbalanced regex fails on the next push rather than on whatever future day the gate
opens.

The parser is deliberately a small strict subset of YAML rather than a permissive one.
The repository ships no third-party dependencies and adding PyYAML for a test would
trade that away, so the subset is hand-written - and a hand-written parser that guesses
is far worse than no parser, because it validates something other than what the runner
will read. Every construct outside the subset is therefore a hard error. If a future
case needs anchors, flow mappings, or multiple documents, this raises instead of
quietly parsing them wrong.

The schema mirrors the runner's own definition, which is authoritative and lives in the
Claude Code binary, not in a published document. It was read out of the bundle rather
than inferred from examples. When the runner's `schema_version` moves past 1.x this
will need revisiting; `MAX_SCHEMA_MAJOR` is where that shows up.
"""

from __future__ import annotations

import re
from pathlib import Path

MAX_SCHEMA_MAJOR = 1

GRADER_TYPES = ("regex", "tool_order", "tool_used", "file_exists", "llm", "baseline")
TARGETS = ("trace", "last_message", "files", "mock_calls")
ARMS = ("with-only", "both")
MATCH_LITERALS = ("contains", "not_contains")
JS_REGEX_FLAGS = set("dgimsuvy")

# Gated tools need an operator grant on the command line; a case that names one in
# `allowed_tools` without the grant reports a notice instead of running.
GATED_TOOLS = ("Bash", "Write", "Edit", "WebFetch")


class EvalCaseError(Exception):
    """A case file is malformed, or uses YAML this parser refuses to guess at."""


# --------------------------------------------------------------------------- parsing


def _unquote(raw: str, where: str) -> str:
    """Resolve a YAML scalar, including the escapes that matter for regex patterns.

    A grader pattern is written `"\\\\.env"` in the file and must reach the runner as
    `\\.env`. Getting this wrong would validate a different regex than the one that
    ships, which is the specific failure this module exists to prevent.
    """
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        body, out, index = raw[1:-1], [], 0
        while index < len(body):
            char = body[index]
            if char != "\\":
                out.append(char)
                index += 1
                continue
            if index + 1 >= len(body):
                raise EvalCaseError(f"{where}: string ends in a dangling backslash")
            escape = body[index + 1]
            mapped = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(escape)
            if mapped is not None:
                out.append(mapped)
            elif escape in ('"', "\\", "/", "'"):
                out.append(escape)
            else:
                raise EvalCaseError(
                    f"{where}: unsupported escape \\{escape} - this parser handles "
                    'only \\\\ \\" \\/ \\n \\t \\r \\0'
                )
            index += 2
        return "".join(out)
    if raw in ("true", "false"):
        return raw == "true"
    if raw == "null" or raw == "~":
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d*\.\d+", raw):
        return float(raw)
    return raw


def _reject_unsupported(line: str, number: int) -> None:
    stripped = line.strip()
    if "\t" in line:
        raise EvalCaseError(f"line {number}: tab character; YAML indentation must be spaces")
    if stripped in ("---", "..."):
        raise EvalCaseError(f"line {number}: multiple documents are not supported")
    if stripped.startswith(("&", "*", "<<")):
        raise EvalCaseError(f"line {number}: anchors, aliases and merge keys are not supported")
    if stripped.startswith("{") or stripped.endswith("{"):
        raise EvalCaseError(f"line {number}: flow mappings are not supported; use block form")


def _split_key(text: str, number: int):
    """Split `key: value`, ignoring a colon inside a quoted scalar."""
    quote = None
    for index, char in enumerate(text):
        if quote:
            if char == quote and text[index - 1] != "\\":
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        if char == ":" and (index + 1 == len(text) or text[index + 1] in " \t"):
            return text[:index].strip(), text[index + 1 :].strip()
    raise EvalCaseError(f"line {number}: expected 'key: value', got {text!r}")


def _flow_sequence(raw: str, where: str):
    inner = raw[1:-1].strip()
    if not inner:
        return []
    if "[" in inner or "{" in inner:
        raise EvalCaseError(f"{where}: nested flow collections are not supported")
    return [_unquote(part.strip(), where) for part in inner.split(",") if part.strip()]


def _parse_block(lines, start: int, indent: int):
    """Parse one block at `indent`, returning (value, index of first unconsumed line)."""
    index = start
    mapping, sequence = {}, []

    while index < len(lines):
        number, raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        _reject_unsupported(raw, number)
        current = len(raw) - len(raw.lstrip(" "))
        if current < indent:
            break
        if current > indent:
            raise EvalCaseError(f"line {number}: unexpected indentation")

        body = raw.strip()

        if body.startswith("- "):
            if mapping:
                raise EvalCaseError(f"line {number}: a list item inside a mapping")
            item_indent = current + 2
            # Re-feed the item's first line at the item's own indentation so a
            # `- key: value` opening and its continuation lines parse as one mapping.
            rest = [(number, " " * item_indent + body[2:])] + lines[index + 1 :]
            value, consumed = _parse_block(rest, 0, item_indent)
            sequence.append(value)
            index += consumed
            continue

        if sequence:
            raise EvalCaseError(f"line {number}: a mapping key inside a list")

        key, value = _split_key(body, number)
        if key in mapping:
            raise EvalCaseError(f"line {number}: duplicate key {key!r}")

        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            block, index = [], index + 1
            while index < len(lines):
                _, text = lines[index]
                if text.strip() and len(text) - len(text.lstrip(" ")) <= current:
                    break
                block.append(text[current + 2 :] if text.strip() else "")
                index += 1
            if value.startswith("|"):
                joined = "\n".join(block).rstrip() + "\n"
            else:
                paragraphs, run = [], []
                for text in block:
                    if text.strip():
                        run.append(text.strip())
                    else:
                        paragraphs.append(" ".join(run))
                        run = []
                paragraphs.append(" ".join(run))
                joined = "\n".join(paragraphs).strip() + "\n"
            mapping[key] = joined
            continue

        if value == "":
            child, consumed = _parse_block(lines, index + 1, current + 2)
            mapping[key] = child
            index += 1 + consumed
            continue

        if value.startswith("["):
            if not value.endswith("]"):
                raise EvalCaseError(f"line {number}: unterminated flow sequence")
            mapping[key] = _flow_sequence(value, f"line {number}")
            index += 1
            continue

        # A flow mapping reaches here as a plain scalar and would be accepted as the
        # literal string "{tool: Bash}" - a tool by that name, silently graded against
        # nothing. Refusing to parse is the whole point of a strict subset.
        if value.startswith("{"):
            raise EvalCaseError(f"line {number}: flow mappings are not supported; use block form")
        if value.startswith(("&", "*")):
            raise EvalCaseError(f"line {number}: anchors and aliases are not supported")

        mapping[key] = _unquote(value, f"line {number}")
        index += 1

    if mapping and sequence:
        raise EvalCaseError(f"line {lines[start][0] if start < len(lines) else '?'}: mixed block")
    return (sequence if sequence else mapping), index - start


def load(text: str):
    """Parse the strict YAML subset these case files are written in."""
    lines = list(enumerate(text.replace("\r\n", "\n").split("\n"), start=1))
    value, _ = _parse_block(lines, 0, 0)
    if not isinstance(value, dict):
        raise EvalCaseError("case.yaml must be a YAML object")
    return value


# ------------------------------------------------------------------------ validation


def _require(value, kinds, where: str):
    if not isinstance(value, kinds) or isinstance(value, bool) and bool not in (kinds,):
        names = kinds.__name__ if isinstance(kinds, type) else "/".join(k.__name__ for k in kinds)
        raise EvalCaseError(f"{where}: expected {names}, got {type(value).__name__}")
    return value


def _check_regex(pattern: str, where: str) -> None:
    """Catch structural regex damage.

    The runner compiles these as JavaScript regexes and Python's dialect is not
    identical, so this cannot prove a pattern means the same thing in both. It does
    reliably catch the mistakes that actually happen in a YAML file: an unbalanced
    group, a dangling quantifier, an unterminated class.
    """
    try:
        re.compile(pattern)
    except re.error as error:
        raise EvalCaseError(f"{where}: not a valid regex ({error})") from error


def _check_target(value, where: str) -> None:
    if isinstance(value, dict):
        if value.get("source") != "file" or "path" not in value:
            raise EvalCaseError(f"{where}: a mapping target must be {{source: file, path: ...}}")
        return
    if value not in TARGETS:
        raise EvalCaseError(f"{where}: must be one of {', '.join(TARGETS)}, or a file source")


def _check_tool_ref(value, where: str) -> None:
    if isinstance(value, str):
        return
    _require(value, dict, where)
    unknown = set(value) - {"tool", "input_match"}
    if unknown:
        raise EvalCaseError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}")
    if "tool" not in value:
        raise EvalCaseError(f"{where}: missing 'tool'")
    if "input_match" in value:
        _check_regex(value["input_match"], f"{where}.input_match")


_GRADER_KEYS = {
    "regex": ({"name", "pattern"}, {"target", "flags", "match", "weight", "arm"}),
    "tool_order": ({"name", "before", "after"}, {"weight", "arm"}),
    "tool_used": ({"name", "tool"}, {"input_match", "min", "max", "weight", "arm"}),
    "file_exists": ({"name", "path"}, {"exists", "weight", "arm"}),
    "llm": ({"name", "criteria"}, {"focus", "weight", "arm"}),
    "baseline": ({"name", "baseline_file", "criteria"}, {"weight", "arm"}),
}


def _check_grader(grader, where: str) -> str:
    _require(grader, dict, where)
    kind = grader.get("type")
    if kind not in GRADER_TYPES:
        raise EvalCaseError(f"{where}: type must be one of {', '.join(GRADER_TYPES)}, got {kind!r}")

    required, optional = _GRADER_KEYS[kind]
    allowed = required | optional | {"type"}
    unknown = set(grader) - allowed
    if unknown:
        raise EvalCaseError(f"{where}: unknown key(s) {', '.join(sorted(unknown))} for type {kind}")
    missing = required - set(grader)
    if missing:
        raise EvalCaseError(f"{where}: missing {', '.join(sorted(missing))} for type {kind}")

    name = _require(grader["name"], str, f"{where}.name")
    if "weight" in grader and not (isinstance(grader["weight"], (int, float)) and grader["weight"] > 0):
        raise EvalCaseError(f"{where}.weight: must be a positive number")
    if "arm" in grader and grader["arm"] not in ARMS:
        raise EvalCaseError(f"{where}.arm: must be one of {', '.join(ARMS)}")

    if kind == "regex":
        _check_regex(grader["pattern"], f"{where}.pattern")
        _check_target(grader.get("target", "last_message"), f"{where}.target")
        flags = grader.get("flags", "")
        if set(str(flags)) - JS_REGEX_FLAGS:
            raise EvalCaseError(f"{where}.flags: must be JS RegExp flags (d g i m s u v y)")
        match = grader.get("match", "contains")
        if match not in MATCH_LITERALS and not re.fullmatch(r"count:\d+", str(match)):
            raise EvalCaseError(f"{where}.match: must be contains | not_contains | count:N")
    elif kind == "tool_order":
        _check_tool_ref(grader["before"], f"{where}.before")
        _check_tool_ref(grader["after"], f"{where}.after")
    elif kind == "tool_used":
        if "input_match" in grader:
            _check_regex(grader["input_match"], f"{where}.input_match")
        for bound in ("min", "max"):
            if bound in grader and not (isinstance(grader[bound], int) and grader[bound] >= 0):
                raise EvalCaseError(f"{where}.{bound}: must be a non-negative integer")
        if "min" in grader and "max" in grader and grader["min"] > grader["max"]:
            raise EvalCaseError(f"{where}: min is greater than max, so it can never pass")
    elif kind == "llm":
        _check_target(grader.get("focus", "last_message"), f"{where}.focus")

    return name


def validate(case, where: str) -> dict:
    """Check one parsed case against the runner's schema. Returns it unchanged."""
    _require(case, dict, where)

    unknown = set(case) - {
        "schema_version", "name", "description", "tags",
        "plugins", "context", "execution", "runs", "graders", "expected_outcome",
    }
    if unknown:
        raise EvalCaseError(f"{where}: unknown top-level key(s) {', '.join(sorted(unknown))}")

    version = case.get("schema_version")
    if not isinstance(version, str):
        raise EvalCaseError(f'{where}: missing required field schema_version (e.g. "1.0")')
    try:
        major = int(version.split(".")[0])
    except ValueError as error:
        raise EvalCaseError(f"{where}: schema_version {version!r} is not a version string") from error
    if major > MAX_SCHEMA_MAJOR:
        raise EvalCaseError(f"{where}: schema_version {version!r} needs a newer runner")

    if not _require(case.get("name"), str, f"{where}.name").strip():
        raise EvalCaseError(f"{where}.name: must not be empty")

    execution = case.get("execution")
    if not isinstance(execution, dict):
        raise EvalCaseError(f"{where}: missing the execution block")
    unknown = set(execution) - {
        "prompt", "max_turns", "timeout_seconds", "model", "allowed_tools",
        "artifact_publish", "growthbook_overrides", "append_system_prompt", "env",
    }
    if unknown:
        raise EvalCaseError(f"{where}.execution: unknown key(s) {', '.join(sorted(unknown))}")
    prompt = execution.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise EvalCaseError(f"{where}: execution.prompt is required")
    if "TODO: describe what the agent should do" in prompt:
        raise EvalCaseError(f"{where}: the prompt is still the blank init template")
    turns = execution.get("max_turns", 10)
    if not isinstance(turns, int) or not 0 < turns <= 200:
        raise EvalCaseError(f"{where}.execution.max_turns: must be 1..200")
    seconds = execution.get("timeout_seconds", 300)
    if not isinstance(seconds, int) or not 0 < seconds <= 3600:
        raise EvalCaseError(f"{where}.execution.timeout_seconds: must be 1..3600")

    runs = case.get("runs", 3)
    if not isinstance(runs, int) or not 0 < runs <= 50:
        raise EvalCaseError(f"{where}.runs: must be 1..50")

    graders = case.get("graders")
    if not isinstance(graders, list) or not graders:
        raise EvalCaseError(f"{where}: at least one grader is required")
    seen = set()
    for index, grader in enumerate(graders):
        name = _check_grader(grader, f"{where}.graders[{index}]")
        if name in seen:
            raise EvalCaseError(f'{where}: duplicate grader name "{name}"')
        seen.add(name)

    context = case.get("context", {})
    if context and not isinstance(context, dict):
        raise EvalCaseError(f"{where}.context: must be a mapping")
    unknown = set(context) - {"scaffold_script", "history_file", "add_dirs"}
    if unknown:
        raise EvalCaseError(f"{where}.context: unknown key(s) {', '.join(sorted(unknown))}")

    return case


def discover(eval_dir: Path):
    """Yield (path, parsed case) for every case under `eval_dir`, results/ excluded."""
    for path in sorted(eval_dir.glob("**/case.yaml")):
        if "results" in path.parts:
            continue
        yield path, load(path.read_text(encoding="utf-8"))
