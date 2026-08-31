#!/usr/bin/env python3
"""Validate harness work graphs and compute a deterministic execution plan.

A graph is a directed acyclic graph of agent work. Nodes sharing a topological
level have no dependency on one another and may run in parallel; levels run in
order.

A node may loop, but only with both an explicit termination condition and a hard
iteration cap, so a generated workflow cannot spin forever.

This module is imported by render_harness.py and is also runnable on its own so
an installed harness can check a graph before anything is generated from it.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

MIN_LOOP_ITERATIONS = 2
MAX_LOOP_ITERATIONS = 20
MAX_NODES = 40

NAME_PATTERN = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class GraphError(ValueError):
    """Raised when a graph specification is not usable."""


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def slugify(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower())
    return text.strip("-")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphError(f"{label} must be a non-empty string")
    return value.strip()


def normalize_node(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GraphError(f"{label} must be an object")

    node_id = slugify(raw.get("id", ""))
    if not node_id or not NAME_PATTERN.match(node_id):
        raise GraphError(f"{label}.id must be a non-empty kebab-case identifier")

    prompt = _text(raw.get("prompt"), f"{label}.prompt")

    depends_on_raw = raw.get("depends_on", [])
    if not isinstance(depends_on_raw, list):
        raise GraphError(f"{label}.depends_on must be an array")
    depends_on: list[str] = []
    for dep in depends_on_raw:
        dep_id = slugify(dep)
        if not dep_id:
            raise GraphError(f"{label}.depends_on contains an empty identifier")
        if dep_id == node_id:
            raise GraphError(f"{label}.depends_on must not contain the node itself")
        if dep_id not in depends_on:
            depends_on.append(dep_id)

    agent = raw.get("agent")
    agent = slugify(agent) if agent else ""

    phase = raw.get("phase")
    phase = _text(phase, f"{label}.phase") if phase else ""

    # Loop semantics: a termination condition and a cap are required together.
    repeat_until = raw.get("repeat_until")
    max_iterations = raw.get("max_iterations")

    if repeat_until is not None and not (
        isinstance(repeat_until, str) and repeat_until.strip()
    ):
        raise GraphError(f"{label}.repeat_until must be a non-empty string when present")

    if max_iterations is not None and repeat_until is None:
        raise GraphError(
            f"{label} sets max_iterations without repeat_until; "
            "a loop needs an explicit termination condition"
        )

    if repeat_until is not None:
        if max_iterations is None:
            raise GraphError(
                f"{label} sets repeat_until without max_iterations; "
                "a loop needs a hard iteration cap"
            )
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
            raise GraphError(f"{label}.max_iterations must be an integer")
        if max_iterations < MIN_LOOP_ITERATIONS or max_iterations > MAX_LOOP_ITERATIONS:
            raise GraphError(
                f"{label}.max_iterations must be between "
                f"{MIN_LOOP_ITERATIONS} and {MAX_LOOP_ITERATIONS}"
            )
        repeat_until = repeat_until.strip()

    return {
        "id": node_id,
        "prompt": prompt,
        "depends_on": depends_on,
        "agent": agent,
        "phase": phase,
        "repeat_until": repeat_until,
        "max_iterations": max_iterations,
    }


def topological_levels(nodes: list[dict[str, Any]]) -> list[list[str]]:
    """Group node ids into levels. Raises GraphError on a cycle."""
    remaining = {node["id"]: set(node["depends_on"]) for node in nodes}
    levels: list[list[str]] = []

    while remaining:
        ready = sorted(node for node, deps in remaining.items() if not deps)
        if not ready:
            stuck = ", ".join(sorted(remaining))
            raise GraphError(
                f"graph contains a dependency cycle among these nodes: {stuck}"
            )
        levels.append(ready)
        for node in ready:
            del remaining[node]
        for deps in remaining.values():
            deps.difference_update(ready)

    return levels


def normalize_graph(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GraphError(f"{label} must be an object")

    name = slugify(raw.get("name", ""))
    if not name or not NAME_PATTERN.match(name):
        raise GraphError(f"{label}.name must be a non-empty kebab-case identifier")

    description = _text(raw.get("description"), f"{label}.description")

    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise GraphError(f"{label}.nodes must contain at least one node")
    if len(raw_nodes) > MAX_NODES:
        raise GraphError(f"{label}.nodes must not exceed {MAX_NODES} nodes")

    nodes = [
        normalize_node(node, f"{label}.nodes[{index}]")
        for index, node in enumerate(raw_nodes)
    ]

    seen: set[str] = set()
    for node in nodes:
        if node["id"] in seen:
            raise GraphError(f"{label} has a duplicate node id: {node['id']}")
        seen.add(node["id"])

    for node in nodes:
        for dep in node["depends_on"]:
            if dep not in seen:
                raise GraphError(
                    f"{label}.nodes[{node['id']}] depends on unknown node: {dep}"
                )

    levels = topological_levels(nodes)

    phases: list[str] = []
    for node in nodes:
        if node["phase"] and node["phase"] not in phases:
            phases.append(node["phase"])

    return {
        "name": name,
        "description": description,
        "nodes": nodes,
        "levels": levels,
        "phases": phases,
    }


def normalize_graphs(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GraphError("graphs must be an array")

    graphs = [
        normalize_graph(graph, f"graphs[{index}]") for index, graph in enumerate(value)
    ]

    seen: set[str] = set()
    for graph in graphs:
        if graph["name"] in seen:
            raise GraphError(f"duplicate graph name: {graph['name']}")
        seen.add(graph["name"])

    return graphs


def execution_plan(graph: dict[str, Any]) -> dict[str, Any]:
    by_id = {node["id"]: node for node in graph["nodes"]}
    return {
        "name": graph["name"],
        "phases": graph["phases"],
        "levels": [
            [
                {
                    "id": node_id,
                    "agent": by_id[node_id]["agent"],
                    "phase": by_id[node_id]["phase"],
                    "loops": by_id[node_id]["repeat_until"] is not None,
                    "max_iterations": by_id[node_id]["max_iterations"],
                }
                for node_id in level
            ]
            for level in graph["levels"]
        ],
    }


def js_quoted(text: Any) -> str:
    """Render a JavaScript single-quoted string literal."""
    escaped = str(text).replace("\\", "\\\\").replace("'", "\\'")
    escaped = escaped.replace("\n", "\\n").replace("\r", "")
    return "'" + escaped + "'"


def js_template(text: Any) -> str:
    """Escape text for inclusion inside a JavaScript template literal.

    Interpolation is disabled so a prompt containing ${...} is treated as prose
    rather than executed as an expression.
    """
    escaped = str(text).replace("\\", "\\\\").replace("`", "\\`")
    return escaped.replace("${", "\\${")


def js_var(node_id: str) -> str:
    return "dep_" + node_id.replace("-", "_")


LOOP_SCHEMA_JS = """const LOOP_SCHEMA = {
  type: 'object',
  properties: {
    done: {
      type: 'boolean',
      description: 'True only when the stated termination condition is met.',
    },
    summary: {
      type: 'string',
      description: 'What changed this iteration and what still remains.',
    },
  },
  required: ['done', 'summary'],
}
"""

UPSTREAM_HELPER_JS = """function upstream(pairs) {
  const parts = pairs
    .filter(function (pair) {
      return pair[1] !== null && pair[1] !== undefined
    })
    .map(function (pair) {
      const value = pair[1]
      const body = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
      return '### ' + pair[0] + '\\n' + body
    })
  return parts.length ? '\\n\\n## Upstream results\\n\\n' + parts.join('\\n\\n') : ''
}
"""


def _agent_options(node: dict[str, Any], label: str, extra: str = "") -> str:
    options = ["label: " + label]
    if node["phase"]:
        options.append("phase: " + js_quoted(node["phase"]))
    if node["agent"]:
        options.append("agentType: " + js_quoted(node["agent"]))
    if extra:
        options.append(extra)
    return "{ " + ", ".join(options) + " }"


def _render_node(node: dict[str, Any]) -> list[str]:
    node_id = node["id"]
    lines = ["node[" + js_quoted(node_id) + "] = (async function () {"]

    for dep in node["depends_on"]:
        lines.append(
            "  const " + js_var(dep) + " = await node[" + js_quoted(dep) + "]"
        )

    if node["depends_on"]:
        pairs = ", ".join(
            "[" + js_quoted(dep) + ", " + js_var(dep) + "]" for dep in node["depends_on"]
        )
        lines.append("  const context = upstream([" + pairs + "])")
    else:
        lines.append("  const context = ''")

    prompt = js_template(node["prompt"])

    if node["repeat_until"] is None:
        lines.append("  return await agent(")
        lines.append("    `" + prompt + "${context}`,")
        lines.append("    " + _agent_options(node, js_quoted(node_id)))
        lines.append("  )")
    else:
        cap = node["max_iterations"]
        condition = js_template(node["repeat_until"])
        label = "`" + js_template(node_id) + " ${attempt}/" + str(cap) + "`"
        lines.extend(
            [
                "  let attempt = 0",
                "  let outcome = null",
                "  while (attempt < " + str(cap) + ") {",
                "    attempt += 1",
                "    outcome = await agent(",
                "      `" + prompt + "${context}",
                "",
                "## Termination condition",
                "",
                "Continue until: " + condition,
                "",
                "This is attempt ${attempt} of " + str(cap) + ". Set done to true only when the",
                "condition above actually holds. Do not claim completion to end the loop.`,",
                "      "
                + _agent_options(node, label, "schema: LOOP_SCHEMA"),
                "    )",
                "    if (outcome && outcome.done) break",
                "  }",
                "  if (!(outcome && outcome.done)) {",
                "    log(",
                "      " + js_quoted(node_id + ": stopped at the iteration cap of ")
                + " + " + str(cap) + " +",
                "        " + js_quoted(" without meeting: " + node["repeat_until"]),
                "    )",
                "  }",
                "  return outcome",
            ]
        )

    lines.append("})().catch(function () { return null })")
    lines.append("")
    return lines


def render_workflow_script(graph: dict[str, Any]) -> str:
    """Render a graph as a Workflow tool script.

    Each node becomes a promise that awaits only its own dependencies, so the
    graph runs with real DAG concurrency rather than artificial level barriers.
    """
    lines = [
        "// Generated by development-harness from the graph named "
        + graph["name"]
        + ".",
        "// Edit the project profile and re-render. Manual edits here are overwritten.",
        "",
        "export const meta = {",
        "  name: " + js_quoted(graph["name"]) + ",",
        "  description: " + js_quoted(graph["description"]) + ",",
    ]

    if graph["phases"]:
        lines.append("  phases: [")
        for phase in graph["phases"]:
            lines.append("    { title: " + js_quoted(phase) + " },")
        lines.append("  ],")

    lines.extend(["}", ""])

    if any(node["repeat_until"] is not None for node in graph["nodes"]):
        lines.extend([LOOP_SCHEMA_JS, ""])

    lines.extend([UPSTREAM_HELPER_JS, "", "const node = {}", ""])

    by_id = {node["id"]: node for node in graph["nodes"]}
    for level in graph["levels"]:
        for node_id in level:
            lines.extend(_render_node(by_id[node_id]))

    lines.extend(
        [
            "const results = {}",
            "for (const key of Object.keys(node)) {",
            "  results[key] = await node[key]",
            "}",
            "return results",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate harness work graphs and print an execution plan."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--config", type=Path, help="project profile containing a graphs array"
    )
    source.add_argument("--graph", type=Path, help="a single graph object")
    parser.add_argument("--name", help="only report on this graph")
    parser.add_argument(
        "--plan", action="store_true", help="print the execution plan as JSON"
    )
    args = parser.parse_args()

    path = args.config or args.graph
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"file not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")

    try:
        if args.config:
            if not isinstance(data, dict):
                fail("profile must be a JSON object")
            graphs = normalize_graphs(data.get("graphs"))
        else:
            graphs = [normalize_graph(data, "graph")]
    except GraphError as exc:
        fail(str(exc))

    if args.name:
        wanted = slugify(args.name)
        graphs = [graph for graph in graphs if graph["name"] == wanted]
        if not graphs:
            fail(f"no graph named {wanted}")

    if not graphs:
        print("OK: no graphs declared")
        return

    if args.plan:
        print(json.dumps([execution_plan(graph) for graph in graphs], indent=2))
        return

    for graph in graphs:
        loops = sum(1 for node in graph["nodes"] if node["repeat_until"] is not None)
        print(
            f"OK: {graph['name']} "
            f"({len(graph['nodes'])} nodes, {len(graph['levels'])} levels, {loops} looping)"
        )


if __name__ == "__main__":
    main()
