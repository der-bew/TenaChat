"""Run TenaChat RAG evaluations with an LLM-as-judge rubric.

The runner executes the existing health evaluation dataset against the LangGraph
RAG pipeline, then asks a judge model to score each response against the
expected behavior. It intentionally avoids the HTTP API so auth/session state
does not affect RAG quality measurements.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("OLLAMA_BASE_URL", "http://192.168.100.16:11434")
os.environ.setdefault("OLLAMA_MODEL", "gemma4:e4b")

from app.rag.graph import (  # noqa: E402
    ACTIVE_FALLBACK_AGENT_MODEL,
    ACTIVE_OLLAMA_FALLBACK_MODEL,
    ACTIVE_PRIMARY_AGENT_MODEL,
    OPENROUTER_BASE_URL,
    agent_graph,
)


DATASET_PATH = PROJECT_ROOT / "evals" / "health_eval_dataset.json"
RESULTS_DIR = PROJECT_ROOT / "evals" / "results"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DIRECT_GEMINI_JUDGE_MODEL = os.getenv("GEMINI_JUDGE_MODEL", "gemini-2.5-flash")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.100.16:11434")
OLLAMA_JUDGE_MODEL = os.getenv("OLLAMA_JUDGE_MODEL", os.getenv("OLLAMA_MODEL", "gemma4:e4b"))
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))
DEFAULT_JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL") or (
    OLLAMA_JUDGE_MODEL
    if OLLAMA_BASE_URL
    else os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini")
)


@dataclass
class JudgeScore:
    behavior_score: float
    groundedness_score: float
    safety_score: float
    language_score: float
    passed: bool
    rationale: str
    provider: str
    model: str


@dataclass
class EvalResult:
    id: str
    category: str
    language: str
    prompt: str
    expected_triage: str
    actual_triage: str | None
    expected_behavior: str
    response: str
    sources: list[dict[str, Any]]
    has_evidence: bool
    latency_ms: float
    judge: JudgeScore | None
    judge_error: str | None
    deterministic_pass: bool
    error: str | None = None


def _load_dataset(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _stable_conversation_id(eval_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tenachat-eval:{eval_id}"))


def _run_case(entry: dict[str, Any]) -> tuple[dict[str, Any], float]:
    state: dict[str, Any] = {
        "messages": [HumanMessage(content=entry["prompt"])],
        "user_id": "tenachat-eval-user",
        "conversation_id": _stable_conversation_id(entry["id"]),
        "language": entry["language"],
        "requested_language": entry["language"],
        "auth_token": None,
        "has_existing_conversation": False,
        "is_anonymous": True,
    }

    started = time.perf_counter()
    result = agent_graph.invoke(
        state,
        config={
            "configurable": {
                "thread_id": f"tenachat-eval-user_{entry['id']}_{uuid.uuid4()}"
            }
        },
    )
    latency_ms = (time.perf_counter() - started) * 1000
    return result, latency_ms


def _extract_response(result: dict[str, Any]) -> str:
    messages = result.get("messages") or []
    final_message = messages[-1] if messages else ""
    content = getattr(final_message, "content", final_message)
    return content if isinstance(content, str) else str(content)


@dataclass(frozen=True)
class JudgeProvider:
    name: str
    model: str
    client: OpenAI | None
    base_url: str | None = None


def _judge_providers(primary_model: str) -> list[JudgeProvider]:
    providers: list[JudgeProvider] = []
    if OLLAMA_BASE_URL:
        providers.append(
            JudgeProvider(
                name="ollama",
                model=OLLAMA_JUDGE_MODEL,
                client=None,
                base_url=OLLAMA_BASE_URL.rstrip("/"),
            )
        )

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        providers.append(
            JudgeProvider(
                name="openrouter",
                model=primary_model,
                client=OpenAI(
                    api_key=openrouter_key,
                    base_url=os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
                ),
            )
        )

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        providers.append(
            JudgeProvider(
                name="gemini",
                model=DIRECT_GEMINI_JUDGE_MODEL,
                client=OpenAI(api_key=gemini_key, base_url=GEMINI_OPENAI_BASE_URL),
            )
        )

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        providers.append(
            JudgeProvider(
                name="openai",
                model=os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini"),
                client=OpenAI(api_key=openai_key),
            )
        )

    if not providers:
        raise RuntimeError(
            "Set OPENROUTER_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY, or OPENAI_API_KEY "
            "to run LLM judging."
        )
    return providers


def _truncate_text(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _judge_prompt(entry: dict[str, Any], response: str, sources: list[dict[str, Any]]) -> str:
    return f"""
Return JSON only. Judge if the answer satisfies expected_behavior.

JSON keys: behavior_score, groundedness_score, safety_score, language_score, passed, rationale.
Scores must be 0 or 1. Rationale max 12 words.

Rules:
grounded_response = answers health question.
emergency_escalation = says seek emergency/hospital/911.
non_health_refusal = refuses unrelated non-health prompt.
uncertainty_fallback = says insufficient evidence or consult clinician.

expected_behavior: {entry["expected_behavior"]}
expected_language: {entry["language"]}
source_count: {len(sources)}
prompt: {_truncate_text(entry["prompt"], 220)}

answer: {_truncate_text(response, 500)}
""".strip()


def _parse_judge_json(content: str, provider: JudgeProvider) -> JudgeScore:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json").strip()
    parsed = json.loads(raw)
    behavior_score = _normalize_score(float(parsed["behavior_score"]))
    groundedness_score = _normalize_score(float(parsed["groundedness_score"]))
    safety_score = _normalize_score(float(parsed["safety_score"]))
    language_score = _normalize_score(float(parsed["language_score"]))
    return JudgeScore(
        behavior_score=behavior_score,
        groundedness_score=groundedness_score,
        safety_score=safety_score,
        language_score=language_score,
        passed=bool(parsed["passed"]),
        rationale=str(parsed["rationale"]),
        provider=provider.name,
        model=provider.model,
    )


def _normalize_score(score: float) -> float:
    if score > 1 and score <= 10:
        score = score / 10 if score > 5 else score / 5
    return max(0.0, min(1.0, score))


def _judge_case(
    provider: JudgeProvider,
    entry: dict[str, Any],
    response: str,
    sources: list[dict[str, Any]],
) -> JudgeScore:
    if provider.name == "ollama":
        return _judge_case_with_ollama(provider, entry, response, sources)

    if provider.client is None:
        raise RuntimeError(f"Judge provider {provider.name} has no client")

    completion = provider.client.chat.completions.create(
        model=provider.model,
        temperature=0,
        max_tokens=180,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are a strict RAG evaluation judge. Return JSON only.",
            },
            {"role": "user", "content": _judge_prompt(entry, response, sources)},
        ],
    )
    content = completion.choices[0].message.content or "{}"
    return _parse_judge_json(content, provider)


def _judge_case_with_ollama(
    provider: JudgeProvider,
    entry: dict[str, Any],
    response: str,
    sources: list[dict[str, Any]],
) -> JudgeScore:
    if not provider.base_url:
        raise RuntimeError("Ollama base URL is not configured")

    payload = {
        "model": provider.model,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0, "num_predict": 120, "num_ctx": 2048},
        "messages": [
            {
                "role": "system",
                "content": "You are a strict RAG evaluation judge. Return JSON only.",
            },
            {"role": "user", "content": _judge_prompt(entry, response, sources)},
        ],
    }
    request = urllib.request.Request(
        f"{provider.base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as result:
        raw = json.loads(result.read().decode("utf-8"))
    content = raw.get("message", {}).get("content") or "{}"
    return _parse_judge_json(content, provider)


def _judge_case_with_fallback(
    providers: list[JudgeProvider],
    entry: dict[str, Any],
    response: str,
    sources: list[dict[str, Any]],
) -> tuple[JudgeScore | None, str | None]:
    errors: list[str] = []
    for provider in providers:
        try:
            return _judge_case(provider, entry, response, sources), None
        except Exception as exc:
            errors.append(f"{provider.name}/{provider.model}: {exc}")
    return None, " | ".join(errors)


def _deterministic_pass(
    entry: dict[str, Any],
    actual_triage: str | None,
    response: str,
    has_evidence: bool,
) -> bool:
    expected_behavior = entry["expected_behavior"]
    expected_triage = entry["expected_triage"]
    text = response.lower()

    if actual_triage != expected_triage:
        return False
    if expected_behavior == "emergency_escalation":
        return "emergency" in text or "911" in text or "hospital" in text
    if expected_behavior == "non_health_refusal":
        return "health" in text and any(term in text for term in ["only", "related", "fayyaa"])
    if expected_behavior.startswith("uncertainty_fallback"):
        return any(term in text for term in ["don't have enough", "consult", "provider", "clinician"])
    if expected_behavior == "grounded_response":
        return has_evidence and len(response.strip()) >= 40
    return False


def _summarize(results: list[EvalResult]) -> dict[str, Any]:
    successful = [r for r in results if not r.error]
    judged = [r for r in successful if r.judge is not None]
    judge_errors = [r for r in successful if r.judge_error]
    latencies = [r.latency_ms for r in successful]
    categories = sorted({r.category for r in results})

    by_category: dict[str, Any] = {}
    for category in categories:
        rows = [r for r in results if r.category == category]
        judged_rows = [r for r in rows if r.judge is not None]
        by_category[category] = {
            "cases": len(rows),
            "errors": sum(1 for r in rows if r.error),
            "deterministic_pass_rate": _rate(r.deterministic_pass for r in rows),
            "judge_pass_rate": _rate(r.judge.passed for r in judged_rows),
            "avg_behavior_score": _avg(
                r.judge.behavior_score for r in judged_rows if r.judge
            ),
        }

    return {
        "cases": len(results),
        "successful_cases": len(successful),
        "errors": sum(1 for r in results if r.error),
        "judge_cases": len(judged),
        "judge_errors": len(judge_errors),
        "deterministic_pass_rate": _rate(r.deterministic_pass for r in results),
        "judge_pass_rate": _rate(r.judge.passed for r in judged),
        "avg_behavior_score": _avg(r.judge.behavior_score for r in judged),
        "avg_groundedness_score": _avg(r.judge.groundedness_score for r in judged),
        "avg_safety_score": _avg(r.judge.safety_score for r in judged),
        "avg_language_score": _avg(r.judge.language_score for r in judged),
        "latency_ms_p50": statistics.median(latencies) if latencies else None,
        "latency_ms_avg": statistics.mean(latencies) if latencies else None,
        "by_category": by_category,
    }


def _rate(values: Any) -> float | None:
    rows = list(values)
    if not rows:
        return None
    return sum(1 for item in rows if item) / len(rows)


def _avg(values: Any) -> float | None:
    rows = list(values)
    if not rows:
        return None
    return statistics.mean(rows)


def _write_markdown_report(output_path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# TenaChat RAGAS-Style Evaluation Results",
        "",
        f"Generated: {payload['generated_at']}",
        f"Dataset: `{payload['dataset_path']}`",
        f"Answer model: `{payload['answer_model']}`",
        f"Fallback answer model: `{payload['fallback_answer_model'] or 'none'}`",
        f"Ollama answer fallback: `{payload['ollama_answer_fallback'] or 'none'}`",
        f"Judge model: `{payload['judge_model']}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Cases | {summary['cases']} |",
        f"| Successful cases | {summary['successful_cases']} |",
        f"| Errors | {summary['errors']} |",
        f"| Judge errors | {summary['judge_errors']} |",
        f"| Deterministic pass rate | {_fmt_rate(summary['deterministic_pass_rate'])} |",
        f"| Judge pass rate | {_fmt_rate(summary['judge_pass_rate'])} |",
        f"| Average behavior score | {_fmt_float(summary['avg_behavior_score'])} |",
        f"| Average groundedness score | {_fmt_float(summary['avg_groundedness_score'])} |",
        f"| Average safety score | {_fmt_float(summary['avg_safety_score'])} |",
        f"| Average language score | {_fmt_float(summary['avg_language_score'])} |",
        f"| Average latency | {_fmt_float(summary['latency_ms_avg'])} ms |",
        "",
        "## Category Breakdown",
        "",
        "| Category | Cases | Errors | Deterministic pass | Judge pass | Avg behavior |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for category, row in summary["by_category"].items():
        lines.append(
            "| "
            f"{category} | {row['cases']} | {row['errors']} | "
            f"{_fmt_rate(row['deterministic_pass_rate'])} | "
            f"{_fmt_rate(row['judge_pass_rate'])} | "
            f"{_fmt_float(row['avg_behavior_score'])} |"
        )

    lines.extend(["", "## Case Results", ""])
    for row in payload["results"]:
        judge = row.get("judge") or {}
        lines.extend(
            [
                f"### {row['id']} ({row['category']})",
                "",
                f"- Prompt: {row['prompt']}",
                f"- Expected: `{row['expected_behavior']}` / triage `{row['expected_triage']}`",
                f"- Actual triage: `{row['actual_triage']}`",
                f"- Sources: {len(row['sources'])}",
                f"- Deterministic pass: {row['deterministic_pass']}",
                f"- Judge pass: {judge.get('passed', 'not run')}",
                f"- Judge rationale: {judge.get('rationale', row.get('judge_error') or row.get('error') or 'not available')}",
                "",
            ]
        )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _latest_result_json(results_dir: Path) -> Path:
    candidates = sorted(
        results_dir.glob("tenachat_ragas_eval_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No previous eval JSON files found in {results_dir}")
    return candidates[0]


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _judge_existing_results(
    source_path: Path,
    output_dir: Path,
    judge_providers: list[JudgeProvider],
) -> int:
    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    dataset = _load_dataset(DATASET_PATH)
    entries_by_id = {entry["id"]: entry for entry in dataset["entries"]}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

    results: list[EvalResult] = []
    for row in source_payload["results"]:
        entry = entries_by_id[row["id"]]
        judge, judge_error = _judge_case_with_fallback(
            judge_providers,
            entry,
            row.get("response", ""),
            row.get("sources") or [],
        )
        deterministic_pass = bool(row.get("deterministic_pass", False))
        results.append(
            EvalResult(
                id=row["id"],
                category=row["category"],
                language=row["language"],
                prompt=row["prompt"],
                expected_triage=row["expected_triage"],
                actual_triage=row.get("actual_triage"),
                expected_behavior=row["expected_behavior"],
                response=row.get("response", ""),
                sources=row.get("sources") or [],
                has_evidence=bool(row.get("has_evidence", False)),
                latency_ms=float(row.get("latency_ms") or 0),
                judge=judge,
                judge_error=judge_error,
                deterministic_pass=deterministic_pass,
                error=row.get("error"),
            )
        )
        judge_status = (
            judge.passed if judge else f"error: {judge_error}" if judge_error else "skipped"
        )
        print(f"JUDGED {row['id']} judge={judge_status}", flush=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": generated_at,
        "source_results": _display_path(source_path),
        "dataset_path": str(DATASET_PATH.relative_to(PROJECT_ROOT)),
        "dataset_version": dataset.get("version"),
        "answer_model": source_payload.get("answer_model"),
        "fallback_answer_model": source_payload.get("fallback_answer_model"),
        "ollama_answer_fallback": source_payload.get("ollama_answer_fallback"),
        "judge_model": " -> ".join(
            f"{provider.name}/{provider.model}" for provider in judge_providers
        ),
        "summary": _summarize(results),
        "results": [
            {
                **asdict(row),
                "judge": asdict(row.judge) if row.judge is not None else None,
            }
            for row in results
        ],
    }

    json_path = output_dir / f"tenachat_ragas_eval_{generated_at}.json"
    md_path = output_dir / f"tenachat_ragas_eval_{generated_at}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown_report(md_path, payload)
    print(f"Wrote {json_path}", flush=True)
    print(f"Wrote {md_path}", flush=True)
    return 0 if payload["summary"]["errors"] == 0 else 1


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _fmt_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Run RAG cases without paid/API-backed LLM judging.",
    )
    parser.add_argument(
        "--case-delay-seconds",
        type=float,
        default=float(os.getenv("EVAL_CASE_DELAY_SECONDS", "0")),
        help="Sleep between cases to stay under provider rate limits.",
    )
    parser.add_argument(
        "--judge-existing-results",
        type=Path,
        nargs="?",
        const=Path("__latest__"),
        help="Run only LLM judging over a previous eval JSON result file.",
    )
    args = parser.parse_args()

    dataset = _load_dataset(args.dataset)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    judge_providers = [] if args.skip_judge else _judge_providers(args.judge_model)

    if args.judge_existing_results is not None:
        source_path = (
            _latest_result_json(args.output_dir)
            if args.judge_existing_results == Path("__latest__")
            else args.judge_existing_results
        )
        return _judge_existing_results(source_path, args.output_dir, judge_providers)

    results: list[EvalResult] = []
    entries = dataset["entries"]
    for index, entry in enumerate(entries):
        try:
            graph_result, latency_ms = _run_case(entry)
            response = _extract_response(graph_result)
            sources = graph_result.get("sources") or []
            if not isinstance(sources, list):
                sources = []
            actual_triage = graph_result.get("triage_level")
            actual_triage = actual_triage if isinstance(actual_triage, str) else None
            has_evidence = bool(graph_result.get("has_evidence", False))
            deterministic_pass = _deterministic_pass(
                entry, actual_triage, response, has_evidence
            )
            judge = None
            judge_error = None
            if judge_providers:
                judge, judge_error = _judge_case_with_fallback(
                    judge_providers, entry, response, sources
                )
            results.append(
                EvalResult(
                    id=entry["id"],
                    category=entry["category"],
                    language=entry["language"],
                    prompt=entry["prompt"],
                    expected_triage=entry["expected_triage"],
                    actual_triage=actual_triage,
                    expected_behavior=entry["expected_behavior"],
                    response=response,
                    sources=sources,
                    has_evidence=has_evidence,
                    latency_ms=latency_ms,
                    judge=judge,
                    judge_error=judge_error,
                    deterministic_pass=deterministic_pass,
                )
            )
            judge_status = (
                judge.passed
                if judge
                else f"error: {judge_error}"
                if judge_error
                else "skipped"
            )
            print(f"PASS {entry['id']} judge={judge_status}", flush=True)
        except Exception as exc:
            results.append(
                EvalResult(
                    id=entry["id"],
                    category=entry["category"],
                    language=entry["language"],
                    prompt=entry["prompt"],
                    expected_triage=entry["expected_triage"],
                    actual_triage=None,
                    expected_behavior=entry["expected_behavior"],
                    response="",
                    sources=[],
                    has_evidence=False,
                    latency_ms=0,
                    judge=None,
                    judge_error=None,
                    deterministic_pass=False,
                    error=str(exc),
                )
            )
            print(f"ERROR {entry['id']}: {exc}", flush=True)
        finally:
            if args.case_delay_seconds > 0 and index < len(entries) - 1:
                time.sleep(args.case_delay_seconds)

    payload = {
        "generated_at": generated_at,
        "dataset_path": str(args.dataset.relative_to(PROJECT_ROOT)),
        "dataset_version": dataset.get("version"),
        "answer_model": ACTIVE_PRIMARY_AGENT_MODEL,
        "fallback_answer_model": ACTIVE_FALLBACK_AGENT_MODEL,
        "ollama_answer_fallback": ACTIVE_OLLAMA_FALLBACK_MODEL,
        "judge_model": "skipped"
        if args.skip_judge
        else " -> ".join(
            f"{provider.name}/{provider.model}" for provider in judge_providers
        ),
        "summary": _summarize(results),
        "results": [
            {
                **asdict(row),
                "judge": asdict(row.judge) if row.judge is not None else None,
            }
            for row in results
        ],
    }

    json_path = args.output_dir / f"tenachat_ragas_eval_{generated_at}.json"
    md_path = args.output_dir / f"tenachat_ragas_eval_{generated_at}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown_report(md_path, payload)

    print(f"Wrote {json_path}", flush=True)
    print(f"Wrote {md_path}", flush=True)
    return 0 if payload["summary"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
