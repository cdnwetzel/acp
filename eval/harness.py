"""Eval harness — the evidence-only lane (owner boundary 2026-10-04).

Runs corpus cases and records outcomes. This pass implements execution for
requires_model=false (harness-layer) cases only; model-dependent cases are
always recorded not_executed in this pass — wiring them to governed endpoints
is a separate owner-authorized step, same as drills.

Rules in force:
- Evidence only: a result is never a gate input; the lane cannot open a gate.
- Wrong-reason rule: a case is green only when the OBSERVED outcome AND
  catching_layer equal the expected pair exactly — caught by an unrelated
  earlier check counts red.
- Executor crash = red with the error text, loud in the summary.
- results/ and baselines/<id>/ are operational state (gitignored);
  baseline-index.json is committed (F-001 durability split: the committed
  index makes a baseline addressable, the preserved bundle supplies details).
- Every run record carries run identity (run_id, code commit, corpus hash,
  ledger head) so a result is reproducible and attributable.

CLI:
  python3 -m eval.harness run [--authorized-model]
  python3 -m eval.harness freeze <run_id> <baseline_id>
  python3 -m eval.harness diff <results-file> <baseline_id>
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, time, uuid

from eval import corpus as corpus_mod
from pipeline.worker import WorkerError, check_access, extract_one_json
from pipeline.validate import load as _load, validate as _validate, ValidationError
from pipeline.phases import verify as verify_phase
from pipeline.phases import code as code_phase
from pipeline import required_imports as ri

REPO_ROOT = corpus_mod.REPO_ROOT
RESULTS_DIR = os.path.join(REPO_ROOT, "eval", "results")
BASELINES_DIR = os.path.join(REPO_ROOT, "eval", "baselines")
BASELINE_INDEX = os.path.join(REPO_ROOT, "eval", "baseline-index.json")


class HarnessError(Exception):
    """Harness failure — loud, never silently skipped."""


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _payload(case):
    return os.path.join(REPO_ROOT, case["input"]["brief_or_payload"])


# --- executors: replay a fixture through its real pipeline layer -----------
# Each returns (observed_outcome, observed_layer, detail).

def _ex_extract_json(sandbox, case):
    try:
        extract_one_json(open(_payload(case)).read())
    except WorkerError as e:
        return ("fail", "schema", f"extract_one_json raised: {e}")
    return ("pass", "none", "exactly one JSON object extracted")


def _ex_contract_check(sandbox, case):
    schema_name = case["check"]["args"]["schema"]
    schema = _load(os.path.join(REPO_ROOT, "contracts", schema_name))
    try:
        doc = _load(_payload(case))
        _validate(schema, doc)
    except (ValidationError, json.JSONDecodeError) as e:
        return ("fail", "schema", f"contract validation raised: {e}")
    return ("pass", "none", "payload validates against " + schema_name)


def _ex_verbatim_trace(sandbox, case):
    spec = json.load(open(_payload(case)))
    doc_path = os.path.join(REPO_ROOT, spec["doc_file"])
    intake_path = os.path.join(REPO_ROOT, spec["intake_file"])
    # replay integrity: aux fixture hashes are pinned in the payload
    for path, cited in ((doc_path, spec["doc_sha256"]),
                        (intake_path, spec["intake_sha256"])):
        if _sha256_file(path) != cited:
            raise HarnessError(f"aux fixture hash mismatch: {path}")
    acs = json.load(open(intake_path))["acceptance_criteria"]
    # 2026-10-10 (F-001 structured VERIFY): the fixtures are historical
    # markdown docs, but the contract now lives on the JSON criterion FIELD.
    # Replay the same fixture text through the one shared criterion-cell
    # parser, then apply the JSON-era traceability rule to those cells —
    # escape corruption and paraphrase are medium-independent and must
    # still be caught.
    from pipeline.gates import verdict_rows
    cells = [c for c in verdict_rows(open(doc_path).read())
             if c[0] != "acceptance criterion"]
    untraced = verify_phase._untraced_criteria(
        {"rows": [{"criterion": c[0]} for c in cells]}, acs)
    if untraced:
        return ("fail", "gate",
                f"verbatim pre-write check: {len(untraced)} of {len(acs)} "
                f"criteria not byte-for-byte traced; first: {untraced[0][:60]!r}")
    return ("pass", "none", "all criteria byte-for-byte traced")


def _ex_ast_imports(sandbox, case):
    spec = json.load(open(_payload(case)))
    evidence = ri.verify(os.path.join(REPO_ROOT, spec["repo"]),
                         spec["required_imports"])
    if evidence["ok"]:
        return ("pass", "none", "all required imports verified against AST")
    failed = [f"{c['symbol']} from {c['from']}: {c['detail']}"
              for c in evidence["checks"] if c["result"] != "pass"]
    return ("fail", "ast", "; ".join(failed))


def _ex_endpoint_down(sandbox, case):
    spec = json.load(open(_payload(case)))
    try:
        check_access(spec["endpoint_record"])
    except WorkerError as e:
        detail = str(e)
        if "start it with" not in detail:
            return ("fail", "runtime",
                    "fail-closed but WITHOUT the operator guidance: " + detail[:120])
        return ("fail", "runtime", "fail-closed with guidance: " + detail[:120])
    return ("pass", "none", "endpoint was reachable")


def _ex_scope_diff(sandbox, case):
    spec = json.load(open(_payload(case)))
    offenders = code_phase.scope_offenders(spec["changed"], spec["scope"])
    if offenders:
        return ("fail", "scope", f"out-of-scope edits caught: {offenders}")
    return ("pass", "none", "no out-of-scope edits")


EXECUTORS = {
    "extract_json": _ex_extract_json,
    "contract_check": _ex_contract_check,
    "verbatim_trace": _ex_verbatim_trace,
    "ast_imports": _ex_ast_imports,
    "endpoint_down": _ex_endpoint_down,
    "scope_diff": _ex_scope_diff,
}


def _code_commit():
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _ledger_head():
    ledger = os.path.join(os.getcwd(), "state.jsonl")
    if not os.path.exists(ledger):
        return None
    from pipeline import state
    rows = state.rows(ledger)
    return rows[-1].get("hash") if rows else None


def run(corpus_path=corpus_mod.CORPUS, results_dir=RESULTS_DIR,
        authorized_model=False):
    """Execute the corpus. Deterministic cases run in a throwaway sandbox;
    model-dependent cases are recorded not_executed (this pass does not wire
    live model execution — see module docstring). Returns the summary dict."""
    cases = corpus_mod.load_corpus(corpus_path)
    run_id = "evalrun-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    head = {
        "type": "eval_run", "run_id": run_id, "ts": _now(),
        "code_commit": _code_commit(),
        "corpus_sha256": _sha256_file(corpus_path),
        "ledger_head": _ledger_head(),
        "authorized_model": authorized_model,
        "note": "evidence only — results are never gate inputs",
    }
    records = []
    for case in cases:
        cid = case["case_id"]
        rec = {"type": "case_result", "run_id": run_id, "case_id": cid,
               "class": case["class"], "holdout": case["holdout"],
               "expected": case["expected"],
               "model": "not_applicable", "human": "pending"}
        if case["execution"]["requires_model"]:
            rec.update(observed=None, deterministic="not_executed",
                       detail="requires owner-authorized live run "
                              "(not wired in this pass)")
        else:
            sandbox = tempfile.mkdtemp(prefix="acp-eval-")
            try:
                outcome, layer, detail = EXECUTORS[case["check"]["executor"]](
                    sandbox, case)
            except Exception as e:
                outcome, layer, detail = ("fail", "runtime",
                                          f"executor error: {e!r}")
            finally:
                shutil.rmtree(sandbox, ignore_errors=True)
            exp = case["expected"]
            green = (outcome, layer) == (exp["outcome"], exp["catching_layer"])
            rec.update(observed={"outcome": outcome, "catching_layer": layer,
                                 "detail": detail},
                       deterministic="green" if green else "red",
                       detail=None if green else
                       f"WRONG-REASON check: expected "
                       f"({exp['outcome']},{exp['catching_layer']}), "
                       f"observed ({outcome},{layer})")
        records.append(rec)
    os.makedirs(results_dir, exist_ok=True)
    results_path = os.path.join(results_dir, run_id + ".jsonl")
    with open(results_path, "w") as f:
        f.write(json.dumps(head) + "\n")
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    executed = [r for r in records if r["deterministic"] != "not_executed"]
    red = [r["case_id"] for r in executed if r["deterministic"] == "red"]
    summary = {
        "run_id": run_id, "results": results_path,
        "cases": len(records), "executed": len(executed),
        "not_executed": len(records) - len(executed),
        "green": len(executed) - len(red), "red": red,
    }
    with open(os.path.join(results_dir, run_id + ".md"), "w") as f:
        f.write(f"# Eval run {run_id}\n\n"
                f"- code commit: {head['code_commit']}\n"
                f"- corpus sha256: {head['corpus_sha256']}\n"
                f"- ledger head: {head['ledger_head']}\n"
                f"- cases: {len(records)}; executed: {len(executed)}; "
                f"not_executed: {len(records) - len(executed)}\n"
                f"- deterministic green: {summary['green']}/{len(executed)}\n"
                f"- red: {red or 'none'}\n\n"
                "Evidence only. This result cannot open a gate.\n")
    return summary


def _read_results(path):
    lines = [json.loads(l) for l in open(path) if l.strip()]
    return lines[0], lines[1:]


def freeze(run_id, baseline_id, results_dir=RESULTS_DIR,
           baselines_dir=BASELINES_DIR, index_path=BASELINE_INDEX):
    """F-001 durability split: operational baseline bundle under
    baselines/<id>/ (gitignored) + committed index entry (addressable:
    baseline_id, source commit, corpus hash, case-set hash, expected-outcome
    hash, manifest hash)."""
    results_path = os.path.join(results_dir, run_id + ".jsonl")
    if not os.path.exists(results_path):
        raise HarnessError(f"no results for run {run_id}: {results_path}")
    head, records = _read_results(results_path)
    bdir = os.path.join(baselines_dir, baseline_id)
    os.makedirs(bdir, exist_ok=True)
    shutil.copyfile(results_path, os.path.join(bdir, "results.jsonl"))
    manifest = {
        "baseline_id": baseline_id, "created_at": _now(),
        "source_run_id": run_id, "source_commit": head["code_commit"],
        "corpus_sha256": head["corpus_sha256"],
        "case_set": sorted(r["case_id"] for r in records),
        "expected_outcomes": {r["case_id"]: [r["expected"]["outcome"],
                                             r["expected"]["catching_layer"]]
                              for r in records},
        "deterministic": {r["case_id"]: r["deterministic"] for r in records},
    }
    manifest_path = os.path.join(bdir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    entry = {
        "baseline_id": baseline_id,
        "source_commit": manifest["source_commit"],
        "corpus_sha256": manifest["corpus_sha256"],
        "case_set_sha256": hashlib.sha256(
            _canonical(manifest["case_set"]).encode()).hexdigest(),
        "expected_outcome_sha256": hashlib.sha256(
            _canonical(manifest["expected_outcomes"]).encode()).hexdigest(),
        "manifest_sha256": _sha256_file(manifest_path),
    }
    index = {"baselines": []}
    if os.path.exists(index_path):
        index = json.load(open(index_path))
    index["baselines"] = [b for b in index["baselines"]
                          if b["baseline_id"] != baseline_id] + [entry]
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2, sort_keys=True)
        f.write("\n")
    return entry


def diff(results_file, baseline_id, baselines_dir=BASELINES_DIR, index_path=None):
    """Byte-deterministic comparison on the deterministic tier: same cases,
    same expected outcomes, diff of observed deterministic scores.
    The committed baseline INDEX is authoritative (F-001/L-17): the on-disk
    manifest must hash to the indexed value and its case-set/expected-outcome
    hashes must match before any comparison runs."""
    manifest_path = os.path.join(baselines_dir, baseline_id, "manifest.json")
    if not os.path.exists(manifest_path):
        raise HarnessError(f"no baseline manifest: {manifest_path}")
    index_file = index_path or os.path.join(
        os.path.dirname(baselines_dir.rstrip("/")), "baseline-index.json")
    entry = None
    if os.path.exists(index_file):
        entry = next((b for b in json.load(open(index_file))["baselines"]
                      if b["baseline_id"] == baseline_id), None)
    if entry is None:
        raise HarnessError(f"baseline {baseline_id} is not in the committed index "
                           f"{index_file} — refusing to diff against an unindexed baseline")
    actual = _sha256_file(manifest_path)
    if actual != entry["manifest_sha256"]:
        raise HarnessError(f"baseline manifest drifted from the committed index: "
                           f"{actual[:16]}… != index {entry['manifest_sha256'][:16]}…")
    baseline = json.load(open(manifest_path))
    for key, field in (("case_set", "case_set_sha256"),
                       ("expected_outcomes", "expected_outcome_sha256")):
        h = hashlib.sha256(_canonical(baseline[key]).encode()).hexdigest()
        if h != entry[field]:
            raise HarnessError(f"baseline {key} does not match the committed index")
    _, records = _read_results(results_file)
    current = {r["case_id"]: r["deterministic"] for r in records}
    current_cases = sorted(current)
    report = {"baseline_id": baseline_id, "match": True, "differences": []}
    if current_cases != baseline["case_set"]:
        report["match"] = False
        report["differences"].append(
            f"case set differs: missing={sorted(set(baseline['case_set']) - set(current_cases))} "
            f"added={sorted(set(current_cases) - set(baseline['case_set']))}")
    for cid in sorted(set(current) & set(baseline["deterministic"])):
        if current[cid] != baseline["deterministic"][cid]:
            report["match"] = False
            report["differences"].append(
                f"{cid}: baseline={baseline['deterministic'][cid]} "
                f"current={current[cid]}")
    return report


def main():
    args = sys.argv[1:]
    if not args:
        raise HarnessError(__doc__)
    try:
        if args[0] == "run":
            summary = run(authorized_model="--authorized-model" in args)
            print(json.dumps(summary, indent=2))
            sys.exit(1 if summary["red"] else 0)
        elif args[0] == "freeze":
            print(json.dumps(freeze(args[1], args[2]), indent=2))
        elif args[0] == "diff":
            report = diff(args[1], args[2])
            print(json.dumps(report, indent=2))
            sys.exit(0 if report["match"] else 1)
        else:
            raise HarnessError(f"unknown command: {args[0]}")
    except (HarnessError, corpus_mod.CorpusError) as e:
        print(f"EVAL HARNESS ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
