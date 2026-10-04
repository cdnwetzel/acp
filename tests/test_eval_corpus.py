"""Eval corpus + harness: schema/semantic validation, wrong-layer rule,
fixture replay, leakage, holdouts, baseline determinism, and the
cannot-open-a-gate proof. The lane is evidence-only by contract."""
import json, os
import pytest
from eval import corpus as corpus_mod, harness
from pipeline import gates, runner


# --- helpers ---------------------------------------------------------------

def _valid_case(**over):
    """A schema-valid case whose payload exists (reuses a committed fixture)."""
    rec = {
        "case_id": "reg-test-001", "class": "regression",
        "target": {"phase": "test", "role": "sdet"},
        "input": {"brief_or_payload": "eval/cases/reg-scope-001/payload.json"},
        "execution": {"requires_model": False, "layer": "harness"},
        "expected": {"outcome": "fail", "catching_layer": "scope",
                     "detail": "synthetic test case for loader semantics"},
        "check": {"executor": "scope_diff"},
        "scoring_tiers": ["deterministic"],
        "provenance": {"source_run_or_fixture": "synthetic",
                       "fixture_sha256": harness._sha256_file(
                           os.path.join(corpus_mod.REPO_ROOT,
                                        "eval/cases/reg-scope-001/payload.json")),
                       "authored": "2026-10-04"},
        "holdout": False, "baseline_id": "baseline-2026-10",
    }
    rec.update(over)
    return rec


def _write_corpus(tmp_path, records):
    path = tmp_path / "corpus.jsonl"
    with open(path, "w") as f:
        for r in records:
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    return str(path)


# --- committed corpus ------------------------------------------------------

def test_committed_corpus_loads():
    cases = corpus_mod.load_corpus()
    assert len(cases) >= 14
    classes = {c["class"] for c in cases}
    assert classes == {"prompt_injection", "malformed_output", "scope_write",
                       "endpoint", "regression", "holdout"}


def test_fixture_replay_reproduces_original_catch(tmp_path):
    """Every deterministic case replays through its real layer and lands on
    the expected outcome+layer — the regression fixtures still bite."""
    summary = harness.run(results_dir=str(tmp_path))
    assert summary["executed"] >= 13
    assert summary["red"] == [], summary["red"]


# --- schema / semantics ----------------------------------------------------

def test_malformed_case_is_loud(tmp_path):
    bad = _write_corpus(tmp_path, ['{"case_id": "reg-x", broken'])
    with pytest.raises(corpus_mod.CorpusError, match="invalid JSON"):
        corpus_mod.load_corpus(bad)
    missing = _valid_case()
    del missing["expected"]
    with pytest.raises(corpus_mod.CorpusError, match="schema violation"):
        corpus_mod.load_case(missing)


def test_f002_outcome_layer_rules():
    with pytest.raises(corpus_mod.CorpusError, match="pass requires"):
        corpus_mod.load_case(_valid_case(
            expected={"outcome": "pass", "catching_layer": "gate",
                      "detail": "a pass must not pretend a gate caught it"}))
    with pytest.raises(corpus_mod.CorpusError, match="human_escalation requires"):
        corpus_mod.load_case(_valid_case(
            expected={"outcome": "human_escalation", "catching_layer": "schema",
                      "detail": "escalation caught by schema is wrong"}))
    with pytest.raises(corpus_mod.CorpusError, match="named catching_layer"):
        corpus_mod.load_case(_valid_case(
            expected={"outcome": "fail", "catching_layer": "none",
                      "detail": "a fail must name its catching layer"}))
    with pytest.raises(corpus_mod.CorpusError, match="named catching_layer"):
        corpus_mod.load_case(_valid_case(
            expected={"outcome": "limitation", "catching_layer": "human",
                      "detail": "a limitation needs its reporting layer"}))


def test_f003_clarity_stop_mapping():
    base = {"outcome": "limitation", "catching_layer": "gate",
            "detail": corpus_mod.CLARITY_DETAIL}
    ok = _valid_case(case_id="net-pxx-clarity-999",
                     **{"class": "endpoint"},
                     expected=dict(base))
    ok["execution"] = {"requires_model": True, "layer": "worker"}
    del ok["check"]
    corpus_mod.load_case(ok)  # the one valid representation
    for bad_outcome, bad_layer in (("pass", "none"), ("fail", "gate"),
                                   ("human_escalation", "human")):
        bad = _valid_case(case_id="net-pxx-clarity-998",
                          **{"class": "endpoint"},
                          expected={"outcome": bad_outcome,
                                    "catching_layer": bad_layer,
                                    "detail": corpus_mod.CLARITY_DETAIL})
        bad["execution"] = {"requires_model": True, "layer": "worker"}
        del bad["check"]
        with pytest.raises(corpus_mod.CorpusError, match="F-003"):
            corpus_mod.load_case(bad)


def test_execution_pairing_and_executor_known():
    with pytest.raises(corpus_mod.CorpusError, match="layer 'harness'"):
        corpus_mod.load_case(_valid_case(
            execution={"requires_model": False, "layer": "worker"}))
    with pytest.raises(corpus_mod.CorpusError, match="layer 'worker'"):
        corpus_mod.load_case(_valid_case(
            execution={"requires_model": True, "layer": "harness"}))
    with pytest.raises(corpus_mod.CorpusError, match="known executor"):
        corpus_mod.load_case(_valid_case(check={"executor": "no_such_executor"}))


def test_fixture_hash_must_match_committed_payload():
    bad = _valid_case()
    bad["provenance"]["fixture_sha256"] = "0" * 64
    with pytest.raises(corpus_mod.CorpusError, match="fixture_sha256 mismatch"):
        corpus_mod.load_case(bad)
    missing = _valid_case()
    missing["input"]["brief_or_payload"] = "eval/cases/reg-test-001/nope.json"
    with pytest.raises(corpus_mod.CorpusError, match="does not exist"):
        corpus_mod.load_case(missing)


def test_duplicate_case_ids_rejected(tmp_path):
    path = _write_corpus(tmp_path, [_valid_case(), _valid_case()])
    with pytest.raises(corpus_mod.CorpusError, match="duplicate case_id"):
        corpus_mod.load_corpus(path)


# --- wrong-layer (wrong-reason) rule ----------------------------------------

def test_wrong_layer_is_red(tmp_path):
    """A case caught by an unrelated layer counts red even though SOMETHING
    stopped it — the corpus measures whether the intended invariant works."""
    case = _valid_case(
        expected={"outcome": "fail", "catching_layer": "schema",
                  "detail": "deliberately wrong layer: the payload is a scope case"})
    path = _write_corpus(tmp_path, [case])
    summary = harness.run(corpus_path=path, results_dir=str(tmp_path))
    assert summary["red"] == ["reg-test-001"]
    results = tmp_path / (summary["run_id"] + ".jsonl")
    rec = [json.loads(l) for l in open(results) if "case_result" in l][0]
    assert rec["deterministic"] == "red"
    assert "WRONG-REASON" in rec["detail"]


def test_executor_crash_is_red_not_silent(tmp_path):
    case = _valid_case(check={"executor": "verbatim_trace"})  # wrong payload shape
    path = _write_corpus(tmp_path, [case])
    summary = harness.run(corpus_path=path, results_dir=str(tmp_path))
    assert summary["red"] == ["reg-test-001"]


# --- holdouts ---------------------------------------------------------------

def test_holdouts_execute_green_on_renamed_worlds(tmp_path):
    summary = harness.run(results_dir=str(tmp_path))
    results = tmp_path / (summary["run_id"] + ".jsonl")
    recs = {json.loads(l)["case_id"]: json.loads(l)
            for l in open(results) if "case_result" in l}
    hold = {cid: r for cid, r in recs.items() if r["holdout"]}
    assert hold, "corpus must contain executed holdouts"
    assert all(r["deterministic"] == "green" for r in hold.values()), hold


# --- leakage ----------------------------------------------------------------

def test_prompt_builders_never_read_corpus_or_fixtures():
    """Static leakage control: no pipeline module may reference the eval
    corpus, its cases, results, or test fixtures. Extends the
    never-read-transcripts invariant."""
    forbidden = ("eval/corpus", "eval/cases", "eval/results", "eval/baselines",
                 "tests/fixtures", "corpus.jsonl")
    roots = [os.path.join(corpus_mod.REPO_ROOT, "pipeline")]
    offenders = []
    for root in roots:
        for dirpath, _, files in os.walk(root):
            for name in files:
                if not name.endswith(".py"):
                    continue
                p = os.path.join(dirpath, name)
                src = open(p).read()
                for f in forbidden:
                    if f in src:
                        offenders.append(f"{p}: {f}")
                if "from eval" in src or "import eval" in src:
                    offenders.append(f"{p}: imports the eval lane")
    assert offenders == [], offenders


# --- cannot open a gate ------------------------------------------------------

def test_eval_results_cannot_open_a_gate(tmp_path, monkeypatch):
    """An all-green eval result planted in the run directory changes no gate
    outcome: gate_intake still fails on a bad artifact and passes on a good
    one — gates never consult the eval lane."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    results = tmp_path / "eval" / "results"
    results.mkdir(parents=True)
    (results / "all-green.jsonl").write_text(json.dumps({
        "type": "case_result", "deterministic": "green",
        "case_id": "reg-test-001"}) + "\n")
    with open("artifacts/intake.json", "w") as f:
        f.write("{not json")
    with pytest.raises(gates.GateError):
        gates.gate_intake()
    with open("artifacts/intake.json", "w") as f:
        json.dump({"problem": "a real problem statement",
                   "constraints": ["stdlib only"],
                   "acceptance_criteria": ["AC-1: x"],
                   "required_imports": []}, f)
    assert gates.gate_intake() is True


def test_gates_module_never_references_eval_lane():
    src = open(gates.__file__).read() + open(runner.__file__).read()
    assert "eval" not in src.lower().replace("evaluat", ""), \
        "gates/runner must not reference the eval lane"


# --- baseline (F-001) ---------------------------------------------------------

def test_baseline_freeze_and_byte_deterministic_diff(tmp_path):
    r1 = harness.run(results_dir=str(tmp_path / "res"))
    r2 = harness.run(results_dir=str(tmp_path / "res"))
    entry = harness.freeze(r1["run_id"], "baseline-test",
                           results_dir=str(tmp_path / "res"),
                           baselines_dir=str(tmp_path / "base"),
                           index_path=str(tmp_path / "index.json"))
    for key in ("baseline_id", "source_commit", "corpus_sha256",
                "case_set_sha256", "expected_outcome_sha256", "manifest_sha256"):
        assert key in entry, key
    report = harness.diff(os.path.join(tmp_path / "res", r2["run_id"] + ".jsonl"),
                          "baseline-test", baselines_dir=str(tmp_path / "base"))
    assert report["match"] is True and report["differences"] == []
    # tamper: a deterministic flip must be reported, never absorbed
    tampered = tmp_path / "tampered.jsonl"
    lines = open(os.path.join(tmp_path / "res", r2["run_id"] + ".jsonl")).readlines()
    rec = json.loads(lines[1])
    rec["deterministic"] = "red" if rec["deterministic"] == "green" else "green"
    lines[1] = json.dumps(rec) + "\n"
    tampered.write_text("".join(lines))
    report = harness.diff(str(tampered), "baseline-test",
                          baselines_dir=str(tmp_path / "base"))
    assert report["match"] is False and report["differences"]


# --- model-tier discipline ----------------------------------------------------

def test_model_cases_never_executed_in_this_pass(tmp_path):
    summary = harness.run(results_dir=str(tmp_path), authorized_model=True)
    results = tmp_path / (summary["run_id"] + ".jsonl")
    head = json.loads(open(results).readline())
    assert head["authorized_model"] is True
    recs = [json.loads(l) for l in open(results) if "case_result" in l]
    model_cases = [r for r in recs if r["deterministic"] == "not_executed"]
    assert len(model_cases) >= 5
    assert all(r["observed"] is None for r in model_cases)
    assert all("owner-authorized" in r["detail"] for r in model_cases)
