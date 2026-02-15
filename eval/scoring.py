"""Auto-scoring from CompletionTrace. No LLM-as-judge."""

import re
from dataclasses import dataclass, field

from eval.backends import CompletionTrace
from eval.cases import TestCase


@dataclass
class TestResult:
    case_id: str
    category: str
    score: float
    passed: bool
    latency_ms: float
    reasons: list[str] = field(default_factory=list)
    error: str | None = None


def _all_tool_calls(trace: CompletionTrace) -> list:
    """Flatten all tool calls across turns."""
    calls = []
    for turn in trace.turns:
        calls.extend(turn.tool_calls)
    return calls


def _tool_names(trace: CompletionTrace) -> list[str]:
    """Get ordered list of tool names called."""
    return [tc.name for tc in _all_tool_calls(trace)]


def _is_iso8601(s: str) -> bool:
    """Check if a string looks like ISO 8601 datetime."""
    return bool(re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", s))


def _has_timezone_offset(s: str) -> bool:
    """Check if an ISO 8601 string has a timezone offset."""
    return bool(re.search(r"[+-]\d{2}:\d{2}$", s)) or s.endswith("Z")


def score_case(case: TestCase, trace: CompletionTrace) -> TestResult:
    """Score a single test case from its trace. Returns TestResult with score 0.0-1.0."""
    reasons = []
    checks = []

    if trace.error:
        return TestResult(
            case_id=case.id,
            category=case.category,
            score=0.0,
            passed=False,
            latency_ms=trace.latency_ms,
            reasons=[f"Error: {trace.error}"],
            error=trace.error,
        )

    called_names = _tool_names(trace)
    all_calls = _all_tool_calls(trace)

    # --- Check 1: Correct tools called ---
    if case.expected_tools:
        expected_set = set(case.expected_tools)
        called_set = set(called_names)
        if expected_set <= called_set:
            checks.append(1.0)
        else:
            missing = expected_set - called_set
            reasons.append(f"Missing tools: {missing}")
            # Partial credit: fraction of expected tools that were called
            if expected_set:
                checks.append(len(expected_set & called_set) / len(expected_set))
            else:
                checks.append(0.0)
    elif case.expected_tools == []:
        # Should NOT call any tools
        if not called_names:
            checks.append(1.0)
        else:
            reasons.append(f"Called tools when none expected: {called_names}")
            checks.append(0.0)

    # --- Check 2: Required args present ---
    if case.required_args:
        arg_scores = []
        for tool_name, required in case.required_args.items():
            matching_calls = [tc for tc in all_calls if tc.name == tool_name]
            if not matching_calls:
                reasons.append(f"No call to {tool_name} to check args")
                arg_scores.append(0.0)
                continue
            # Check the last call to this tool (in case it was called multiple times)
            tc = matching_calls[-1]
            present = [arg for arg in required if arg in tc.args]
            missing = [arg for arg in required if arg not in tc.args]
            if missing:
                reasons.append(f"{tool_name} missing args: {missing}")
            arg_scores.append(len(present) / len(required) if required else 1.0)
        if arg_scores:
            checks.append(sum(arg_scores) / len(arg_scores))

    # --- Check 3: Tool sequence ---
    if case.expected_tool_sequence:
        # Check that the expected tools appear in order (not necessarily contiguous)
        seq = case.expected_tool_sequence
        seq_idx = 0
        for name in called_names:
            if seq_idx < len(seq) and name == seq[seq_idx]:
                seq_idx += 1
        if seq_idx == len(seq):
            checks.append(1.0)
        else:
            reasons.append(f"Wrong tool sequence: expected {seq}, got {called_names}")
            checks.append(seq_idx / len(seq))

    # --- Check 4: ISO date format ---
    if case.check_iso_dates:
        date_args_ok = True
        for tc in all_calls:
            for key in ("start", "end"):
                if key in tc.args:
                    if not _is_iso8601(tc.args[key]):
                        reasons.append(f"{tc.name}.{key} not ISO 8601: '{tc.args[key]}'")
                        date_args_ok = False
        checks.append(1.0 if date_args_ok else 0.0)

    # --- Check 5: Timezone offset ---
    if case.check_timezone_offset:
        tz_ok = True
        for tc in all_calls:
            for key in ("start", "end"):
                if key in tc.args:
                    if not _has_timezone_offset(tc.args[key]):
                        reasons.append(f"{tc.name}.{key} missing timezone offset: '{tc.args[key]}'")
                        tz_ok = False
        checks.append(1.0 if tz_ok else 0.0)

    # --- Check 6: Expected content in response ---
    if case.expected_content:
        final_lower = trace.final_text.lower()
        found = [kw for kw in case.expected_content if kw.lower() in final_lower]
        missing = [kw for kw in case.expected_content if kw.lower() not in final_lower]
        if missing:
            reasons.append(f"Missing in response: {missing}")
        checks.append(len(found) / len(case.expected_content))

    # --- Check 7: Conciseness (word count) ---
    if case.max_words is not None:
        word_count = len(trace.final_text.split())
        if word_count <= case.max_words:
            checks.append(1.0)
        else:
            reasons.append(f"Too verbose: {word_count} words (max {case.max_words})")
            # Graceful degradation — slight overshoot still gets partial credit
            overshoot = word_count / case.max_words
            checks.append(max(0.0, 1.0 - (overshoot - 1.0)))

    # --- Aggregate ---
    if not checks:
        # No criteria to check — pass by default (e.g. "say hello")
        score = 1.0
    else:
        score = sum(checks) / len(checks)

    return TestResult(
        case_id=case.id,
        category=case.category,
        score=round(score, 3),
        passed=score >= 0.8,
        latency_ms=trace.latency_ms,
        reasons=reasons,
    )
