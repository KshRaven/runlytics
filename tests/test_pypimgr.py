import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PYPIMGR_PATH = Path(__file__).parents[1] / "scripts" / "pypimgr" / "pypimgr.py"
SPEC = importlib.util.spec_from_file_location("runlytics_pypimgr", PYPIMGR_PATH)
pypimgr = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pypimgr
SPEC.loader.exec_module(pypimgr)


def test_release_commit_message_defaults_to_release_version(monkeypatch):
    monkeypatch.setattr(pypimgr, "ask_yes", lambda *_args, **_kwargs: False)

    message = pypimgr.release_commit_message("0.3.0", SimpleNamespace(yes=False))

    assert message == "Release v0.3.0"


def test_legacy_token_command_is_not_available():
    with pytest.raises(SystemExit) as exc_info:
        pypimgr.build_parser().parse_args(["token"])

    assert exc_info.value.code == 2


def test_publish_command_pushes_local_tag_for_trusted_publishing(monkeypatch, capsys):
    calls = []

    def fake_git(*args):
        calls.append(args)
        if args == ("rev-parse", "--verify", "refs/tags/v0.2.1^{}"):
            return SimpleNamespace(returncode=0, stdout="release-commit\n")
        if args == ("rev-parse", "HEAD"):
            return SimpleNamespace(returncode=0, stdout="release-commit\n")
        if args == ("remote", "get-url", "origin"):
            return SimpleNamespace(returncode=0, stdout="https://github.com/KshRaven/runlytics.git\n")
        if args == ("ls-remote", "--tags", "origin", "refs/tags/v0.2.1", "refs/tags/v0.2.1^{}"):
            return SimpleNamespace(returncode=0, stdout="")
        if args == ("push", "origin", "v0.2.1"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(pypimgr, "is_repo", lambda: True)
    monkeypatch.setattr(pypimgr, "get_version", lambda: "0.2.1")
    monkeypatch.setattr(pypimgr, "dirty", lambda: [])
    monkeypatch.setattr(pypimgr, "git", fake_git)

    assert pypimgr.build_parser().parse_args(["publish"]).cmd == "publish"
    assert pypimgr.cmd_publish(SimpleNamespace(yes=True)) == 0
    assert ("push", "origin", "v0.2.1") in calls
    assert "Trusted Publishing" in capsys.readouterr().out


def test_publish_does_not_push_tag_already_on_origin(monkeypatch):
    calls = []

    def fake_git(*args):
        calls.append(args)
        if args == ("rev-parse", "--verify", "refs/tags/v0.2.1^{}"):
            return SimpleNamespace(returncode=0, stdout="release-commit\n")
        if args == ("rev-parse", "HEAD"):
            return SimpleNamespace(returncode=0, stdout="release-commit\n")
        if args == ("remote", "get-url", "origin"):
            return SimpleNamespace(returncode=0, stdout="https://github.com/KshRaven/runlytics.git\n")
        if args == ("ls-remote", "--tags", "origin", "refs/tags/v0.2.1", "refs/tags/v0.2.1^{}"):
            return SimpleNamespace(returncode=0, stdout="release-commit\trefs/tags/v0.2.1\n")
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(pypimgr, "is_repo", lambda: True)
    monkeypatch.setattr(pypimgr, "get_version", lambda: "0.2.1")
    monkeypatch.setattr(pypimgr, "dirty", lambda: [])
    monkeypatch.setattr(pypimgr, "git", fake_git)

    with pytest.raises(pypimgr.Fail, match="already on origin"):
        pypimgr.cmd_publish(SimpleNamespace(yes=True))

    assert not any(args[0] == "push" for args in calls)


def test_release_commit_message_reads_commit_txt(monkeypatch, tmp_path):
    (tmp_path / "commit.txt").write_text("Custom release\n\nDetails.\n", encoding="utf-8")
    monkeypatch.setattr(pypimgr, "ROOT", tmp_path)
    answers = iter([True, True])
    monkeypatch.setattr(pypimgr, "ask_yes", lambda *_args, **_kwargs: next(answers))

    message = pypimgr.release_commit_message("0.3.0", SimpleNamespace(yes=False))

    assert message == "Custom release\n\nDetails."


def test_release_commit_message_prompts_for_custom_text(monkeypatch):
    answers = iter([True, False])
    monkeypatch.setattr(pypimgr, "ask_yes", lambda *_args, **_kwargs: next(answers))
    monkeypatch.setattr(pypimgr, "ask_text", lambda *_args, **_kwargs: "Custom release")

    message = pypimgr.release_commit_message("0.3.0", SimpleNamespace(yes=False))

    assert message == "Custom release"


def test_release_state_requires_empty_unreleased_and_matching_tag(monkeypatch, tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## Unreleased\n\n## 0.3.0\n- Notes.\n", encoding="utf-8")
    monkeypatch.setattr(pypimgr, "CHANGELOG", changelog)
    monkeypatch.setattr(pypimgr, "get_version", lambda: "0.3.0")
    monkeypatch.setattr(pypimgr, "git", lambda *_args: SimpleNamespace(stdout="v0.3.0\n"))

    pypimgr.validate_release_state("0.3.0", check_tag=True)

    changelog.write_text("# Changelog\n\n## Unreleased\n- Pending.\n\n## 0.3.0\n- Notes.\n", encoding="utf-8")
    with pytest.raises(pypimgr.Fail, match="empty Unreleased"):
        pypimgr.validate_release_state("0.3.0")


def test_empty_unreleased_section_allows_release_without_notes(monkeypatch, tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## Unreleased\n\n## 0.2.0\n- Existing release.\n", encoding="utf-8")
    monkeypatch.setattr(pypimgr, "CHANGELOG", changelog)
    monkeypatch.setattr(pypimgr, "get_version", lambda: "0.2.1")

    pypimgr.stamp_changelog("0.2.1")
    pypimgr.validate_release_state("0.2.1")

    assert pypimgr.section("Unreleased")["body"] == ""
    assert pypimgr.section("0.2.1")["body"] == ""
    assert pypimgr.cmd_notes(SimpleNamespace(version="0.2.1")) == 0
    assert capsys.readouterr().out == "No changelog notes were provided for 0.2.1.\n"


def test_missing_unreleased_section_allows_release_without_notes(monkeypatch, tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## 0.2.0\n- Existing release.\n", encoding="utf-8")
    monkeypatch.setattr(pypimgr, "CHANGELOG", changelog)
    monkeypatch.setattr(pypimgr, "get_version", lambda: "0.2.1")

    pypimgr.stamp_changelog("0.2.1")
    pypimgr.validate_release_state("0.2.1")

    assert pypimgr.section("Unreleased") is None
    assert pypimgr.section("0.2.1")["body"] == ""


def test_release_state_rejects_a_mismatched_tag(monkeypatch, tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## Unreleased\n\n## 0.3.0\n- Notes.\n", encoding="utf-8")
    monkeypatch.setattr(pypimgr, "CHANGELOG", changelog)
    monkeypatch.setattr(pypimgr, "get_version", lambda: "0.3.0")
    monkeypatch.setattr(pypimgr, "git", lambda *_args: SimpleNamespace(stdout="v0.2.0\n"))

    with pytest.raises(pypimgr.Fail, match="latest git tag is v0.2.0"):
        pypimgr.validate_release_state("0.3.0", check_tag=True)


def test_stamp_changelog_appends_unreleased_notes_to_existing_version(monkeypatch, tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## Unreleased\n- A follow-up fix.\n- Another follow-up fix.\n\n"
        "## 0.2.0\n- Existing release note.\n- Another existing note.\n\n"
        "## 0.1.0\n- Older release note.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pypimgr, "CHANGELOG", changelog)

    pypimgr.stamp_changelog("0.2.0")

    assert not pypimgr.section("Unreleased")["body"]
    assert pypimgr.section("0.2.0")["body"] == (
        "- Existing release note.\n- Another existing note.\n- A follow-up fix.\n- Another follow-up fix."
    )
    assert "- Another existing note.\n- A follow-up fix.\n- Another follow-up fix.\n\n## 0.1.0" in changelog.read_text(
        encoding="utf-8",
    )


def test_dirs_use_project_local_cache_and_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(pypimgr, "ROOT", tmp_path)
    monkeypatch.setattr(pypimgr, "ENVFILE", tmp_path / ".env.release")
    monkeypatch.setattr(pypimgr, "project_name", lambda: "sample")
    monkeypatch.delenv(pypimgr.PROJECT_CACHE_ENV, raising=False)

    assert pypimgr.dirs() == (tmp_path / ".cache" / "pypimgr" / "sample", tmp_path / ".logs")


def test_cache_preference_uses_project_env_then_os_override(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.release"
    env_file.write_text("PYPIMGR_USE_PROJECT_CACHE=0\n", encoding="utf-8")
    monkeypatch.setattr(pypimgr, "ROOT", tmp_path)
    monkeypatch.setattr(pypimgr, "ENVFILE", env_file)
    monkeypatch.setattr(pypimgr, "project_name", lambda: "sample")
    monkeypatch.setattr(pypimgr, "IS_WIN", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.delenv(pypimgr.PROJECT_CACHE_ENV, raising=False)

    assert pypimgr.dirs()[0] == tmp_path / "local-app-data" / "pypimgr" / "sample"

    monkeypatch.setenv(pypimgr.PROJECT_CACHE_ENV, "1")
    assert pypimgr.dirs() == (tmp_path / ".cache" / "pypimgr" / "sample", tmp_path / ".logs")


def test_dirs_use_platform_global_paths_when_project_cache_is_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(pypimgr, "ROOT", tmp_path)
    monkeypatch.setattr(pypimgr, "ENVFILE", tmp_path / ".env.release")
    monkeypatch.setattr(pypimgr, "project_name", lambda: "sample")
    monkeypatch.setattr(pypimgr, "IS_WIN", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setenv(pypimgr.PROJECT_CACHE_ENV, "false")

    assert pypimgr.dirs() == (
        tmp_path / "local-app-data" / "pypimgr" / "sample",
        tmp_path / "local-app-data" / "pypimgr" / "sample" / "logs",
    )


def test_global_dirs_use_xdg_cache_and_state_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(pypimgr, "IS_WIN", False)
    monkeypatch.setattr(pypimgr.sys, "platform", "linux")
    monkeypatch.setattr(pypimgr, "project_name", lambda: "sample")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    assert pypimgr.global_dirs() == (
        tmp_path / "cache" / "pypimgr" / "sample",
        tmp_path / "state" / "pypimgr" / "sample",
    )


def test_logs_displays_paths_relative_to_log_directory(monkeypatch, tmp_path, capsys):
    log_dir = tmp_path / "global-logs"
    log_file = log_dir / "release" / "latest.log"
    log_file.parent.mkdir(parents=True)
    log_file.write_text("release complete\n", encoding="utf-8")
    monkeypatch.setattr(pypimgr, "LOGDIR", log_dir)
    monkeypatch.setattr(pypimgr, "TERM", None)

    assert pypimgr.cmd_logs() == 0
    output = capsys.readouterr().out
    assert f"--- {Path('release') / 'latest.log'} ---" in output
    assert "release complete" in output


def test_commands_write_categorized_logs(monkeypatch, tmp_path):
    log_dir = tmp_path / ".logs"
    monkeypatch.setattr(pypimgr, "ROOT", tmp_path)
    monkeypatch.setattr(pypimgr, "LOGDIR", log_dir)
    monkeypatch.setattr(pypimgr, "LOGFILE", log_dir / "general" / "session.log")
    monkeypatch.setattr(pypimgr, "TERM", None)

    rc, output = pypimgr.sh([sys.executable, "-c", "print('check output')"], "pytest", cwd=tmp_path, quiet=True)

    assert rc == 0
    assert "check output" in output
    assert pypimgr.LAST_COMMAND_LOG.parent == log_dir / "tests"
    assert "check output" in pypimgr.LAST_COMMAND_LOG.read_text(encoding="utf-8")


def test_tui_shows_multiline_errors_and_saves_them(monkeypatch, tmp_path):
    log_dir = tmp_path / ".logs"
    monkeypatch.setattr(pypimgr, "LOGDIR", log_dir)
    monkeypatch.setattr(pypimgr, "LOGFILE", log_dir / "general" / "session.log")
    monkeypatch.setattr(pypimgr, "TERM", object())
    shown = {}
    monkeypatch.setattr(pypimgr.ui, "view_text", lambda _term, _title, lines: shown.update(lines=lines))

    def fail():
        raise pypimgr.Fail("build failed:\ncompiler detail")

    assert pypimgr.tui_run("Build", fail) == 1
    assert any("compiler detail" in line for line in shown["lines"])
    assert any("Error log:" in line for line in shown["lines"])
    assert list((log_dir / "build").glob("*-error.log"))


def test_unpushed_release_check_refuses_remote_commit(monkeypatch):
    def fake_git(*args):
        if args == ("rev-parse", "--verify", "refs/tags/v0.2.0^{}"):
            return SimpleNamespace(returncode=0, stdout="release-commit\n")
        if args == ("rev-parse", "HEAD"):
            return SimpleNamespace(returncode=0, stdout="release-commit\n")
        if args == ("remote",):
            return SimpleNamespace(returncode=0, stdout="origin\n")
        if args == ("ls-remote", "--heads", "origin"):
            return SimpleNamespace(returncode=0, stdout="release-commit\trefs/heads/main\n")
        if args == ("cat-file", "-e", "release-commit^{commit}"):
            return SimpleNamespace(returncode=0, stdout="")
        if args == ("merge-base", "--is-ancestor", "HEAD", "release-commit"):
            return SimpleNamespace(returncode=0, stdout="")
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(pypimgr, "git", fake_git)

    with pytest.raises(pypimgr.Fail, match="already present on remote"):
        pypimgr.ensure_release_is_unpushed("0.2.0")


def test_same_version_release_amends_unpushed_commit_and_retags(monkeypatch, tmp_path):
    root = tmp_path
    (root / "runlytics").mkdir()
    (root / "runlytics" / "_version.py").write_text('__version__ = "0.2.0"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sample"\ndynamic = ["version"]\n'
        '[tool.setuptools.dynamic]\nversion = { attr = "runlytics._version.__version__" }\n',
        encoding="utf-8",
    )
    changelog = root / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## Unreleased\n- A follow-up fix.\n\n## 0.2.0\n- Existing release note.\n\n"
        "## 0.1.0\n- Older release note.\n",
        encoding="utf-8",
    )

    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Test User")
    git("config", "user.email", "test@example.com")
    git("add", "-A")
    git("commit", "-m", "Baseline")
    remote = root.parent / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True, text=True, check=True)
    git("remote", "add", "origin", str(remote))
    git("push", "-u", "origin", "main")
    git("commit", "--allow-empty", "-m", "Release v0.2.0")
    git("tag", "-a", "v0.2.0", "-m", "v0.2.0")
    previous_head = git("rev-parse", "HEAD")

    monkeypatch.setattr(pypimgr, "ROOT", root)
    monkeypatch.setattr(pypimgr, "CHANGELOG", changelog)
    monkeypatch.setattr(pypimgr, "ENVFILE", root / ".env.release")
    monkeypatch.setattr(pypimgr, "CACHE", root / ".cache" / "pypimgr" / "sample")
    monkeypatch.setattr(pypimgr, "LOGDIR", root / ".logs")
    monkeypatch.setattr(pypimgr, "LOGFILE", root / ".logs" / "general" / "session.log")
    monkeypatch.setattr(pypimgr, "ART", root / ".cache" / "pypimgr" / "sample" / "artifacts")
    monkeypatch.setattr(pypimgr, "do_build", lambda: [])
    monkeypatch.setattr(pypimgr, "do_verify", lambda: None)
    args = SimpleNamespace(
        test=False, bump="fix", upload=False, push=True, version_files_only=False, dry=False,
        yes=True, skip_tests=True, message="Release v0.2.0: follow-up fixes", message_file=None,
    )

    assert pypimgr.cmd_release(args) == 0

    assert git("rev-parse", "HEAD") != previous_head
    assert git("rev-parse", "refs/tags/v0.2.0^{}") == git("rev-parse", "HEAD")
    assert git("log", "-1", "--format=%s") == "Release v0.2.0: follow-up fixes"
    assert not pypimgr.section("Unreleased")["body"]
    assert pypimgr.section("0.2.0")["body"] == "- Existing release note.\n- A follow-up fix."
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert remote_head == git("rev-parse", "HEAD")
    remote_tag = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/tags/v0.2.0^{}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert remote_tag == git("rev-parse", "HEAD")
