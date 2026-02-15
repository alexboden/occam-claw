"""CLI entry point for the eval suite.

Usage:
    python -m eval.runner                           # all backends, all cases
    python -m eval.runner --backend bedrock         # bedrock only
    python -m eval.runner --backend ollama --ollama-model llama3.1:8b
    python -m eval.runner --category tool_selection # one category
    python -m eval.runner --case ms_01              # one case
    python -m eval.runner --output results.json     # save JSON
"""

import argparse
import json
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path

from eval.backends import BedrockBackend, OllamaBackend, CompletionTrace
from eval.cases import ALL_CASES, CATEGORIES, TestCase
from eval.scoring import score_case, TestResult
from eval.test_image import generate_test_image_base64


def _load_config() -> dict:
    """Load config.toml if it exists, for Bedrock model/region defaults."""
    config_path = Path(__file__).resolve().parent.parent / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    return {}


def _build_backends(args, config: dict) -> list:
    backends = []
    llm_config = config.get("llm", {})

    if args.backend in (None, "bedrock"):
        model = llm_config.get("model", "us.anthropic.claude-sonnet-4-20250514-v1:0")
        region = llm_config.get("aws_region", "us-east-1")
        backends.append(BedrockBackend(model=model, aws_region=region))

    if args.backend in (None, "ollama"):
        model = args.ollama_model or "llama3.1:8b"
        base_url = args.ollama_url or "http://localhost:11434"
        backends.append(OllamaBackend(model=model, base_url=base_url))

    return backends


def _select_cases(args) -> list[TestCase]:
    if args.case:
        matches = [c for c in ALL_CASES if c.id == args.case]
        if not matches:
            print(f"Unknown case: {args.case}", file=sys.stderr)
            sys.exit(1)
        return matches
    if args.category:
        if args.category not in CATEGORIES:
            print(f"Unknown category: {args.category}", file=sys.stderr)
            print(f"Available: {', '.join(CATEGORIES.keys())}", file=sys.stderr)
            sys.exit(1)
        return CATEGORIES[args.category]
    return ALL_CASES


def _prepare_case(case: TestCase, image_b64: str) -> TestCase:
    """Fill in deferred fields like vision image data."""
    if case.image_b64 == "DEFERRED":
        case.image_b64 = image_b64
    return case


def _run_case(backend, case: TestCase) -> TestResult:
    """Run a single case on a backend and return the scored result."""
    trace = backend.run(case.prompt, image_b64=case.image_b64)
    return score_case(case, trace)


def _print_report(results_by_backend: dict[str, list[TestResult]]):
    """Print the comparison table to stdout."""
    backend_names = list(results_by_backend.keys())
    categories = list(CATEGORIES.keys())

    # Header
    col_width = 28
    print()
    header = f"{'Category':<20}"
    for name in backend_names:
        header += f" | {name:<{col_width}}"
    print(header)
    print("-" * len(header))

    # Per-category rows
    totals = {name: {"passed": 0, "total": 0, "latency": []} for name in backend_names}

    for cat in categories:
        row = f"{cat:<20}"
        for name in backend_names:
            cat_results = [r for r in results_by_backend[name] if r.category == cat]
            if not cat_results:
                row += f" | {'--':<{col_width}}"
                continue
            passed = sum(1 for r in cat_results if r.passed)
            total = len(cat_results)
            avg_ms = sum(r.latency_ms for r in cat_results) / total
            pct = int(passed / total * 100)
            cell = f"{passed}/{total} ({pct:>3}%)  avg {avg_ms:>5.0f}ms"
            row += f" | {cell:<{col_width}}"
            totals[name]["passed"] += passed
            totals[name]["total"] += total
            totals[name]["latency"].extend(r.latency_ms for r in cat_results)
        print(row)

    # Total row
    print("-" * len(header))
    row = f"{'TOTAL':<20}"
    for name in backend_names:
        t = totals[name]
        if t["total"]:
            pct = int(t["passed"] / t["total"] * 100)
            avg_ms = sum(t["latency"]) / t["total"]
            cell = f"{t['passed']}/{t['total']} ({pct:>3}%)  avg {avg_ms:>5.0f}ms"
        else:
            cell = "--"
        row += f" | {cell:<{col_width}}"
    print(row)
    print()


def _print_failures(results_by_backend: dict[str, list[TestResult]]):
    """Print detailed failure breakdown."""
    any_failures = False
    for name, results in results_by_backend.items():
        failures = [r for r in results if not r.passed]
        if not failures:
            continue
        if not any_failures:
            print("=" * 60)
            print("FAILURES")
            print("=" * 60)
            any_failures = True
        print(f"\n--- {name} ---")
        for r in failures:
            print(f"  {r.case_id} (score: {r.score:.2f})")
            for reason in r.reasons:
                print(f"    - {reason}")
            if r.error:
                print(f"    ERROR: {r.error}")
    if not any_failures:
        print("All cases passed!")


def _save_json(results_by_backend: dict[str, list[TestResult]], path: str):
    """Export results to JSON."""
    output = {}
    for name, results in results_by_backend.items():
        output[name] = [asdict(r) for r in results]
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results saved to {path}")


def main():
    parser = argparse.ArgumentParser(description="Eval suite: Bedrock vs Local Models")
    parser.add_argument("--backend", choices=["bedrock", "ollama"], help="Run only this backend")
    parser.add_argument("--ollama-model", help="Ollama model name (default: llama3.1:8b)")
    parser.add_argument("--ollama-url", help="Ollama base URL (default: http://localhost:11434)")
    parser.add_argument("--category", help="Run only this category")
    parser.add_argument("--case", help="Run only this case ID")
    parser.add_argument("--output", help="Save results to JSON file")
    args = parser.parse_args()

    config = _load_config()
    backends = _build_backends(args, config)
    cases = _select_cases(args)

    if not backends:
        print("No backends selected.", file=sys.stderr)
        sys.exit(1)

    # Pre-generate the test image once
    image_b64 = generate_test_image_base64()
    cases = [_prepare_case(c, image_b64) for c in cases]

    results_by_backend: dict[str, list[TestResult]] = {}

    for backend in backends:
        label = f"{backend.name} ({backend.model})"
        print(f"Running {len(cases)} cases on {label}...")
        results = []
        for i, case in enumerate(cases, 1):
            sys.stdout.write(f"  [{i}/{len(cases)}] {case.id}... ")
            sys.stdout.flush()
            result = _run_case(backend, case)
            status = "PASS" if result.passed else "FAIL"
            print(f"{status} ({result.latency_ms:.0f}ms)")
            results.append(result)
        results_by_backend[label] = results

    _print_report(results_by_backend)
    _print_failures(results_by_backend)

    if args.output:
        _save_json(results_by_backend, args.output)


if __name__ == "__main__":
    main()
