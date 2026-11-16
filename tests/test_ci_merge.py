"""Two workflows appending to the same capture log must not stop a rebase (lock run 2026-11-15 lost picks that way)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOG = "data/lines/market_captures.csv"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout


def clone(remote, dest):
    git(remote.parent, "clone", "-q", str(remote), str(dest))
    return dest


def append(repo, row):
    p = repo / LOG
    p.write_text(p.read_text() + row + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", row)


@pytest.fixture()
def remote(tmp_path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    git(tmp_path, "init", "-q", "-b", "main", str(seed))
    (seed / "data/lines").mkdir(parents=True)
    (seed / LOG).write_text("capture_id,captured_at\n")
    shutil.copy(ROOT / ".gitattributes", seed / ".gitattributes")
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", "seed")
    git(seed, "remote", "add", "origin", str(bare))
    git(seed, "push", "-q", "origin", "main")
    return bare


def test_concurrent_appends_rebase_cleanly(remote, tmp_path):
    lock, cap = clone(remote, tmp_path / "lock"), clone(remote, tmp_path / "cap")
    append(cap, "cap1,20:32")
    git(cap, "push", "-q", "origin", "main")
    append(lock, "lock1,20:46")
    git(lock, "pull", "-q", "--rebase", "origin", "main")        # the step that failed on 2026-11-15
    git(lock, "push", "-q", "origin", "main")
    rows = (lock / LOG).read_text().splitlines()
    assert "cap1,20:32" in rows and "lock1,20:46" in rows
    assert not (lock / ".git/rebase-merge").exists()


def test_without_the_attribute_the_same_race_conflicts(remote, tmp_path):
    lock, cap = clone(remote, tmp_path / "lock"), clone(remote, tmp_path / "cap")
    (cap / ".gitattributes").unlink()
    git(cap, "add", "-A")
    git(cap, "commit", "-qm", "drop attrs")
    git(cap, "push", "-q", "origin", "main")
    git(lock, "pull", "-q", "--ff-only", "origin", "main")
    append(cap, "cap1,20:32")
    git(cap, "push", "-q", "origin", "main")
    append(lock, "lock1,20:46")
    with pytest.raises(subprocess.CalledProcessError):
        git(lock, "pull", "-q", "--rebase", "origin", "main")
    assert (lock / ".git/rebase-merge").exists()                  # stuck, as in the failed run
    git(lock, "rebase", "--abort")                                 # what the workflow now does before retrying
    assert not (lock / ".git/rebase-merge").exists()
