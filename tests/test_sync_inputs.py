"""A waiting lock run pulls pool lines merged during its wait, and can never break or block the pick (2026-11-26)."""
import shutil
import subprocess

import pytest

from engine.picks import sync_inputs as S

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
LINES = "data/lines/league_lines.csv"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout


def commit_file(repo, path, text):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"edit {path}")


@pytest.fixture()
def pair(tmp_path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(bare), str(seed))
    git(seed, "checkout", "-q", "-b", "main")
    commit_file(seed, LINES, "game_id,spread\n")
    commit_file(seed, "src/engine/x.py", "A = 1\n")
    git(seed, "push", "-q", "origin", "main")
    runner = tmp_path / "runner"          # the lock run's checkout, taken before the wait
    git(tmp_path, "clone", "-q", str(bare), str(runner))
    return seed, runner


def test_off_without_ref(pair, monkeypatch):
    monkeypatch.delenv(S.ENV_REF, raising=False)
    assert S.sync_before_pick(cwd=pair[1]).startswith("SYNC off")


def test_pool_lines_merged_during_wait_are_pulled(pair):
    seed, runner = pair
    commit_file(seed, LINES, "game_id,spread\n2026_12_PHI_DAL,-8.5\n")
    commit_file(seed, "docs/cbs_lines_report.md", "report\n")
    git(seed, "push", "-q", "origin", "main")
    assert "2026_12_PHI_DAL" not in (runner / LINES).read_text()
    msg = S.sync_before_pick("main", cwd=runner)
    assert msg.startswith("SYNC ok: fast-forwarded 2 file(s), 1 under data/lines"), msg
    assert "2026_12_PHI_DAL,-8.5" in (runner / LINES).read_text()
    assert git(runner, "status", "--porcelain") == ""           # clean tree, nothing for the commit step to trip on
    assert git(runner, "rev-parse", "HEAD") == git(seed, "rev-parse", "HEAD")


def test_already_up_to_date(pair):
    assert S.sync_before_pick("main", cwd=pair[1]) == "SYNC ok: already up to date"


def test_code_change_upstream_leaves_checkout_alone(pair):
    seed, runner = pair
    commit_file(seed, LINES, "game_id,spread\nnew,-1.5\n")
    commit_file(seed, "src/engine/x.py", "A = 2\n")
    git(seed, "push", "-q", "origin", "main")
    before = git(runner, "rev-parse", "HEAD")
    msg = S.sync_before_pick("main", cwd=runner)
    assert msg.startswith("SYNC skipped: 1 code/workflow file(s) changed upstream"), msg
    assert git(runner, "rev-parse", "HEAD") == before
    assert (runner / "src/engine/x.py").read_text() == "A = 1\n"


def test_workflow_change_is_code(pair):
    seed, runner = pair
    commit_file(seed, ".github/workflows/lock-run.yml", "name: x\n")
    git(seed, "push", "-q", "origin", "main")
    assert "code/workflow" in S.sync_before_pick("main", cwd=runner)


def test_unpushed_local_commit_is_left_alone(pair):
    seed, runner = pair
    commit_file(runner, "data/predictions/predictions.csv", "a\n")          # an earlier pass whose push failed
    commit_file(seed, LINES, "game_id,spread\nnew,-1.5\n")
    git(seed, "push", "-q", "origin", "main")
    before = git(runner, "rev-parse", "HEAD")
    assert S.sync_before_pick("main", cwd=runner) == "SYNC skipped: local commits not on origin yet"
    assert git(runner, "rev-parse", "HEAD") == before


def test_dirty_file_that_upstream_changes_does_not_raise_or_clobber(pair):
    seed, runner = pair
    commit_file(seed, LINES, "game_id,spread\nnew,-1.5\n")
    git(seed, "push", "-q", "origin", "main")
    (runner / LINES).write_text("local edit\n")
    msg = S.sync_before_pick("main", cwd=runner)
    assert msg.startswith("SYNC skipped: fast-forward refused"), msg
    assert (runner / LINES).read_text() == "local edit\n"


def test_fetch_failure_never_raises(pair):
    seed, runner = pair
    git(runner, "remote", "set-url", "origin", str(runner / "does-not-exist"))
    assert S.sync_before_pick("main", cwd=runner).startswith("SYNC skipped: fetch failed")


def test_not_a_git_repo_never_raises(tmp_path):
    assert S.sync_before_pick("main", cwd=tmp_path).startswith("SYNC skipped")
