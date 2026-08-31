# Publishing

## 1. Create the repository

Create a public GitHub repository, preferably:

```text
claude-development-harness
```

Push the complete marketplace root, not only `plugins/development-harness/`.

## 2. Validate locally

```bash
claude plugin validate .
claude plugin validate ./plugins/development-harness
python3 -m unittest discover -s tests -v
```

The first Claude command validates the marketplace and referenced plugin manifest. The second checks the plugin's skills and other components.

## 3. Install from the published repository

```text
/plugin marketplace add OWNER/claude-development-harness
/plugin install development-harness@harness-tools
```

## 4. Release discipline

The plugin version is declared only in:

```text
plugins/development-harness/.claude-plugin/plugin.json
```

Bump it whenever the distributed plugin changes. Do not duplicate the version in the marketplace entry; a stale plugin manifest version can otherwise mask updates.

Recommended release steps:

1. update tests and documentation,
2. update `CHANGELOG.md`,
3. bump the plugin version,
4. validate locally,
5. tag the Git commit, for example `v1.0.0`,
6. push the tag and release notes.

## 5. User updates

Users refresh the marketplace and receive the new plugin version with:

```text
/plugin marketplace update harness-tools
```

If a plugin is already installed, Claude Code uses the version change as the update signal.
