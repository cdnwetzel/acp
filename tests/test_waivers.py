"""F-005 (owner ruling 2026-10-12): reviewer dispositions are RESOLVED/OPEN;
OPEN halts REVIEW; only the owner waives, via a ledgered receipt bound to the
current lifecycle, the exact review attempt, and the finding identity.

Regression anchor: the rung-6 challenge artifact (WAIVED + 'not covered by
the acceptance tests') is now malformed BY CONSTRUCTION — parse failure, not
keyword matching.
"""
import json, os, subprocess, sys
import pytest
from pipeline import approvals, envelope, gates, runner, state

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RUNG6_REVIEW = (
    "# review.md\n\n## TASK-1\n"
    "- issue: none — RESOLVED (diff satisfies the criterion)\n\n"
    "## TASK-2\n"
    "- issue: clamp incorrectly handles intervals when hi < 0 and lo ≤ hi "
    "(the swap logic is incorrect) — WAIVED: not covered by the acceptance "
    "tests for clamp(5, 0, 10), clamp(-1, 0, 10), or clamp(15, 0, 10).\n")

def _manifest(tmp_path, tasks=("TASK-1", "TASK-2")):
    os.makedirs("artifacts/diff", exist_ok=True)
    for t in tasks:
        open(f"artifacts/diff/{t}.patch", "w").write("diff")
    open("artifacts/diff/manifest.json", "w").write(json.dumps(
        {"diffs": [{"task": t, "path": f"artifacts/diff/{t}.patch",
                    "scope": ["a.py"]} for t in tasks]}))

# ------------------------------------------------------------- gate shape --

def test_rung6_waived_coverage_excuse_is_malformed(tmp_path, monkeypatch):
    """The exact rung-6 reviewer output now fails parsing (F-005)."""
    monkeypatch.chdir(tmp_path)
    _manifest(tmp_path)
    open("artifacts/review.md", "w").write(RUNG6_REVIEW)
    with pytest.raises(gates.GateError, match="not a reviewer disposition"):
        gates.gate_review()

def test_open_finding_halts_without_waiver(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _manifest(tmp_path)
    open("artifacts/review.md", "w").write(
        "## TASK-1\n- issue: none — RESOLVED (ok)\n"
        "## TASK-2\n- issue: real defect — OPEN: violates AC-2\n")
    with pytest.raises(gates.GateError, match="explicitly OPEN"):
        gates.gate_review()

def test_open_finding_passes_with_matching_waiver(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _manifest(tmp_path)
    open("artifacts/review.md", "w").write(
        "## TASK-1\n- issue: none — RESOLVED (ok)\n"
        "## TASK-2\n- issue: real defect — OPEN: violates AC-2\n")
    fh = gates.finding_sha256("TASK-2", "issue: real defect — OPEN: violates AC-2")
    assert gates.gate_review(waivers=[{"finding_sha256": fh}])

def test_waiver_for_nonexistent_finding_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _manifest(tmp_path)
    open("artifacts/review.md", "w").write(
        "## TASK-1\n- issue: none — RESOLVED (ok)\n"
        "## TASK-2\n- issue: real defect — OPEN: violates AC-2\n")
    fh = gates.finding_sha256("TASK-2", "issue: real defect — OPEN: violates AC-2")
    # A receipt that covers nothing leaves the OPEN finding uncovered…
    with pytest.raises(gates.GateError, match="explicitly OPEN"):
        gates.gate_review(waivers=[{"finding_sha256": "f" * 64}])
    # …and a stray receipt alongside the valid one is refused as
    # orphan/forgery even though coverage is complete.
    with pytest.raises(gates.GateError, match="orphan or forgery"):
        gates.gate_review(waivers=[{"finding_sha256": fh},
                                   {"finding_sha256": "f" * 64}])

def test_malformed_output_not_rescued_by_receipt(tmp_path, monkeypatch):
    """Parsing is pure: a receipt never rescues malformed reviewer output."""
    monkeypatch.chdir(tmp_path)
    _manifest(tmp_path)
    bad = "## TASK-1\n- issue: none — RESOLVED (ok)\n" \
          "## TASK-2\n- issue: perf — WAIVED: excuse\n"
    open("artifacts/review.md", "w").write(bad)
    fh = gates.finding_sha256("TASK-2", "issue: perf — WAIVED: excuse")
    with pytest.raises(gates.GateError, match="not a reviewer disposition"):
        gates.gate_review(waivers=[{"finding_sha256": fh}])

def test_duplicate_task_section_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _manifest(tmp_path)
    open("artifacts/review.md", "w").write(
        "## TASK-1\n- issue: none — RESOLVED (ok)\n"
        "## TASK-1\n- issue: none — RESOLVED (ok again)\n"
        "## TASK-2\n- issue: none — RESOLVED (ok)\n")
    with pytest.raises(gates.GateError, match="duplicate review section"):
        gates.gate_review()

def test_finding_outside_any_section_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _manifest(tmp_path)
    open("artifacts/review.md", "w").write(
        "- issue: orphan — RESOLVED (no section owns this)\n"
        "## TASK-1\n- issue: none — RESOLVED (ok)\n"
        "## TASK-2\n- issue: none — RESOLVED (ok)\n")
    with pytest.raises(gates.GateError, match="outside any task section"):
        gates.gate_review()

# ------------------------------------------------------------ waiver CLI ---

def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return env

def _cli(tmp_path, *args):
    return subprocess.run([sys.executable, "-m", "pipeline.approvals", *args],
                          capture_output=True, text=True, env=_env(),
                          cwd=tmp_path)

OPEN_LINE = "issue: real defect — OPEN: violates AC-2"

def _failed_review(tmp_path, findings=None):
    """A lifecycle with REVIEW gate_failed on OPEN finding(s); the failure
    row binds the review.md bytes (runner behavior post-F-005)."""
    findings = findings or {"TASK-2": [OPEN_LINE]}
    _manifest_dir = tmp_path  # cwd for the subprocess setup
    lines = ["# review.md", ""]
    for t in ("TASK-1", "TASK-2"):
        lines.append(f"## {t}")
        for f in findings.get(t, ["issue: none — RESOLVED (ok)"]):
            lines.append("- " + f)
        lines.append("")
    review_txt = "\n".join(lines)
    setup = (
        "import json, os, hashlib\n"
        "os.makedirs('artifacts/diff', exist_ok=True)\n"
        "for t in ('TASK-1','TASK-2'):\n"
        "    open(f'artifacts/diff/{t}.patch','w').write('diff')\n"
        "open('artifacts/diff/manifest.json','w').write(json.dumps({'diffs':"
        "[{'task': t, 'path': f'artifacts/diff/{t}.patch', 'scope': ['a.py']}"
        " for t in ('TASK-1','TASK-2')]}))\n"
        f"open('artifacts/review.md','w').write({review_txt!r})\n"
        "from pipeline import state\n"
        "state.emit('intake','started',detail={'lifecycle_id':'lctest0001'})\n"
        "state.emit('review','started')\n"
        "h=hashlib.sha256(open('artifacts/review.md','rb').read()).hexdigest()\n"
        "state.emit('review','gate_failed',detail={'error':'explicitly OPEN "
        "issue','artifact_sha256':h})\n")
    subprocess.run([sys.executable, "-c", setup], check=True, env=_env(),
                   cwd=tmp_path)

def _receipts(tmp_path):
    return [json.loads(l) for l in open(tmp_path / "state.jsonl")
            if json.loads(l)["event"] == "owner_waiver"]

def test_waive_by_index_records_full_bindings(tmp_path):
    _failed_review(tmp_path)
    r = _cli(tmp_path, "review", "waive", "TASK-2", "1",
             "owner accepts the deviation for this drill")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["recorded"] and out["lifecycle_id"] == "lctest0001"
    assert out["task_id"] == "TASK-2" and out["finding_index"] == 1
    assert out["finding_sha256"] == gates.finding_sha256("TASK-2", OPEN_LINE)
    assert out["attempt_started_hash"] and out["attempt_failed_hash"]
    assert out["review_md_sha256"] and out["diff_manifest_sha256"]
    assert out["reason"] == "owner accepts the deviation for this drill"

def test_waive_by_hash_prefix(tmp_path):
    _failed_review(tmp_path)
    fh = gates.finding_sha256("TASK-2", OPEN_LINE)
    r = _cli(tmp_path, "review", "waive", "TASK-2", fh[:12], "by hash")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["finding_sha256"] == fh

def test_double_waiver_refused(tmp_path):
    _failed_review(tmp_path)
    assert _cli(tmp_path, "review", "waive", "TASK-2", "1", "first").returncode == 0
    r = _cli(tmp_path, "review", "waive", "TASK-2", "1", "again")
    assert r.returncode == 2 and "irreversible" in r.stderr
    assert len(_receipts(tmp_path)) == 1

def test_waive_requires_failed_window(tmp_path):
    subprocess.run([sys.executable, "-c",
                    "from pipeline import state; "
                    "state.emit('intake','started',detail={'lifecycle_id':'lc'})"],
                   check=True, env=_env(), cwd=tmp_path)
    r = _cli(tmp_path, "review", "waive", "TASK-1", "1", "no failure")
    assert r.returncode == 2 and "never started" in r.stderr

def test_waive_refused_on_drifted_artifact(tmp_path):
    _failed_review(tmp_path)
    with open(tmp_path / "artifacts/review.md", "a") as f:
        f.write("\n# edited after the failure\n")
    r = _cli(tmp_path, "review", "waive", "TASK-2", "1", "stale bytes")
    assert r.returncode == 2 and "drifted" in r.stderr
    assert not _receipts(tmp_path)

def test_waive_selector_errors(tmp_path):
    _failed_review(tmp_path)
    assert _cli(tmp_path, "review", "waive", "TASK-2", "5", "x").returncode == 2
    assert _cli(tmp_path, "review", "waive", "TASK-2", "abc", "x").returncode == 2
    assert _cli(tmp_path, "review", "waive", "TASK-1", "1", "x").returncode == 2
    assert _cli(tmp_path, "review", "waive", "TASK-2", "1", "").returncode == 2
    assert _cli(tmp_path, "review", "waive", "TASK-2", "1").returncode == 2

def test_waive_rejects_other_gates_and_bad_task(tmp_path):
    assert _cli(tmp_path, "intake", "waive", "TASK-1", "1", "x").returncode == 2
    assert _cli(tmp_path, "review", "approve", "x").returncode == 2
    assert _cli(tmp_path, "review", "waive", "TASK-x", "1", "x").returncode == 2

def test_two_open_findings_need_individual_waivers(tmp_path):
    """A task-level waiver must not silently waive every finding."""
    _failed_review(tmp_path, findings={"TASK-2": [
        "issue: defect one — OPEN: violates AC-2",
        "issue: defect two — OPEN: violates AC-2"]})
    r1 = _cli(tmp_path, "review", "waive", "TASK-2", "1", "accept one")
    assert r1.returncode == 0, r1.stderr
    r2 = _cli(tmp_path, "review", "waive", "TASK-2", "2", "accept two")
    assert r2.returncode == 0, r2.stderr
    receipts = _receipts(tmp_path)
    assert len(receipts) == 2
    assert {r["detail"]["finding_index"] for r in receipts} == {1, 2}
    assert receipts[0]["detail"]["finding_sha256"] != \
        receipts[1]["detail"]["finding_sha256"]

# ------------------------------------------------------- runner resume -----

def _mock_lifecycle_to_review_failure(tmp_path, monkeypatch, finding):
    """Run the mock lifecycle to a REVIEW gate failure with one OPEN finding;
    returns nothing (ledger + artifacts are on disk in tmp_path)."""
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    state.emit("intake", "human_approve", detail={"reason": "ok"})
    assert runner.run_all() == "gate_open:plan"
    state.emit("plan", "human_approve", detail={"reason": "ok"})
    import pipeline.phases.review as review_mod
    real_run = review_mod.run
    def sabotaged(**kw):
        path = real_run(**kw)
        open(path, "a").write(f"\n- {finding}\n")
        return path
    monkeypatch.setattr(review_mod, "run", sabotaged)
    with pytest.raises(gates.GateError, match="explicitly OPEN"):
        runner.run_all()
    monkeypatch.setattr(review_mod, "run", real_run)  # restore for any resume

def test_waiver_resume_completes_review_without_recaller(tmp_path, monkeypatch):
    """OPEN → owner waiver → resume: NO second reviewer call, artifact
    preserved, deviation visible in validation.md, envelope reconciles."""
    _mock_lifecycle_to_review_failure(
        tmp_path, monkeypatch, "issue: planted defect — OPEN: violates AC-9")
    # The mock manifest's last section is TASK-3; the appended finding lands
    # under it.
    r = subprocess.run([sys.executable, "-m", "pipeline.approvals", "review",
                        "waive", "TASK-3", "1", "accepted for drill"],
                       capture_output=True, text=True, env=_env(), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    # Reviewer invocation is explicitly FORBIDDEN on the waiver path — any
    # call raises, so a passing resume proves no recall happened.
    import pipeline.phases.review as review_mod
    def _boom(**kw):
        raise AssertionError("reviewer invoked during waiver resume")
    monkeypatch.setattr(review_mod, "run", _boom)
    started_before = [e for e in state.rows() if e["phase"] == "review"
                      and e["event"] == "started"]
    assert runner.run_all() == "gate_open:validate"
    started_after = [e for e in state.rows() if e["phase"] == "review"
                     and e["event"] == "started"]
    assert len(started_after) == len(started_before)  # no reviewer recall
    comp = [e for e in state.rows() if e["phase"] == "review"
            and e["event"] == "complete"]
    assert comp and comp[-1]["detail"]["waived_findings"]
    assert comp[-1]["detail"]["waiver_receipts"]
    vtxt = open("artifacts/validation.md").read()
    assert "## Owner waivers" in vtxt
    assert comp[-1]["detail"]["waived_findings"][0] in vtxt
    assert "planted defect" in vtxt  # the deviation is visible at VALIDATE
    report = envelope.reconcile()
    assert report["ok"], report["failures"]

def test_waiver_completion_refuses_concurrent_rerun(tmp_path, monkeypatch):
    """P1 (2026-10-12): a competing REVIEW rerun intervening between the
    waiver gate evidence and the completion must refuse the completion —
    the transact verify re-checks the attempt window under the lock."""
    _mock_lifecycle_to_review_failure(
        tmp_path, monkeypatch, "issue: planted defect — OPEN: violates AC-9")
    r = subprocess.run([sys.executable, "-m", "pipeline.approvals", "review",
                        "waive", "TASK-3", "1", "accepted"],
                       capture_output=True, text=True, env=_env(), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    real_emit_gate = envelope.emit_gate
    def interleaved(phase, result, detail=""):
        real_emit_gate(phase, result, detail)
        if phase == "review" and result == "pass":
            state.emit("review", "started")  # the concurrent rerun lands here
    monkeypatch.setattr(envelope, "emit_gate", interleaved)
    with pytest.raises(gates.GateError, match="concurrent rerun"):
        runner.run_all()
    assert not [e for e in state.rows()
                if e["phase"] == "review" and e["event"] == "complete"]
    # …and the emitted gate evidence without a completion is visible to
    # reconciliation as an interruption.
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_INCOMPLETE" in f for f in report["failures"])

def test_waiver_resume_requires_exact_coverage(tmp_path, monkeypatch):
    """Two OPEN findings, one waived → loud refusal, no silent partial pass."""
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    state.emit("intake", "human_approve", detail={"reason": "ok"})
    assert runner.run_all() == "gate_open:plan"
    state.emit("plan", "human_approve", detail={"reason": "ok"})
    import pipeline.phases.review as review_mod
    real_run = review_mod.run
    def sabotaged(**kw):
        path = real_run(**kw)
        open(path, "a").write("\n- issue: defect one — OPEN: violates AC-9"
                              "\n- issue: defect two — OPEN: violates AC-9\n")
        return path
    monkeypatch.setattr(review_mod, "run", sabotaged)
    with pytest.raises(gates.GateError, match="explicitly OPEN"):
        runner.run_all()
    monkeypatch.setattr(review_mod, "run", real_run)  # restore for any resume
    r = subprocess.run([sys.executable, "-m", "pipeline.approvals", "review",
                        "waive", "TASK-3", "1", "only one"],
                       capture_output=True, text=True, env=_env(), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    with pytest.raises(gates.GateError, match="do not exactly cover"):
        runner.run_all()

def test_receipts_orphaned_by_rerun(tmp_path, monkeypatch):
    """A later review 'started' opens a new window; old receipts no longer
    drive a waiver resume (the owner-driven fresh rerun proceeds instead)."""
    _mock_lifecycle_to_review_failure(
        tmp_path, monkeypatch, "issue: planted defect — OPEN: violates AC-9")
    r = subprocess.run([sys.executable, "-m", "pipeline.approvals", "review",
                        "waive", "TASK-3", "1", "accepted"],
                       capture_output=True, text=True, env=_env(), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert runner._review_failed_window(state.lifecycle_rows()) is not None
    state.emit("review", "started")  # owner-driven rerun begins
    assert runner._review_failed_window(state.lifecycle_rows()) is None

def test_failed_attempt_hash_does_not_block_rerun(tmp_path, monkeypatch):
    """§4.1: failure A → rerun B (different bytes) → completion → resume.
    The failed attempt's recorded hash must not block the rerun's distinct
    completed bytes."""
    _mock_lifecycle_to_review_failure(
        tmp_path, monkeypatch, "issue: planted defect — OPEN: violates AC-9")
    fail = [e for e in state.rows() if e["event"] == "gate_failed"][-1]
    assert fail["detail"].get("artifact_sha256")  # failure binds the bytes
    # Operator-driven rerun: mock worker regenerates review.md (different
    # bytes — no planted finding), gate passes, phase completes.
    assert runner.run_all() == "gate_open:validate"
    comp = [e for e in state.rows() if e["phase"] == "review"
            and e["event"] == "complete"]
    assert comp
    assert comp[-1]["detail"]["artifact_sha256"] != \
        fail["detail"]["artifact_sha256"]
    # And resume past it is unblocked.
    state.emit("validate", "human_approve", detail={"reason": "ok"})
    assert runner.run_all() == "done"

# ------------------------------------------------------- validate gate -----

def _validation_doc(entries=None):
    lines = ["# validation.md", "", "Problem: x", "", "## Owner waivers", ""]
    if entries is None:
        lines.append("- None")
    else:
        for e in entries:
            lines += [f"- task: {e['task_id']}",
                      f"  finding_sha256: {e['finding_sha256']}",
                      f"  receipt: {e['receipt_hash']}",
                      f"  reason: {e['reason']}"]
            if e.get("finding_text") is not None:
                lines.append(f"  finding: {e['finding_text']}")
    lines += ["", "SIGN-OFF: pending\n"]
    return "\n".join(lines)

W1 = {"task_id": "TASK-2", "finding_sha256": "a" * 64, "receipt_hash": "b" * 64,
      "reason": "accepted", "finding_text": "issue: x — OPEN: y"}

def test_validate_waivers_none_clean(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/validation.md", "w").write(_validation_doc())
    assert gates.gate_validate(waivers=[])

def test_validate_waivers_section_required(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/validation.md", "w").write("# v\nSIGN-OFF: pending\n")
    with pytest.raises(gates.GateError, match="Owner waivers"):
        gates.gate_validate(waivers=[])

def test_validate_waivers_content_checked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/validation.md", "w").write(_validation_doc([W1]))
    assert gates.gate_validate(waivers=[W1])
    # omitted entry
    open("artifacts/validation.md", "w").write(_validation_doc())
    with pytest.raises(gates.GateError):
        gates.gate_validate(waivers=[W1])
    # extra entry
    W2 = dict(W1, finding_sha256="c" * 64)
    open("artifacts/validation.md", "w").write(_validation_doc([W1, W2]))
    with pytest.raises(gates.GateError):
        gates.gate_validate(waivers=[W1])
    # altered reason
    open("artifacts/validation.md", "w").write(
        _validation_doc([dict(W1, reason="altered")]))
    with pytest.raises(gates.GateError):
        gates.gate_validate(waivers=[W1])
    # altered finding text (review P1 2026-10-12: benign text beside genuine
    # hashes previously passed the gate)
    open("artifacts/validation.md", "w").write(
        _validation_doc([dict(W1, finding_text="issue: harmless cosmetic "
                                               "issue — OPEN: trivial")]))
    with pytest.raises(gates.GateError):
        gates.gate_validate(waivers=[W1])
    # missing finding line
    open("artifacts/validation.md", "w").write(
        _validation_doc([dict(W1, finding_text=None)]))
    with pytest.raises(gates.GateError):
        gates.gate_validate(waivers=[W1])

# ------------------------------------------------------------- reconcile ---

def test_reconcile_waiver_missing_receipt(tmp_path, monkeypatch):
    """A completion claiming waived findings with NO receipt is unproven
    authorization."""
    def ops():
        state.emit("intake", "started", detail={"lifecycle_id": "lcrec001"})
        state.emit("review", "started")
        state.emit("review", "gate_failed",
                   detail={"error": "OPEN", "artifact_sha256": "x" * 64})
        state.emit("review", "complete", artifact="artifacts/review.md",
                   detail={"artifact_sha256": "x" * 64,
                           "waived_findings": ["f" * 64]})
        envelope.emit_run_manifest({})
        envelope.emit_gate("review", "pass",
                           "owner-waiver resume (F-005); waived_findings=" + "f" * 64)
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/review.md", "w").write("x")
    ops()
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_MISSING" in f for f in report["failures"])

def test_reconcile_waiver_wrong_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec002"})
    state.emit("review", "started")
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    state.emit("review", "owner_waiver", detail={
        "lifecycle_id": "SOME-OTHER-LIFECYCLE", "finding_sha256": "f" * 64,
        "attempt_started_hash": "0" * 64, "attempt_failed_hash": "0" * 64})
    envelope.emit_run_manifest({})
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_AUTHORITY" in f for f in report["failures"])

def test_reconcile_waiver_unapplied_unorphaned(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec003"})
    state.emit("review", "started")
    s = state.rows()[-1]["hash"]
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    fh_row = state.rows()[-1]["hash"]
    state.emit("review", "owner_waiver",
               detail=_receipt_detail("lcrec003", "f" * 64, s, fh_row))
    envelope.emit_run_manifest({})
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_NOT_APPLIED" in f for f in report["failures"])

def test_reconcile_waiver_interruption(tmp_path, monkeypatch):
    """Gate evidence emitted, completion never landed → visible failure."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec004"})
    state.emit("review", "started")
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + "f" * 64)
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_INCOMPLETE" in f for f in report["failures"])

def _receipt_detail(lc, fh, s_hash, f_hash, review_h="x" * 64):
    return {"lifecycle_id": lc, "task_id": "TASK-2", "finding_index": 1,
            "finding_sha256": fh, "finding_text": "issue: x — OPEN: y",
            "reason": "accepted", "review_md_sha256": review_h,
            "diff_manifest_sha256": "y" * 64,
            "attempt_started_hash": s_hash, "attempt_failed_hash": f_hash}

def test_reconcile_stale_attempt_applied(tmp_path, monkeypatch):
    """P1: a receipt from attempt 1 applied by a completion AFTER a rerun
    started is a stale-window application — even if bytes are identical."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    fh = "f" * 64
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec005"})
    state.emit("review", "started")
    s1 = state.rows()[-1]["hash"]
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    f1 = state.rows()[-1]["hash"]
    state.emit("review", "owner_waiver",
               detail=_receipt_detail("lcrec005", fh, s1, f1))
    receipt_h = state.rows()[-1]["hash"]
    state.emit("review", "started")  # the rerun orphans attempt 1's window
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64,  # identical bytes
                       "waived_findings": [fh],
                       "waiver_receipts": [receipt_h]})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + fh)
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_STALE_ATTEMPT" in f for f in report["failures"])

def test_reconcile_completion_naming_non_receipt(tmp_path, monkeypatch):
    """A completion whose waiver_receipts point at a non-receipt row fails."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    fh = "f" * 64
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec006"})
    state.emit("review", "started")
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    not_a_receipt = state.rows()[-1]["hash"]  # the gate_failed row itself
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64, "waived_findings": [fh],
                       "waiver_receipts": [not_a_receipt]})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + fh)
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_AUTHORITY" in f and "not an owner_waiver row" in f
               for f in report["failures"])

def test_reconcile_coverage_mismatch(tmp_path, monkeypatch):
    """Receipts resolve and verify, but their findings do not exactly match
    the completion's waived_findings."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec007"})
    state.emit("review", "started")
    s1 = state.rows()[-1]["hash"]
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    f1 = state.rows()[-1]["hash"]
    state.emit("review", "owner_waiver",
               detail=_receipt_detail("lcrec007", "a" * 64, s1, f1))
    receipt_h = state.rows()[-1]["hash"]
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64,
                       "waived_findings": ["b" * 64],  # different finding
                       "waiver_receipts": [receipt_h]})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + "b" * 64)
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_COVERAGE" in f for f in report["failures"])

def test_applied_waivers_resolve_exact_receipt_rows(tmp_path, monkeypatch):
    """P1: with two attempts producing IDENTICAL bytes, the inventory must
    come from the completion's waiver_receipts row hashes — the orphaned
    attempt-1 receipt must not leak in."""
    monkeypatch.chdir(tmp_path)
    fh = "f" * 64
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec008"})
    for attempt in (1, 2):
        state.emit("review", "started")
        s = state.rows()[-1]["hash"]
        state.emit("review", "gate_failed",
                   detail={"error": "OPEN", "artifact_sha256": "x" * 64})
        f = state.rows()[-1]["hash"]
        state.emit("review", "owner_waiver",
                   detail=_receipt_detail("lcrec008", fh, s, f))
        if attempt == 2:
            receipt2 = state.rows()[-1]["hash"]
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64, "waived_findings": [fh],
                       "waiver_receipts": [receipt2]})
    applied = runner._applied_waivers(state.lifecycle_rows())
    assert len(applied) == 1
    assert applied[0]["receipt_hash"] == receipt2
    assert applied[0]["attempt_started_hash"] != receipt2  # sanity: attempt 2

# ------------------------------------------- repair pass 2 (2026-10-12) ---

def _waive_planted(tmp_path):
    r = subprocess.run([sys.executable, "-m", "pipeline.approvals", "review",
                        "waive", "TASK-3", "1", "accepted"],
                       capture_output=True, text=True, env=_env(), cwd=tmp_path)
    assert r.returncode == 0, r.stderr

def test_waiver_completion_rechecks_manifest_mutation(tmp_path, monkeypatch):
    """P1: the CODE manifest is rechecked under the completion lock —
    mutation between gate evidence and completion refuses."""
    _mock_lifecycle_to_review_failure(
        tmp_path, monkeypatch, "issue: planted defect — OPEN: violates AC-9")
    _waive_planted(tmp_path)
    real_emit_gate = envelope.emit_gate
    def interleaved(phase, result, detail=""):
        real_emit_gate(phase, result, detail)
        if phase == "review" and result == "pass":
            open("artifacts/diff/manifest.json", "a").write("\n# mutated\n")
    monkeypatch.setattr(envelope, "emit_gate", interleaved)
    with pytest.raises(gates.GateError, match="manifest changed"):
        runner.run_all()
    assert not [e for e in state.rows()
                if e["phase"] == "review" and e["event"] == "complete"]

def test_waiver_completion_rechecks_manifest_deletion(tmp_path, monkeypatch):
    _mock_lifecycle_to_review_failure(
        tmp_path, monkeypatch, "issue: planted defect — OPEN: violates AC-9")
    _waive_planted(tmp_path)
    real_emit_gate = envelope.emit_gate
    def interleaved(phase, result, detail=""):
        real_emit_gate(phase, result, detail)
        if phase == "review" and result == "pass":
            os.remove("artifacts/diff/manifest.json")
    monkeypatch.setattr(envelope, "emit_gate", interleaved)
    with pytest.raises(gates.GateError, match="manifest deleted"):
        runner.run_all()
    assert not [e for e in state.rows()
                if e["phase"] == "review" and e["event"] == "complete"]

def _ledgered_waiver_completion(lc, manifest_h="y" * 64):
    """A complete, well-formed waiver chain; returns the receipt detail."""
    fh = "f" * 64
    state.emit("intake", "started", detail={"lifecycle_id": lc})
    state.emit("code", "complete", artifact="artifacts/diff/manifest.json",
               detail={"artifact_sha256": manifest_h})
    state.emit("review", "started")
    s1 = state.rows()[-1]["hash"]
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    f1 = state.rows()[-1]["hash"]
    state.emit("review", "owner_waiver",
               detail=_receipt_detail(lc, fh, s1, f1))
    rh = state.rows()[-1]["hash"]
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64, "waived_findings": [fh],
                       "waiver_receipts": [rh]})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + fh)
    return fh

def test_reconcile_complete_valid_waiver_chain_is_clean(tmp_path, monkeypatch):
    """Positive control: a fully bound waiver chain reconciles clean."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/review.md", "w").write("x")
    _ledgered_waiver_completion("lcrec100")
    report = envelope.reconcile()
    assert report["ok"], report["failures"]

def test_reconcile_receipt_missing_binding_field(tmp_path, monkeypatch):
    """P1: a receipt missing any required binding field fails — incomplete
    claims never skip verification."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/review.md", "w").write("x")
    fh = "f" * 64
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec101"})
    state.emit("code", "complete", artifact="artifacts/diff/manifest.json",
               detail={"artifact_sha256": "y" * 64})
    state.emit("review", "started")
    s1 = state.rows()[-1]["hash"]
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    f1 = state.rows()[-1]["hash"]
    d = _receipt_detail("lcrec101", fh, s1, f1)
    del d["diff_manifest_sha256"]
    state.emit("review", "owner_waiver", detail=d)
    rh = state.rows()[-1]["hash"]
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64, "waived_findings": [fh],
                       "waiver_receipts": [rh]})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + fh)
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_AUTHORITY" in f and "lacks required" in f
               for f in report["failures"])

def test_reconcile_attempt_pair_mismatch(tmp_path, monkeypatch):
    """started+failed hashes that both exist but belong to DIFFERENT
    attempts do not form a window."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/review.md", "w").write("x")
    fh = "f" * 64
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec102"})
    state.emit("code", "complete", artifact="artifacts/diff/manifest.json",
               detail={"artifact_sha256": "y" * 64})
    state.emit("review", "started")
    s1 = state.rows()[-1]["hash"]
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    state.emit("review", "started")  # attempt 2
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "x" * 64})
    f2 = state.rows()[-1]["hash"]
    # receipt binds attempt-1's started with attempt-2's failure
    state.emit("review", "owner_waiver",
               detail=_receipt_detail("lcrec102", fh, s1, f2))
    rh = state.rows()[-1]["hash"]
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64, "waived_findings": [fh],
                       "waiver_receipts": [rh]})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + fh)
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("do not form one attempt" in f for f in report["failures"])

def test_reconcile_wrong_manifest_binding(tmp_path, monkeypatch):
    """The receipt's manifest binding must equal the completed CODE
    manifest's hash."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/review.md", "w").write("x")
    _ledgered_waiver_completion("lcrec103", manifest_h="m" * 64)
    # ^ receipt binds diff_manifest_sha256 "y"*64 (the _receipt_detail
    # default) while CODE completed "m"*64
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("WAIVER_MANIFEST" in f for f in report["failures"])

def test_reconcile_failure_without_artifact_hash_unbindable(tmp_path, monkeypatch):
    """P1 (third pass): the bound failure must carry the failed bytes' hash —
    a receipt against an unbound failure fails authority."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/review.md", "w").write("x")
    fh = "f" * 64
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec104"})
    state.emit("code", "complete", artifact="artifacts/diff/manifest.json",
               detail={"artifact_sha256": "y" * 64})
    state.emit("review", "started")
    s1 = state.rows()[-1]["hash"]
    state.emit("review", "gate_failed", detail={"error": "OPEN"})  # no hash
    f1 = state.rows()[-1]["hash"]
    state.emit("review", "owner_waiver",
               detail=_receipt_detail("lcrec104", fh, s1, f1))
    rh = state.rows()[-1]["hash"]
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64, "waived_findings": [fh],
                       "waiver_receipts": [rh]})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + fh)
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("failed bytes are unbound" in f for f in report["failures"])

def test_reconcile_receipt_must_bind_the_failed_bytes(tmp_path, monkeypatch):
    """P1 (third pass): receipt + completion naming review bytes DIFFERENT
    from the bound failure's recorded hash fail — the exact-evidence chain
    is failure bytes == receipt bytes == completion bytes."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/review.md", "w").write("x")
    fh = "f" * 64
    state.emit("intake", "started", detail={"lifecycle_id": "lcrec105"})
    state.emit("code", "complete", artifact="artifacts/diff/manifest.json",
               detail={"artifact_sha256": "y" * 64})
    state.emit("review", "started")
    s1 = state.rows()[-1]["hash"]
    # the failure recorded DIFFERENT bytes than the receipt/completion claim
    state.emit("review", "gate_failed",
               detail={"error": "OPEN", "artifact_sha256": "z" * 64})
    f1 = state.rows()[-1]["hash"]
    state.emit("review", "owner_waiver",
               detail=_receipt_detail("lcrec105", fh, s1, f1))  # "x"*64
    rh = state.rows()[-1]["hash"]
    state.emit("review", "complete", artifact="artifacts/review.md",
               detail={"artifact_sha256": "x" * 64, "waived_findings": [fh],
                       "waiver_receipts": [rh]})
    envelope.emit_run_manifest({})
    envelope.emit_gate("review", "pass",
                       "owner-waiver resume (F-005); waived_findings=" + fh)
    report = envelope.reconcile()
    assert not report["ok"]
    assert any("not the failed bytes" in f for f in report["failures"])

def test_resume_validator_rejects_receipt_against_unbound_failure(tmp_path, monkeypatch):
    """The same check fires on the runner's resume path (shared validator):
    hand-edit the failure row's hash binding away and the resume refuses."""
    _mock_lifecycle_to_review_failure(
        tmp_path, monkeypatch, "issue: planted defect — OPEN: violates AC-9")
    _waive_planted(tmp_path)
    # Simulate a failure row whose artifact binding disagrees with the
    # receipt: rewrite review.md is caught elsewhere, so instead verify the
    # validator directly against the live window rows.
    rows = state.lifecycle_rows()
    win = runner._review_failed_window(rows)
    assert win is not None
    last_start, fail, receipts = win
    from pipeline import waiver_proof
    assert waiver_proof.check_receipt_bindings(
        receipts[0], rows, state.lifecycle()["id"]) == []
    forged_fail = dict(fail, detail={"error": "OPEN"})  # hash binding removed
    forged = [r if r.get("hash") != fail.get("hash") else forged_fail
              for r in rows]
    # the forged row's stored hash no longer matches its content, so find the
    # validator's failure against the forged window rows
    errs = waiver_proof.check_receipt_bindings(
        receipts[0], forged, state.lifecycle()["id"])
    assert any("unbound" in e or "stale or foreign" in e for e in errs)
