/**
 * OpenCode guard plugin: deny what the contract already forbids in prose.
 *
 * The port of `hook_guard.py` to the one mechanism OpenCode gives a repository.
 * Measured on OpenCode 1.18.29 (`.ai/reports/0014-opencode-enforcement-surface.md`):
 * a throw inside `tool.execute.before` is a real deny for `read`, `write`, `edit`,
 * `bash`, and `task`, the thrown text reaches the model verbatim, the file on disk
 * is unchanged, and the hook also fires for a subagent's tool calls.
 *
 * The same three limits the Python guard states apply here, plus one that is
 * specific to this host:
 *
 * **It fails open.** Anything this file throws that is not a deliberate deny is
 * swallowed and the call proceeds. A defect here must not lock an operator out of
 * their own repository; the fallback is the prose rule that was there before.
 *
 * **It reads a command, not a shell.** Patterns over a command string. Defense in
 * depth over the permission system, never a sandbox.
 *
 * **It denies; it never allows.** No path returns an allow decision. A guard that
 * could grant would be a way to widen authority from inside the repository.
 *
 * **It does nothing at module scope.** A plugin whose module body throws leaves
 * `opencode run` producing no session at all, which is worse than no guard. So the
 * only work at load time is declaring constants, and every read of the filesystem
 * happens inside a try/catch in the hook.
 *
 * Escape hatch: set `HARNESS_HOOKS_DISABLE=1` to make every harness guard - this
 * one and the Python hooks - stand down.
 */

const DISABLE_ENV = "HARNESS_HOOKS_DISABLE"

// Kept in step with `hook_guard.SECRET_FILENAMES` by a test rather than by an
// import: these two files run on different hosts in different languages, and the
// only thing that can keep them equal is a check that reads both.
const SECRET_FILENAMES = new Set([
  ".env",
  ".env.local",
  ".env.production",
  ".env.development",
  ".env.test",
  ".envrc",
  ".netrc",
  ".npmrc",
  ".pypirc",
  ".htpasswd",
  "credentials",
  "credentials.json",
  "service-account.json",
  "id_rsa",
  "id_ed25519",
  "settings.local.json",
])

const SECRET_SUFFIXES = [".pem", ".key", ".pfx", ".p12", ".jks", ".keystore", ".asc"]

const SECRET_DIR_FRAGMENTS = ["/.ssh/", "/.aws/", "/.gnupg/", "/.docker/config"]

// OpenCode's tool names, measured rather than assumed. `patch` is included
// because it is a write path when the host offers it; a name that never arrives
// costs nothing.
const READ_TOOLS = new Set(["read"])
const WRITE_TOOLS = new Set(["write", "edit", "patch"])

// The keys those tools carry their path in. `filePath` is what 1.18.29 sends;
// the others are cheap insurance against a rename.
const PATH_KEYS = ["filePath", "path", "file_path"]

const ALWAYS_DENIED_GIT = [
  [/\bgit\s+reset\s+(--\S+\s+)*--hard\b/, "git reset --hard discards local work"],
  [/\bgit\s+clean\s+(-\S*f|--force)/, "git clean deletes untracked files"],
  [/\bgit\s+checkout\s+--\s/, "git checkout -- discards uncommitted changes"],
  [/\bgit\s+push\s+(--force|-f)\b/, "a force push rewrites published history"],
  [/\bgit\s+push\s+.*--force/, "a force push rewrites published history"],
  [/\bgit\s+branch\s+(-D|--delete\s+--force)/, "a forced branch delete loses commits"],
  [/\bgit\s+filter-branch\b/, "filter-branch rewrites every commit"],
  [/\bgit\s+reflog\s+(expire|delete)/, "expiring the reflog removes the last safety net"],
]

const COMMIT_GIT = [
  [/\bgit\s+commit\b/, "git commit"],
  [/\bgit\s+merge\b/, "git merge"],
  [/\bgit\s+rebase\b/, "git rebase"],
]

const PUSH_GIT = [[/\bgit\s+push\b/, "git push"]]

const RM_PATTERN = /\brm\s+(-\S+\s+)*-\S*[rR]\S*f|\brm\s+(-\S+\s+)*-\S*f\S*[rR]/

const RM_TARGETS = [" /", " ~", " .git", " ..", " $HOME", " /*"]

// Kept in step with `hook_guard.WIDENING_TOKENS` by a test. Two of these are
// Codex's own bypasses, and they are refused here because a repository that
// declares more than one host is one shell away from either binary.
const WIDENING_TOKENS = [
  "--dangerously-skip-permissions",
  "--permission-mode bypassPermissions",
  "--dangerously-bypass-approvals-and-sandbox",
  "--dangerously-bypass-hook-trust",
]

// `--auto` needs a boundary: `--autocompact` is a flag the harness itself
// passes, and a substring match would refuse the launcher's own command.
const AUTO_FLAG = /--auto(\s|$)/

/** A refusal this file meant to make, as opposed to a defect in it. */
class HarnessDeny extends Error {
  constructor(reason) {
    super(`harness guard: ${reason}`)
    this.name = "HarnessDeny"
    this.harnessDeny = true
  }
}

const deny = (reason) => {
  throw new HarnessDeny(reason)
}

/** Return the reason this path is secret-bearing, or null. */
const looksSecret = (rawPath) => {
  if (!rawPath) return null
  const text = String(rawPath).replace(/\\/g, "/")
  const name = text.split("/").pop() || ""

  if (SECRET_FILENAMES.has(name)) return `${name} is a secret-bearing file`
  if (name.startsWith(".env")) return `${name} is an environment file`
  for (const suffix of SECRET_SUFFIXES) {
    if (name.endsWith(suffix)) return `${name} looks like a key or certificate`
  }
  const lowered = "/" + text.toLowerCase().replace(/^\/+/, "")
  for (const fragment of SECRET_DIR_FRAGMENTS) {
    if (lowered.includes(fragment)) return `${text} is inside a credential directory`
  }
  return null
}

const guardFileTool = (tool, args) => {
  for (const key of PATH_KEYS) {
    const found = looksSecret(args[key] === undefined ? "" : String(args[key]))
    if (found) {
      const verb = WRITE_TOOLS.has(tool) ? "write to" : "read"
      deny(
        `refusing to ${verb} it: ${found}. Report such files by name only. ` +
          `Set ${DISABLE_ENV}=1 if the operator has authorized this.`,
      )
    }
  }
}

const guardBash = (command, policy) => {
  if (!command) return
  // A newline-joined command is still one command line to the shell.
  const flat = String(command).split(/\s+/).filter(Boolean).join(" ")

  for (const [pattern, reason] of ALWAYS_DENIED_GIT) {
    if (pattern.test(flat)) deny(`refusing this command: ${reason}`)
  }

  for (const [pattern, label] of PUSH_GIT) {
    if (pattern.test(flat)) {
      deny(
        `refusing ${label}: publishing is an operator action, not an agent one, ` +
          "whatever the commit policy says",
      )
    }
  }

  if (policy !== "commit-locally") {
    for (const [pattern, label] of COMMIT_GIT) {
      if (pattern.test(flat)) {
        deny(
          `refusing ${label}: the agent commit policy is ${policy}. ` +
            "Leave the change in the working tree and say what you did.",
        )
      }
    }
  }

  if (RM_PATTERN.test(flat)) {
    for (const target of RM_TARGETS) {
      if (`${flat} `.includes(`${target} `) || flat.replace(/\s+$/, "").endsWith(target)) {
        deny(
          `refusing a recursive force delete of ${target.trim()}: ` +
            "name the paths explicitly instead",
        )
      }
    }
  }

  for (const token of WIDENING_TOKENS) {
    if (flat.includes(token)) {
      deny(`refusing a command carrying ${token}: a session may not widen its own authority`)
    }
  }

  if (AUTO_FLAG.test(flat)) {
    deny(
      "refusing a command carrying --auto: it auto-approves every permission " +
        "that is not explicitly denied",
    )
  }
}

export const HarnessGuard = async ({ directory }) => {
  /**
   * The policy the operator chose at setup is the one the guard enforces. A
   * missing or unreadable profile falls back to the stricter answer, because a
   * guard that guesses should guess toward refusing. Read once per session: the
   * profile is installed configuration, not something a run rewrites.
   */
  let policy = "no-commit"
  try {
    const fs = await import("node:fs/promises")
    const path = await import("node:path")
    const root = directory || process.cwd()
    const raw = await fs.readFile(
      path.join(root, ".ai", "harness", "project-profile.json"),
      "utf8",
    )
    const value = JSON.parse(raw).agent_commit_policy
    if (typeof value === "string") policy = value
  } catch {
    // Stays `no-commit`.
  }

  return {
    "tool.execute.before": async (input, output) => {
      // Read at call time, not at load time: an operator who exports the escape
      // hatch expects it to hold for the process they exported it in.
      if (process.env[DISABLE_ENV] === "1") return
      try {
        const tool = String((input && input.tool) || "")
        const args = (output && output.args) || {}
        if (READ_TOOLS.has(tool) || WRITE_TOOLS.has(tool)) {
          guardFileTool(tool, args)
          return
        }
        if (tool === "bash") {
          guardBash(args.command, policy)
        }
      } catch (error) {
        // A deliberate refusal is the point of the file; anything else is a
        // defect in it, and a defect must not deny a call that should proceed.
        if (error && error.harnessDeny) throw error
      }
    },
  }
}
