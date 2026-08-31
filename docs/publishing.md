# Publishing

## 1. The repository

The marketplace root is the repository root, not `plugins/development-harness/`. Push the whole tree — `/plugin marketplace add` reads `.claude-plugin/marketplace.json` at the top level and resolves the plugin from there.

The repository is public, so `marketplace add` works for anyone. Nothing else in the layout depends on visibility.

## 2. Validate locally

One command, the same one CI runs:

```bash
bash scripts/validate-repo.sh
```

It covers `compileall`, the unit suite, both JSON manifests, and rendering plus validating every profile under `examples/`. When Claude Code is present it also runs:

```bash
claude plugin validate .
claude plugin validate ./plugins/development-harness
```

The first validates the marketplace and the referenced plugin manifest; the second checks the plugin's skills and other components.

## 3. Install from the published repository

```text
/plugin marketplace add AlperenEvci/claude-code-development-harness
/plugin install development-harness@alperenevci-harness
/reload-plugins
```

## 4. Release discipline

The version lives in three places and the test suite pins them to each other:

```text
plugins/development-harness/.claude-plugin/plugin.json      "version"
plugins/development-harness/scripts/render_harness.py       GENERATOR_VERSION
CHANGELOG.md                                                the top ## heading
```

Bumping one alone fails `test_the_version_is_the_same_in_all_three_places`. That is deliberate: `GENERATOR_VERSION` is stamped into every rendered package, so a package that reports a version the plugin never shipped is worse than no version at all. Do **not** duplicate the version into the marketplace entry; a stale copy there can mask updates.

Release steps:

1. update tests and documentation,
2. add the `CHANGELOG.md` section,
3. bump `plugin.json` and `GENERATOR_VERSION` to match it,
4. run the full gate,
5. confirm CI is green on both matrix legs — `ubuntu-latest` is authoritative, since two symlink tests skip on Windows and the POSIX permission-bit assertion only runs on Linux, but a red Windows leg still blocks a release,
6. tag the commit, for example `v1.0.0`,
7. push the tag and release notes.

## 5. Compatibility

Every profile field added since 0.2.0 is optional and defaulted, so 1.0.0 is an additive release and needs no migration. The three profiles shipped with 0.2.0 are frozen under `tests/fixtures/v0.2-*.json` and rendered and validated on every run, so this stays true rather than being asserted once.

## 6. User updates

Users refresh the marketplace and receive the new plugin version with:

```text
/plugin marketplace update alperenevci-harness
```

If a plugin is already installed, Claude Code uses the version change as the update signal.

An installed harness in a project is not upgraded by a plugin update. Re-run `/development-harness:setup` in that project; it detects the existing harness and takes the Upgrade path, which is dry-run and conflict-aware like any other install.
