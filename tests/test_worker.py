import types
import pytest
from pipeline import worker


def _r(rc, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)


def test_isolation_toml_fail_closed_and_clarity_scoped():
    # The isolation config is the worker's evidence of its own posture:
    # empty fallback chain (fail closed) and the owner-approved, narrowly
    # scoped clarity_gate opt-out for single-shot contract-gated invocations.
    assert "fallback_models = []" in worker.ISOLATION_TOML
    assert "clarity_gate = false" in worker.ISOLATION_TOML


def test_clarity_stop_classified_with_rc_stderr_and_prompt_hash():
    # Owner condition 2026-10-04: a pxx CLARIFICATION_REQUIRED stop is a
    # pxx-side tooling stop — original exit code, complete stderr, and
    # prompt identity preserved; never a pass, never a silent retry.
    r = _r(2,
           stdout="[CLARIFICATION_REQUIRED] The task references 'ops.py', "
                  "which does not exist under /repo. Which file did you mean? "
                  "(rounds=0 tokens=0 diff_lines=0)\n",
           stderr="line1\nline2\nline3-trailing")
    err = worker.classify_pxx_failure("the prompt", r, "t.log")
    assert isinstance(err, worker.ClarityGateStop)
    assert isinstance(err, worker.WorkerError)  # still a failure, never a pass
    msg = str(err)
    assert "rc=2" in msg
    assert worker.prompt_hash("the prompt")[:16] in msg
    assert "ops.py" in msg and "Which file did you mean?" in msg
    assert "line3-trailing" in msg  # complete stderr, not a tail
    assert "(rounds=" not in msg.split("stderr")[0]  # status trailer stripped


def test_generic_pxx_failure_is_not_a_clarity_stop():
    r = _r(1, stdout="boom", stderr="x" * 5000)
    err = worker.classify_pxx_failure("p", r, "t.log")
    assert type(err) is worker.WorkerError
    assert "rc=1" in str(err)


def test_write_transcript_records_command_config_hash_and_full_io(tmp_path):
    r = _r(0, stdout="out", stderr="err")
    p = tmp_path / "t.log"
    worker.write_transcript(str(p), ["pxx", "ask", "-m", "hi"], "hi", r)
    text = p.read_text()
    assert text.startswith("$ pxx ask -m hi\n[rc=0]\n")
    assert f"[prompt_sha256={worker.prompt_hash('hi')}]" in text
    assert worker.ISOLATION_TOML in text  # exact config in force, as evidence
    assert text.endswith("--- stdout ---\nout\n--- stderr ---\nerr")
