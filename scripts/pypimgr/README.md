# pypimgr

`pypimgr` checks, tests, builds, and releases Python packages. It requires Python 3.10 or newer and Git. Run it
from the project directory, or use `-C <directory>` to select a project.

## Usage

From the runlytics repository:

```powershell
python scripts\pypimgr\pypimgr.py status
python scripts\pypimgr\pypimgr.py doctor
```

```sh
python scripts/pypimgr/pypimgr.py status
python scripts/pypimgr/pypimgr.py doctor
```

Running `pypimgr` without an action opens its terminal interface when attached to a terminal. Use `-y` to accept
confirmations non-interactively.

## Actions

| Action | Description |
| --- | --- |
| `status`, `check`, `doctor` | Inspect project, version, Git state, required files, and release tools. |
| `test` | Run Ruff and pytest when available. |
| `build`, `verify`, `contents` | Build distributions, inspect them, or list their contents. |
| `bump VERSION` | Update the package version and changelog; accepts `patch`, `minor`, `major`, `fix`, or a version. |
| `release [bump]` | Test, build, verify, commit, and tag a release. |
| `publish` | Push a local release tag to start the GitHub Actions workflow; it does not upload from the local machine. |
| `notes VERSION`, `logs`, `clean` | Print release notes, show logs, or remove generated build files. |

Use `pypimgr --help` or `pypimgr <action> --help` for the full options. `release --test` tests and builds without
changing version files, committing, tagging, or publishing. `release --dry` checks and tests without making
changes. `release --push` pushes the release commit and tag after creating them. Use the `fix` bump only to amend
an unpublished release; published versions cannot be replaced.

## Publishing

The GitHub Actions workflow builds and validates the distributions, creates a GitHub release, then publishes the
same artifacts to TestPyPI and PyPI using Trusted Publishing. Configure a Trusted Publisher for `runlytics` on
each index with repository `KshRaven/runlytics` and workflow `release.yml`. The workflow uses GitHub environments
`testpypi` and `pypi`; each publisher must match its environment or allow any environment.

To create and publish a new release, run `pypimgr release patch --push` or choose another bump. To push a
previously created local tag, run `pypimgr publish`. `pypimgr release --test` is a local rehearsal and does not
upload to TestPyPI. Published versions are not overwritten: the workflow skips an index where the version already
exists and reports other lookup or upload failures.

## Cache and logs

Build artifacts and the tool environment are stored under `.cache/pypimgr/<project>/`; logs go under `.logs/`.
Set `PYPIMGR_USE_PROJECT_CACHE=0` to use per-user cache and log directories instead. The setting can be provided
in the process environment or in `.env.release`; the process environment takes precedence. Set it to `1` to force
project-local storage.

## Using pypimgr with another project

The script discovers the project root and package name from `pyproject.toml`. It expects conventional project
files such as `CHANGELOG.md` and `MANIFEST.in`, Git tags named `v<version>`, and Ruff/pytest for validation.
Projects with different release files or test commands require changes to the script.
