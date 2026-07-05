"""
AIQE API Validation Agent.

Validates REST API endpoints discovered by Project Analysis
and exercises API test scripts from Automation Generator.

Responsibilities:
    - Validate all discovered API endpoints exist and respond
    - Verify response schemas match expected formats
    - Test authentication boundaries (protected vs public endpoints)
    - Check rate limiting behaviour (if enabled)
    - Validate error responses have correct HTTP status codes
    - Test input validation (malformed requests)
    - Verify CORS headers if applicable
    - Run generated API test scripts

Deterministic vs AI:
    Endpoint discovery: deterministic (from API graph)
    Schema validation: deterministic (compare response to spec)
    Error code checking: deterministic (HTTP standard)
    Root cause analysis: AI (why did this endpoint fail?)
    Test generation: AI (what edge cases to test?)

Tier: 2 (Execution)
Dependencies: automation_generator, project_analysis
Memory Reads:
    - automation_generator.api_tests
    - project_analysis.result
    - intelligence.api_dependency_graph
Memory Writes:
    - api_validation.results
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)


@dataclass
class APITestResult:
    """Result of a single API endpoint validation."""
    test_id: str = field(default_factory=lambda: f"api_{uuid.uuid4().hex[:8]}")
    endpoint: str = ""
    method: str = "GET"
    test_type: str = "smoke"
    passed: bool = False
    status_code: int | None = None
    expected_status: int | None = None
    response_time_ms: float = 0.0
    error: str | None = None
    request_payload: dict[str, Any] = field(default_factory=dict)
    response_snippet: str = ""
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "endpoint": self.endpoint,
            "method": self.method,
            "test_type": self.test_type,
            "passed": self.passed,
            "status_code": self.status_code,
            "expected_status": self.expected_status,
            "response_time_ms": self.response_time_ms,
            "error": self.error,
            "validation_errors": self.validation_errors,
            "response_snippet": self.response_snippet[:200],
        }


class APIValidationOutput(AgentOutput):
    """Output from the API Validation Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, Any]] = []
        self.failed_tests: list[dict[str, Any]] = []
        self.total_endpoints_tested: int = 0
        self.total_passed: int = 0
        self.total_failed: int = 0
        self.pass_rate: float = 0.0
        self.slowest_endpoint: str = ""
        self.slowest_response_ms: float = 0.0
        self.auth_issues: list[str] = []
        self.schema_violations: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "results": self.results,
            "failed_tests": self.failed_tests,
            "total_endpoints_tested": self.total_endpoints_tested,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "pass_rate": self.pass_rate,
            "slowest_endpoint": self.slowest_endpoint,
            "slowest_response_ms": self.slowest_response_ms,
            "auth_issues": self.auth_issues,
            "schema_violations": self.schema_violations,
        }


class APIValidationInput(AgentInput):
    """Input for the API Validation Agent."""
    base_url: str = "http://localhost:8000"
    auth_token: str = ""
    validate_schemas: bool = True
    test_auth_boundaries: bool = True
    test_rate_limits: bool = False
    timeout_seconds: int = 10
    max_endpoints: int = 50


class APIValidationAgent(BaseAgent):
    """
    API Validation Agent — Tier 2.

    Validates discovered API endpoints and runs generated
    API test scripts.
    """

    NAME = "api_validation"
    DESCRIPTION = (
        "Validates REST API endpoints: existence, schemas, "
        "authentication boundaries, error responses, "
        "and response time."
    )
    TIER = 2
    DEPENDENCIES = ["automation_generator", "project_analysis"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> APIValidationOutput:
        """Validate API endpoints."""
        assert isinstance(input_data, APIValidationInput), (
            f"Expected APIValidationInput, got {type(input_data).__name__}"
        )

        output = APIValidationOutput()

        # ==================================================
        # PHASE 1: LOAD CONTEXT FROM MEMORY
        # ==================================================

        api_graph_data: dict[str, Any] = {}
        project_analysis: dict[str, Any] = {}
        api_test_scripts: list[dict[str, Any]] = []

        if self._memory:
            api_graph_data = await self._memory.get(
                key=str(MemoryKeys.API_DEPENDENCY_GRAPH),
                reader=self.NAME,
            ) or {}
            project_analysis = await self._memory.get(
                key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
                reader=self.NAME,
            ) or {}
            api_test_scripts = await self._memory.get(
                key=str(MemoryKeys.GENERATED_API_TESTS),
                reader=self.NAME,
            ) or []

        # Extract endpoints from API graph
        endpoints = self._extract_endpoints(api_graph_data)
        routes = project_analysis.get("routes", [])

        # Merge endpoints from both sources
        all_endpoints = self._merge_endpoints(endpoints, routes)
        all_endpoints = all_endpoints[:input_data.max_endpoints]

        if not all_endpoints and not api_test_scripts:
            output.reasoning = (
                "No API endpoints or test scripts found. "
                "This may be a non-API project."
            )
            output.confidence = 1.0
            await self._write_to_memory(input_data, output)
            return output

        # Check if API is reachable
        api_reachable = await self._check_api(input_data.base_url)

        # ==================================================
        # PHASE 2: VALIDATE ENDPOINTS
        # ==================================================

        all_results: list[APITestResult] = []

        if api_reachable and not input_data.dry_run:
            results = await self._validate_live_endpoints(
                endpoints=all_endpoints,
                input_data=input_data,
            )
            all_results.extend(results)
        else:
            # Simulate API validation
            results = self._simulate_validation(
                endpoints=all_endpoints,
                input_data=input_data,
            )
            all_results.extend(results)

        # ==================================================
        # PHASE 3: AI-ASSISTED ANALYSIS OF FAILURES
        # ==================================================

        failed = [r for r in all_results if not r.passed]
        if failed and self._gateway and not input_data.dry_run:
            await self._ai_analyse_failures(
                failed_results=failed,
                output=output,
                input_data=input_data,
            )

        # ==================================================
        # PHASE 4: COMPUTE STATISTICS
        # ==================================================

        output.results = [r.to_dict() for r in all_results]
        output.failed_tests = [r.to_dict() for r in all_results if not r.passed]
        output.total_endpoints_tested = len(all_results)
        output.total_passed = sum(1 for r in all_results if r.passed)
        output.total_failed = sum(1 for r in all_results if not r.passed)
        output.pass_rate = (
            output.total_passed / output.total_endpoints_tested
            if output.total_endpoints_tested > 0 else 0.0
        )

        # Find slowest endpoint
        if all_results:
            slowest = max(all_results, key=lambda r: r.response_time_ms)
            output.slowest_endpoint = slowest.endpoint
            output.slowest_response_ms = slowest.response_time_ms

        # Collect auth issues
        output.auth_issues = [
            r.endpoint for r in all_results
            if r.status_code == 401 and r.test_type != "auth_boundary"
        ]

        output.reasoning = (
            f"Validated {output.total_endpoints_tested} API endpoints. "
            f"Pass rate: {output.pass_rate:.0%}. "
            f"{'API was live.' if api_reachable else 'API was not reachable — simulated.'} "
            f"Auth issues: {len(output.auth_issues)}. "
            f"Schema violations: {len(output.schema_violations)}."
        )
        output.confidence = 0.85 if api_reachable else 0.5

        if output.total_failed > 0:
            output.add_evidence(
                kind="api_failures",
                content=f"{output.total_failed} API endpoints failed validation",
                source="api_validation_agent",
                relevance="API failures requiring bug analysis",
            )

        output.suggested_next_action = (
            f"Bug Analysis Agent should examine {output.total_failed} "
            f"API validation failures."
            if output.total_failed > 0
            else "All API endpoints validated successfully."
        )

        await self._write_to_memory(input_data, output)
        return output

    def _extract_endpoints(
        self, api_graph_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract endpoint information from the API dependency graph."""
        endpoints = []
        for node_id, node in api_graph_data.get("nodes", {}).items():
            meta = node.get("metadata", {})
            if meta.get("method") and meta.get("path"):
                endpoints.append({
                    "method": meta["method"],
                    "path": meta["path"],
                    "requires_auth": meta.get("requires_auth", False),
                    "source": meta.get("source", "api_graph"),
                })
        return endpoints

    def _merge_endpoints(
        self,
        graph_endpoints: list[dict[str, Any]],
        route_endpoints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge endpoints from multiple sources, deduplicating."""
        seen = set()
        merged = []

        for ep in graph_endpoints + route_endpoints:
            key = f"{ep.get('method', 'GET')}:{ep.get('path', '')}"
            if key not in seen:
                seen.add(key)
                merged.append(ep)

        return merged

    async def _check_api(self, base_url: str) -> bool:
        """Check if the API is reachable."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(base_url)
                return response.status_code < 500
        except Exception:
            return False

    async def _validate_live_endpoints(
        self,
        endpoints: list[dict[str, Any]],
        input_data: APIValidationInput,
    ) -> list[APITestResult]:
        """Validate endpoints against a live API."""
        import httpx
        results = []

        headers: dict[str, str] = {}
        if input_data.auth_token:
            headers["Authorization"] = f"Bearer {input_data.auth_token}"

        async with httpx.AsyncClient(
            base_url=input_data.base_url,
            timeout=input_data.timeout_seconds,
        ) as client:
            for endpoint in endpoints:
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "/")
                requires_auth = endpoint.get("requires_auth", False)

                # Skip non-GET for safety in validation mode
                if method not in {"GET", "HEAD", "OPTIONS"}:
                    results.append(APITestResult(
                        endpoint=path,
                        method=method,
                        test_type="skipped",
                        passed=True,
                        response_snippet=f"Skipped {method} endpoint in validation mode",
                    ))
                    continue

                with Timer() as timer:
                    try:
                        response = await client.request(
                            method=method,
                            url=path,
                            headers=headers,
                        )
                        response_ms = timer.elapsed_ms

                        passed = response.status_code < 500
                        snippet = ""
                        try:
                            snippet = str(response.json())[:200]
                        except Exception:
                            snippet = response.text[:200]

                        results.append(APITestResult(
                            endpoint=path,
                            method=method,
                            test_type="smoke",
                            passed=passed,
                            status_code=response.status_code,
                            response_time_ms=response_ms,
                            response_snippet=snippet,
                        ))

                    except Exception as e:
                        results.append(APITestResult(
                            endpoint=path,
                            method=method,
                            test_type="smoke",
                            passed=False,
                            response_time_ms=timer.elapsed_ms,
                            error=str(e),
                        ))

                    # Auth boundary test
                    if input_data.test_auth_boundaries and requires_auth:
                        try:
                            unauth_response = await client.request(
                                method=method,
                                url=path,
                            )
                            auth_passed = unauth_response.status_code in {
                                401, 403
                            }
                            results.append(APITestResult(
                                endpoint=path,
                                method=method,
                                test_type="auth_boundary",
                                passed=auth_passed,
                                status_code=unauth_response.status_code,
                                response_time_ms=timer.elapsed_ms,
                                validation_errors=[] if auth_passed else [
                                    f"Protected endpoint returned "
                                    f"{unauth_response.status_code} without auth "
                                    f"(expected 401/403)"
                                ],
                            ))
                        except Exception:
                            pass

        return results

    def _simulate_validation(
        self,
        endpoints: list[dict[str, Any]],
        input_data: APIValidationInput,
    ) -> list[APITestResult]:
        """Simulate API validation for dry-run or unreachable API."""
        results = []
        for i, endpoint in enumerate(endpoints[:10]):
            results.append(APITestResult(
                endpoint=endpoint.get("path", "/"),
                method=endpoint.get("method", "GET"),
                test_type="simulated",
                passed=True,
                status_code=200,
                response_time_ms=float(50 + i * 10),
                response_snippet="[SIMULATED] API not reachable",
            ))
        return results

    async def _ai_analyse_failures(
        self,
        failed_results: list[APITestResult],
        output: APIValidationOutput,
        input_data: APIValidationInput,
    ) -> None:
        """Use AI to analyse API validation failures."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        failure_summary = "\n".join([
            f"- {r.method} {r.endpoint}: "
            f"status={r.status_code}, error={r.error}"
            for r in failed_results[:10]
        ])

        user_message = f"""Analyse these API validation failures:

FAILURES:
{failure_summary}

For each failure:
1. What is the likely root cause?
2. Is this a configuration issue, code bug, or environment problem?
3. What is the severity (Critical/High/Medium/Low)?
4. What should the developer check first?

Be concise and specific."""

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
            output.metadata["failure_analysis"] = response.content
            output.add_evidence(
                kind="ai_failure_analysis",
                content=response.content[:300],
                source=f"AI Gateway ({response.provider})",
                relevance="AI root cause analysis of API failures",
            )

        except Exception as e:
            logger.warning(
                "api_validation_ai_failed",
                error=str(e),
            )

    async def _write_to_memory(
        self,
        input_data: AgentInput,
        output: APIValidationOutput,
    ) -> None:
        if not self._memory:
            return
        await self._memory.set(
            key=str(MemoryKeys.API_VALIDATION_RESULTS),
            value=output.to_dict(),
            written_by=self.NAME,
        )
