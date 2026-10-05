"""Worker boundary (repair program step 5, 2026-10-04): isolation-file
preservation (ADV-017), string-aware JSON extraction (ADV-019), and the
ignored-file/commit-aware read-only boundary (ADV-020)."""
import json, os, subprocess
import pytest
from pipeline import worker as w

# ---------------------------------------------------------- ADV-017 ------

def test_isolation_write_preserves_preexisting_pxx_toml(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    original = b"# USER CONFIG precious\nmodel = 'mine'\n"
    (repo / "pxx.toml").write_bytes(original)
    iso, restore = w.isolation_write(str(repo))
    assert open(iso).read() == w.ISOLATION_TOML  # isolation in force
    os.remove(iso)                               # simulate pxx's stash-removal
    restore()
    assert (repo / "pxx.toml").read_bytes() == original  # byte-identical

def test_isolation_write_removes_only_what_we_created(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    iso, restore = w.isolation_write(str(repo))
    assert os.path.exists(iso)
    restore()
    assert not os.path.exists(iso)  # we created it; it goes

# ---------------------------------------------------------- ADV-019 ------

def test_extract_one_json_braces_in_strings():
    obj = w.extract_one_json('{"problem": "close the brace } here", "k": 1}')
    assert obj == {"problem": "close the brace } here", "k": 1}
    obj = w.extract_one_json('{"problem": "open { brace", "k": 1}')
    assert obj["k"] == 1

def test_extract_one_json_stray_brace_prose_tolerated():
    """Prose around the object (even containing a lone brace) is fine when
    exactly one object exists."""
    assert w.extract_one_json('note } done\n{"a": 1}') == {"a": 1}

def test_extract_one_json_still_rejects_duplicates_and_multi(tmp_path):
    with pytest.raises(w.WorkerError, match="found 2"):
        w.extract_one_json('{"tasks": [1]} {"tasks": [2]}')
    with pytest.raises(w.WorkerError, match="found 0"):
        w.extract_one_json("no json here")
    with pytest.raises(w.WorkerError, match="duplicate keys"):
        w.extract_one_json('{"a": 1, "a": 2}')

# ---------------------------------------------------------- ADV-020 ------

def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(str(repo), "init", "-q", "-b", "main")
    _git(str(repo), "config", "user.email", "t@t")
    _git(str(repo), "config", "user.name", "t")
    (repo / "a.py").write_text("x = 1\n")
    (repo / ".gitignore").write_text("*.cache\n")
    _git(str(repo), "add", "-A")
    _git(str(repo), "commit", "-qm", "base")
    return str(repo)

def test_read_only_boundary_clean_pass(tmp_path):
    repo = _repo(tmp_path)
    before = w.git_boundary_snapshot(repo)
    w.assert_read_only(repo, before, "REVIEW")  # must not raise

def test_read_only_boundary_sees_ignored_files(tmp_path):
    repo = _repo(tmp_path)
    before = w.git_boundary_snapshot(repo)
    with open(os.path.join(repo, "secret.cache"), "w") as f:  # ignored file
        f.write("planted")
    with pytest.raises(w.WorkerError, match="read-only boundary"):
        w.assert_read_only(repo, before, "REVIEW")

def test_read_only_boundary_sees_commits(tmp_path):
    repo = _repo(tmp_path)
    before = w.git_boundary_snapshot(repo)
    with open(os.path.join(repo, "a.py"), "a") as f:
        f.write("y = 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "sneaky commit")
    with pytest.raises(w.WorkerError, match="HEAD moved"):
        w.assert_read_only(repo, before, "VERIFY")
