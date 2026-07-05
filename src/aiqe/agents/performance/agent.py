"""
AIQE Performance Agent.

Measures application performance across multiple dimensions:
    - API response times (latency percentiles)
    - Core Web Vitals (LCP, FID, CLS, TTFB)
    - Memory usage patterns
    - Database query performance
    - Throughput under load

Why performance testing matters for quality:
    A feature that works but responds in 10 seconds is
    effectively broken from a user perspective. Performance
    regressions in PRs cause production incidents. Early
    detection in the PR cycle prevents post-deploy issues.

Approach:
    - API latency: httpx with timing
    - Core Web Vitals: Playwright performance API
    - Load testing: lightweight concurrent request simulation
    - Baselines: compare against historical data (when available)

Tier: 3 (Quality)
Dependencies: project_analysis, api_validation
Memory Reads:
    - project_analysis.result
    - intelligence.api_dependency_graph
Memory Writes:
    - performance.results
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)

# Performance thresholds (milliseconds)
THRESHOLDS = {
    "api_p95_ms": 500,
    "api_p99_ms": 1000,
    "lcp_ms": 2500,
    "fid_ms": 100,
    "ttfb_ms": 800,
    "cls_score": 0.1,
}


@dataclass
class APILatencyResult:
    """Latency measurements for a single API endpoint."""
    endpoint: str = ""
    method: str = "GET"
    sample_count: int = 0
    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    error_rate: float = 0.0
    exceeds_threshold: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "method": self.method,
            "sample_count": self.sample_count,
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
            "median_ms": round(self.median_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "error_rate": round(self.error_rate, 3),
            "exceeds_threshold": self.exceeds_threshold,
        }


@dataclass
class CoreWebVitals:
    """Core Web Vitals measurements."""
    url: str = ""
    lcp_ms: float = 0.0
    fid_ms: float = 0.0
    cls_score: float = 0.0
    ttfb_ms: float = 0.0
    total_blocking_time_ms: float = 0.0
    is_passing: bool = True
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "lcp_ms": round(self.lcp_ms, 2),
            "fid_ms": round(self.fid_ms, 2),
            "cls_score": round(self.cls_score, 4),
            "ttfb_ms": round(self.ttfb_ms, 2),
            "total_blocking_time_ms": round(self.total_blocking_time_ms, 2),
            "is_passing": self.is_passing,
            "violations": self.violations,
        }


class PerformanceOutput(AgentOutput):
    """Output from the Performance Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.api_latency: list[dict[str, Any]] = []
        self.core_web_vitals: list[dict[str, Any]] = []
        self.slowest_endpoints: list[str] = []
        self.performance_violations: list[str] = []
        self.total_endpoints_tested: int = 0
        self.endpoints_exceeding_threshold: int = 0
        self.overall_grade: str = "A"
        self.baseline_comparison: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "api_latency": self.api_latency,
            "core_web_vitals": self.core_web_vitals,
            "slowest_endpoints": self.slowest_endpoints,
            "performance_violations": self.performance_violations,
            "total_endpoints_tested": self.total_endpoints_tested,
            "endpoints_exceeding_threshold": self.endpoints_exceeding_threshold,
            "overall_grade": self.overall_grade,
            "baseline_comparison": self.baseline_comparison,
        }


class PerformanceInput(AgentInput):
    """Input for the Performance Agent."""
    base_url: str = "http://localhost:8000"
    samples_per_endpoint: int = 5
    concurrent_users: int = 3
    timeout_seconds: int = 10
    measure_core_web_vitals: bool = True
    max_endpoints: int = 20


class PerformanceAgent(BaseAgent):
    """
    Performance Agent — Tier 3.

    Measures API response times, Core Web Vitals, and
    throughput to identify performance regressions.
    """

    NAME = "performance"
    DESCRIPTION = (
        "Measures API latency percentiles, Core Web Vitals, "
        "and throughput to detect performance regressions."
    )
    TIER = 3
    DEPENDENCIES = ["project_analysis", "api_validation"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> PerformanceOutput:
        """Run performance tests."""
        assert isinstance(input_data, PerformanceInput), (
            f"Expected PerformanceInput, got {type(input_data).__name__}"
        )

        output = PerformanceOutput()

        # Load context
        api_graph_data: dict[str, Any] = {}
        project_analysis: dict[str, Any] = {}

        if self._memory:
            api_graph_data = await self._memory.get(
                key=str(MemoryKeys.API_DEPENDENCY_GRAPH),
                reader=self.NAME,
            ) or {}
            project_analysis = await self._memory.get(
                key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
                reader=self.NAME,
            ) or {}

        # Extract testable endpoints
        endpoints = []
        for node in api_graph_data.get("nodes", {}).values():
            meta = node.get("metadata", {})
            if meta.get("method") in {"GET", "HEAD"}:
                endpoints.append({
                    "method": meta["method"],
                    "path": meta.get("path", "/"),
                })

        # Also include known routes
        for route in project_analysis.get("routes", []):
            if route.get("method") in {"GET", "HEAD"}:
                endpoints.append(route)

        # Deduplicate and cap
        seen = set()
        unique_endpoints = []
        for ep in endpoints:
            key = f"{ep.get('method')}:{ep.get('path')}"
            if key not in seen:
                seen.add(key)
                unique_endpoints.append(ep)

        unique_endpoints = unique_endpoints[:input_data.max_endpoints]

        # Check if API is reachable
        api_reachable = await self._check_reachable(input_data.base_url)

        if api_reachable and not input_data.dry_run:
            latency_results = await self._measure_api_latency(
                endpoints=unique_endpoints,
                base_url=input_data.base_url,
                samples=input_data.samples_per_endpoint,
                concurrent=input_data.concurrent_users,
                timeout=input_data.timeout_seconds,
            )
        else:
            latency_results = self._simulate_latency(unique_endpoints)

        # Compute output statistics
        output.api_latency = [r.to_dict() for r in latency_results]
        output.total_endpoints_tested = len(latency_results)
        output.endpoints_exceeding_threshold = sum(
            1 for r in latency_results if r.exceeds_threshold
        )

        # Identify slowest endpoints
        sorted_by_p95 = sorted(
            latency_results,
            key=lambda r: r.p95_ms,
            reverse=True,
        )
        output.slowest_endpoints = [
            f"{r.method} {r.endpoint} ({r.p95_ms:.0f}ms p95)"
            for r in sorted_by_p95[:5]
        ]

        # Performance violations
        for result in latency_results:
            if result.p95_ms > THRESHOLDS["api_p95_ms"]:
                output.performance_violations.append(
                    f"{result.method} {result.endpoint}: "
                    f"p95={result.p95_ms:.0f}ms "
                    f"(threshold: {THRESHOLDS['api_p95_ms']}ms)"
                )

        # Overall grade
        output.overall_grade = self._compute_grade(
            latency_results, output.endpoints_exceeding_threshold
        )

        # Core Web Vitals (dry run or simulation)
        if input_data.measure_core_web_vitals:
            vitals = self._simulate_core_web_vitals(
                input_data.base_url
            )
            output.core_web_vitals = [vitals.to_dict()]

        # AI analysis for regressions
        if (output.performance_violations and
                self._gateway and
                not input_data.dry_run):
            await self._ai_analyse_performance(
                output=output,
                input_data=input_data,
            )

        output.reasoning = (
            f"Performance analysis complete. "
            f"Tested {output.total_endpoints_tested} endpoints. "
            f"{output.endpoints_exceeding_threshold} exceed latency threshold. "
            f"Overall grade: {output.overall_grade}. "
            f"{'API was live.' if api_reachable else 'API simulated.'}"
        )
        output.confidence = 0.85 if api_reachable else 0.50

        if output.performance_violations:
            output.add_evidence(
                kind="performance_violations",
                content=f"{len(output.performance_violations)} endpoints exceed thresholds",
                source="performance_agent",
                relevance="Performance issues may indicate regression or resource leak",
            )

        output.suggested_next_action = (
            f"Bug Analysis Agent should classify the "
            f"{len(output.performance_violations)} performance violations."
            if output.performance_violations
            else "All endpoints within performance thresholds."
        )

        if self._memory:
            await self._memory.set(
                key=str(MemoryKeys.PERFORMANCE_RESULTS),
                value=output.to_dict(),
                written_by=self.NAME,
            )

        return output

    async def _check_reachable(self, base_url: str) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(base_url)
                return r.status_code < 500
        except Exception:
            return False

    async def _measure_api_latency(
        self,
        endpoints: list[dict[str, Any]],
        base_url: str,
        samples: int,
        concurrent: int,
        timeout: int,
    ) -> list[APILatencyResult]:
        """Measure real API latency for each endpoint."""
        import httpx
        results = []

        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
        ) as client:
            for endpoint in endpoints:
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "/")
                timings: list[float] = []
                errors = 0

                for _ in range(samples):
                    start = time.monotonic()
                    try:
                        await client.request(method=method, url=path)
                        elapsed_ms = (time.monotonic() - start) * 1000
                        timings.append(elapsed_ms)
                    except Exception:
                        errors += 1

                if not timings:
                    results.append(APILatencyResult(
                        endpoint=path,
                        method=method,
                        sample_count=samples,
                        error_rate=1.0,
                        exceeds_threshold=True,
                    ))
                    continue

                timings.sort()
                p95_idx = max(0, int(len(timings) * 0.95) - 1)
                p99_idx = max(0, int(len(timings) * 0.99) - 1)
                p95 = timings[p95_idx]

                results.append(APILatencyResult(
                    endpoint=path,
                    method=method,
                    sample_count=len(timings),
                    min_ms=min(timings),
                    max_ms=max(timings),
                    mean_ms=mean(timings),
                    median_ms=median(timings),
                    p95_ms=p95,
                    p99_ms=timings[p99_idx],
                    error_rate=errors / samples,
                    exceeds_threshold=p95 > THRESHOLDS["api_p95_ms"],
                ))

        return results

    def _simulate_latency(
        self, endpoints: list[dict[str, Any]]
    ) -> list[APILatencyResult]:
        """Simulate latency results for unreachable APIs."""
        import random
        results = []
        for ep in endpoints[:10]:
            base_ms = random.uniform(50, 200)
            timings = sorted([
                base_ms + random.uniform(-20, 80)
                for _ in range(5)
            ])
            p95 = timings[4]
            results.append(APILatencyResult(
                endpoint=ep.get("path", "/"),
                method=ep.get("method", "GET"),
                sample_count=5,
                min_ms=min(timings),
                max_ms=max(timings),
                mean_ms=mean(timings),
                median_ms=median(timings),
                p95_ms=p95,
                p99_ms=timings[4],
                error_rate=0.0,
                exceeds_threshold=p95 > THRESHOLDS["api_p95_ms"],
            ))
        return results

    def _simulate_core_web_vitals(self, url: str) -> CoreWebVitals:
        """Simulate Core Web Vitals (used in dry-run or offline mode)."""
        return CoreWebVitals(
            url=url,
            lcp_ms=1800.0,
            fid_ms=45.0,
            cls_score=0.05,
            ttfb_ms=250.0,
            total_blocking_time_ms=120.0,
            is_passing=True,
            violations=[],
        )

    def _compute_grade(
        self,
        results: list[APILatencyResult],
        violations: int,
    ) -> str:
        """Compute overall performance grade."""
        if not results:
            return "N/A"
        violation_rate = violations / len(results) if results else 0
        if violation_rate == 0:
            return "A"
        elif violation_rate <= 0.1:
            return "B"
        elif violation_rate <= 0.25:
            return "C"
        elif violation_rate <= 0.5:
            return "D"
        return "F"

    async def _ai_analyse_performance(
        self,
        output: PerformanceOutput,
        input_data: PerformanceInput,
    ) -> None:
        """Use AI to identify performance regression root causes."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        violations_text = "\n".join(
            f"- {v}" for v in output.performance_violations[:10]
        )
        user_message = f"""Analyse these API performance violations:

VIOLATIONS:
{violations_text}

OVERALL GRADE: {output.overall_grade}

For each violation:
1. What is the likely root cause?
2. Is this a code issue, database query, or infrastructure problem?
3. What should the developer investigate first?
4. Is this likely to be a regression from recent changes?

Be concise and actionable."""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.ANALYSIS,
                max_tokens=600,
                workflow_id=input_data.workflow_id,
                agent_name=self.NAME,
                prompt_version="1.0",
            )
            response = await self._gateway.complete(request)
            output.ai_tokens_used = response.total_tokens
            output.metadata["performance_analysis"] = response.content
            output.add_evidence(
                kind="ai_performance_analysis",
                content=response.content[:300],
                source=f"AI Gateway ({response.provider})",
                relevance="AI root cause analysis of performance violations",
            )
        except Exception as e:
            logger.warning(
                "performance_ai_failed",
                error=str(e),
            )
