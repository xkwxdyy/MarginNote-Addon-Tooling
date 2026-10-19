# Add-on workspace tools

Small, offline utilities for MarginNote add-on workspaces. Requires Python 3.9 or newer. No third-party Python dependencies, downloads, publishing, installation, or Git operations.

## Workspace locations

Copy `addon-workspace.example.json` to `addon-workspace.local.json` at the workspace root and edit the project entries. Keep the local file out of public repositories. `path` is relative to the workspace; `payload` is relative to that project and defaults to `.`. Paths must remain inside their respective roots, including resolved symlinks.

```sh
python3 Tooling/public/bin/addon-workspace.py --workspace "$workspace" list
python3 Tooling/public/bin/addon-workspace.py --workspace "$workspace" resolve example-addon
payload=$(python3 Tooling/public/bin/addon-workspace.py --workspace "$workspace" resolve example-addon --field payload_root)
```

`resolve` returns JSON containing `project_id`, `workspace_root`, `tooling_root`, `project_root`, and `payload_root`. `tooling_root` is the directory containing this utility, independent of a project's Git root. `--field` prints a single value without JSON quoting; shell callers should quote the result.

An explicit `--workspace` wins over `ADDON_WORKSPACE_ROOT`. Manifest precedence is `addon-workspace.local.json`, then `addon-workspace.json`, then `addon-workspace.example.json`. Otherwise, the utility searches ancestors of the current directory and its own installation, preferring real configurations over example files. An invalid higher-priority manifest fails instead of silently falling back. Unknown projects, malformed configurations, escaped paths, and missing selected project or payload directories fail with a nonzero exit code. `list` validates configuration paths without requiring every configured project to be checked out.

Python and Node callers can consume the same CLI output:

```python
paths = json.loads(subprocess.check_output([
    "python3", tool, "--workspace", workspace, "resolve", project_id
], text=True))
```

```javascript
const paths = JSON.parse(execFileSync('python3', [
  tool, '--workspace', workspace, 'resolve', projectId
], { encoding: 'utf8' }));
```

The examples assume the standard-library `json`/`subprocess` modules or Node's `execFileSync` have been imported.

## Package verification

```sh
python3 Tooling/public/bin/addon-workspace.py verify-package package.mnaddon \
  --source staging/plugin \
  --expect-addon-id example.extension.addon \
  --expect-version 1.0.0
```

Verification checks ZIP integrity, unsafe or duplicate paths, symlinks, encryption, root `mnaddon.json` and `main.js`, manifest identity/version, and SHA-256. `--expect-sha256` optionally compares an expected digest. Archives are never extracted or executed.

With `--source`, every packaged file must match the corresponding source or staging file byte for byte. Use repeated `--compare-file relative/path` options to restrict comparison to selected files. Generated bundles should be compared with their staging tree. Extra source files are allowed; repeated `--required-file relative/path` options enforce additional package contents.

Successful output is JSON. Failures print an explanation to stderr and exit nonzero. Reports verify local artifacts only; native host behavior and device acceptance require separate testing.

## Local checks

```sh
python3 -m unittest discover -s tests -v
```

The Ubuntu CI workflow uses Python 3.12 and Node 24. It runs explicit offline tests with read-only repository permissions and has no release job or credentials.
