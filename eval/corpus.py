"""Eval corpus registry — loader + the owner-recorded semantic contract.

The schema (contracts/eval_case.schema.json) validates STRUCTURE; this module
enforces SEMANTICS (docs/eval-corpus-design.md §1, §9 dispositions):

- F-002 outcome<->catching_layer, no null ambiguity: pass="none",
  human_escalation="human"; fail and limitation require a named layer.
- F-003 outcome mapping: refusal is behavior, not an outcome; a classified
  pxx ClarityGateStop is exactly outcome=limitation, catching_layer=gate,
  detail="pxx clarity gate stopped the request before execution".
- execution pairing: requires_model=false <-> layer="harness" (net-* network
  cases can never be misread as model-evaluation evidence);
  requires_model=true <-> layer="worker".
- requires_model=false cases must name a known executor (the harness must be
  able to run every deterministic case).
- provenance.fixture_sha256 must equal the sha256 of the committed payload
  file — a cited fixture must EXIST and match, never a dangling reference.
- case_id prefix <-> class consistency; holdout=true <-> class="holdout".

Any violation is a loud CorpusError; the corpus never loads partially.
"""
import hashlib, json, os

from pipeline.validate import load as _load, validate as _validate, ValidationError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(REPO_ROOT, "contracts", "eval_case.schema.json")
CORPUS = os.path.join(REPO_ROOT, "eval", "corpus.jsonl")

CLARITY_DETAIL = "pxx clarity gate stopped the request before execution"

PREFIX_CLASS = {
    "inj": "prompt_injection", "mal": "malformed_output", "scope": "scope_write",
    "net": "endpoint", "reg": "regression", "hold": "holdout",
}
NAMED_LAYERS = {"schema", "gate", "ast", "scope", "runtime", "envelope"}
EXECUTORS = {"extract_json", "contract_check", "verbatim_trace",
             "ast_imports", "endpoint_down", "scope_diff"}


class CorpusError(Exception):
    """Corpus record failed schema or semantic validation. Loud; never skipped."""


def _err(case_id, msg):
    raise CorpusError(f"{case_id}: {msg}")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_case(rec, repo_root=REPO_ROOT):
    """Validate one case record: schema first, then the semantic contract.
    Returns the record unchanged; raises CorpusError on any violation."""
    cid = rec.get("case_id", "<no case_id>")
    try:
        _validate(_load(SCHEMA), rec)
    except ValidationError as e:
        _err(cid, f"schema violation: {e}")

    prefix = rec["case_id"].split("-")[0]
    if PREFIX_CLASS[prefix] != rec["class"]:
        _err(cid, f"case_id prefix '{prefix}' implies class "
                  f"'{PREFIX_CLASS[prefix]}', got '{rec['class']}'")
    if rec["holdout"] != (rec["class"] == "holdout"):
        _err(cid, "holdout flag must be true exactly when class == 'holdout'")

    # F-002: outcome <-> catching_layer, exactly one deterministic representation
    outcome, layer = rec["expected"]["outcome"], rec["expected"]["catching_layer"]
    if outcome == "pass" and layer != "none":
        _err(cid, "F-002: outcome pass requires catching_layer 'none' — "
                  "a pass must not pretend a gate caught anything")
    if outcome == "human_escalation" and layer != "human":
        _err(cid, "F-002: human_escalation requires catching_layer 'human'")
    if outcome in ("fail", "limitation") and layer not in NAMED_LAYERS:
        _err(cid, f"F-002: outcome {outcome} requires a named catching_layer "
                  f"({sorted(NAMED_LAYERS)}), got '{layer}'")

    # F-003: a ClarityGateStop case has exactly one valid representation
    detail = rec["expected"]["detail"]
    if "clarity" in rec["case_id"] or "clarity gate" in detail.lower():
        if (outcome, layer, detail) != ("limitation", "gate", CLARITY_DETAIL):
            _err(cid, "F-003: a ClarityGateStop case must be outcome=limitation, "
                      f"catching_layer=gate, detail={CLARITY_DETAIL!r}")

    # execution pairing: network/harness cases are never model evidence
    req_model, ex_layer = rec["execution"]["requires_model"], rec["execution"]["layer"]
    if req_model and ex_layer != "worker":
        _err(cid, "requires_model=true requires execution.layer 'worker'")
    if not req_model and ex_layer != "harness":
        _err(cid, "requires_model=false requires execution.layer 'harness' — "
                  "harness cases can never be misread as model-evaluation evidence")
    if not req_model:
        ex = rec.get("check", {}).get("executor")
        if ex not in EXECUTORS:
            _err(cid, f"deterministic case must name a known executor "
                      f"({sorted(EXECUTORS)}), got {ex!r}")

    # fixture provenance: the cited hash must equal the committed payload's hash
    payload = os.path.join(repo_root, rec["input"]["brief_or_payload"])
    if not os.path.exists(payload):
        _err(cid, f"payload file does not exist: {rec['input']['brief_or_payload']}")
    actual = _sha256_file(payload)
    if actual != rec["provenance"]["fixture_sha256"]:
        _err(cid, f"fixture_sha256 mismatch: record cites "
                  f"{rec['provenance']['fixture_sha256'][:16]}..., payload hashes "
                  f"{actual[:16]}... — fixture changed without updating the record")
    return rec


def load_corpus(path=CORPUS, repo_root=REPO_ROOT):
    """Load and validate the whole corpus. Loud on any invalid record;
    duplicate case_ids rejected. Returns the list of case records."""
    cases, seen = [], set()
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise CorpusError(f"corpus line {ln}: invalid JSON: {e}")
            load_case(rec, repo_root)
            if rec["case_id"] in seen:
                raise CorpusError(f"duplicate case_id: {rec['case_id']}")
            seen.add(rec["case_id"])
            cases.append(rec)
    if not cases:
        raise CorpusError("corpus is empty")
    return cases
