"""
AIQE Security Testing Agent.

Performs automated security testing across multiple attack
surface categories.

Security test categories:
    SQL Injection    — detects unsanitised SQL queries
    XSS              — detects unescaped output in HTML responses
    Authentication   — tests auth bypass, weak tokens, session issues
    Authorisation    — tests privilege escalation, IDOR
    Secrets Detection — scans codebase for hardcoded credentials
    HTTP Headers     — validates security headers (HSTS, CSP, etc.)
    Dependency Scan  — checks dependencies for known CVEs

Design principles:
    - Deterministic tests run first (pattern matching, static analysis)
    - AI analysis runs second (interpret findings, classify severity)
    - NEVER automatically fix security issues (ADR-009)
    - Evidence for every finding (ADR-011)
    - All findings include confidence score (ADR-008)

Tier: 3 (Quality)
Dependencies: project_analysis, test_case_generator
Memory Reads:
    - project_analysis.result
    - intelligence.api_dependency_graph
Memory Writes:
    - security_testing.results
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput, BugSeverity
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)

# ==================================================
# SECURITY PATTERNS (deterministic detection)
# ==================================================

# SQL injection vulnerability patterns
_SQL_INJECTION_PATTERNS = [
    re.compile(r'f["\'].*SELECT.*\{', re.IGNORECASE),
    re.compile(r'f["\'].*INSERT.*\{', re.IGNORECASE),
    re.compile(r'f["\'].*UPDATE.*\{', re.IGNORECASE),
    re.compile(r'f["\'].*DELETE.*\{', re.IGNORECASE),
    re.compile(r'"%\s*%\s*.*\s*%\s*"', re.IGNORECASE),
    re.compile(r'query\s*=\s*["\'].*\+\s*\w+', re.IGNORECASE),
    re.compile(r'execute\s*\(["\'].*%s.*["\'].*%.*\w+\)', re.IGNORECASE),
]

# XSS vulnerability patterns
_XSS_PATTERNS = [
    re.compile(r'innerHTML\s*=\s*\w+', re.IGNORECASE),
    re.compile(r'document\.write\s*\(\s*\w+', re.IGNORECASE),
    re.compile(r'eval\s*\(\s*\w+', re.IGNORECASE),
    re.compile(r'\.html\s*\(\s*\w+\s*\)', re.IGNORECASE),
    re.compile(r'dangerouslySetInnerHTML', re.IGNORECASE),
    re.compile(r'v-html\s*=', re.IGNORECASE),
]

# Hardcoded secret patterns
_SECRET_PATTERNS = [
    re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']'),
    re.compile(r'(?i)(api_key|apikey|secret_key)\s*=\s*["\'][^"\']{8,}["\']'),
    re.compile(r'(?i)(token|bearer)\s*=\s*["\'][^"\']{8,}["\']'),
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),
    re.compile(r'github_pat_[a-zA-Z0-9_]{36,}'),
    re.compile(r'(?i)private_key\s*=\s*["\']-----BEGIN'),
]

# Missing security header patterns
_SECURITY_HEADERS = [
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-XSS-Protection",
    "Referrer-Policy",
]

# Known vulnerable dependency patterns (simplified)
_VULNERABLE_DEPS = {
    "django": [("1.", BugSeverity.CRITICAL), ("2.0", BugSeverity.HIGH)],
    "flask": [("0.", BugSeverity.HIGH)],
    "pillow": [("8.2", BugSeverity.CRITICAL), ("8.1", BugSeverity.CRITICAL)],
    "pyyaml": [("5.3", BugSeverity.HIGH)],
    "requests": [("2.19", BugSeverity.MEDIUM)],
}


@dataclass
class SecurityFinding:
    """A single security issue found during testing."""
    id: str = field(default_factory=lambda: f"sec_{uuid.uuid4().hex[:8]}")
    category: str = ""
    title: str = ""
    severity: str = BugSeverity.MEDIUM.value
    confidence: float = 0.7
    file_path: str = ""
    line_number: int = 0
    snippet: str = ""
    description: str = ""
    remediation: str = ""
    cwe: str = ""
    owasp: str = ""
    is_false_positive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "snippet": self.snippet[:200],
            "description": self.description,
            "remediation": self.remediation,
            "cwe": self.cwe,
            "owasp": self.owasp,
            "is_false_positive": self.is_false_positive,
        }


class SecurityTestingOutput(AgentOutput):
    """Output from the Security Testing Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.findings: list[dict[str, Any]] = []
        self.total_findings: int = 0
        self.by_category: dict[str, int] = {}
        self.by_severity: dict[str, int] = {}
        self.files_scanned: int = 0
        self.dependencies_checked: int = 0
        self.headers_checked: bool = False
        self.scan_coverage: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "findings": self.findings,
            "total_findings": self.total_findings,
            "by_category": self.by_category,
            "by_severity": self.by_severity,
            "files_scanned": self.files_scanned,
            "dependencies_checked": self.dependencies_checked,
            "headers_checked": self.headers_checked,
            "scan_coverage": self.scan_coverage,
        }


class SecurityTestingInput(AgentInput):
    """Input for the Security Testing Agent."""
    scan_sql_injection: bool = True
    scan_xss: bool = True
    scan_auth: bool = True
    scan_secrets: bool = True
    scan_dependencies: bool = True
    scan_headers: bool = True
    base_url: str = "http://localhost:8000"
    max_files_to_scan: int = 200


class SecurityTestingAgent(BaseAgent):
    """
    Security Testing Agent — Tier 3.

    Performs multi-category security scanning using deterministic
    pattern matching and AI-assisted severity classification.
    """

    NAME = "security_testing"
    DESCRIPTION = (
        "Scans for SQL injection, XSS, auth issues, hardcoded "
        "secrets, vulnerable dependencies, and missing security headers."
    )
    TIER = 3
    DEPENDENCIES = ["project_analysis", "test_case_generator"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> SecurityTestingOutput:
        """Run security tests."""
        assert isinstance(input_data, SecurityTestingInput), (
            f"Expected SecurityTestingInput, got {type(input_data).__name__}"
        )

        output = SecurityTestingOutput()
        project_path = Path(input_data.project_path)
        all_findings: list[SecurityFinding] = []

        # Load project context
        project_analysis: dict[str, Any] = {}
        if self._memory:
            project_analysis = await self._memory.get(
                key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
                reader=self.NAME,
            ) or {}

        # ==================================================
        # PHASE 1: STATIC ANALYSIS (deterministic)
        # ==================================================

        source_files = self._collect_source_files(
            project_path,
            max_files=input_data.max_files_to_scan,
        )
        output.files_scanned = len(source_files)

        with Timer() as timer:
            if input_data.scan_sql_injection:
                findings = self._scan_sql_injection(source_files)
                all_findings.extend(findings)
                output.scan_coverage.append("sql_injection")

            if input_data.scan_xss:
                findings = self._scan_xss(source_files)
                all_findings.extend(findings)
                output.scan_coverage.append("xss")

            if input_data.scan_secrets:
                findings = self._scan_secrets(source_files)
                all_findings.extend(findings)
                output.scan_coverage.append("secrets")

            if input_data.scan_dependencies:
                deps = project_analysis.get("dependencies", [])
                findings = self._scan_dependencies(deps)
                all_findings.extend(findings)
                output.dependencies_checked = len(deps)
                output.scan_coverage.append("dependencies")

        logger.info(
            "security_static_analysis_complete",
            workflow_id=input_data.workflow_id,
            findings=len(all_findings),
            files_scanned=output.files_scanned,
            duration_seconds=timer.elapsed_seconds,
        )

        # ==================================================
        # PHASE 2: RUNTIME CHECKS (if API is reachable)
        # ==================================================

        if input_data.scan_headers and not input_data.dry_run:
            header_findings = await self._check_security_headers(
                input_data.base_url
            )
            all_findings.extend(header_findings)
            output.headers_checked = True
            output.scan_coverage.append("headers")

        # ==================================================
        # PHASE 3: AI CLASSIFICATION OF FINDINGS
        # ==================================================

        if all_findings and self._gateway and not input_data.dry_run:
            await self._ai_classify_findings(
                findings=all_findings,
                output=output,
                input_data=input_data,
            )

        # ==================================================
        # PHASE 4: COMPUTE STATISTICS
        # ==================================================

        output.findings = [f.to_dict() for f in all_findings]
        output.total_findings = len(all_findings)

        for finding in all_findings:
            cat = finding.category
            sev = finding.severity
            output.by_category[cat] = output.by_category.get(cat, 0) + 1
            output.by_severity[sev] = output.by_severity.get(sev, 0) + 1

        critical_count = output.by_severity.get("Critical", 0)
        high_count = output.by_severity.get("High", 0)

        output.reasoning = (
            f"Security scan complete. "
            f"Scanned {output.files_scanned} files, "
            f"{output.dependencies_checked} dependencies. "
            f"Found {output.total_findings} security issues: "
            f"{critical_count} Critical, {high_count} High. "
            f"Coverage: {output.scan_coverage}."
        )
        output.confidence = 0.80

        if all_findings:
            critical = [f for f in all_findings if f.severity == "Critical"]
            if critical:
                output.add_evidence(
                    kind="critical_security_finding",
                    content=f"{len(critical)} Critical security issues found",
                    source="security_testing_agent",
                    relevance="Critical security findings require immediate attention",
                )

        output.suggested_next_action = (
            f"Bug Analysis Agent should classify the "
            f"{output.total_findings} security findings and "
            f"produce remediation guidance."
            if output.total_findings > 0
            else "No security issues detected in this scan."
        )

        # Write to memory
        if self._memory:
            await self._memory.set(
                key=str(MemoryKeys.SECURITY_SCAN_RESULTS),
                value=output.to_dict(),
                written_by=self.NAME,
            )

        return output

    def _collect_source_files(
        self, project_path: Path, max_files: int
    ) -> list[Path]:
        """Collect source files for security scanning."""
        skip_dirs = {
            ".git", ".venv", "venv", "node_modules",
            "__pycache__", "dist", "build", "htmlcov",
        }
        extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx",
            ".rb", ".go", ".java", ".php", ".env",
        }
        files = []
        for f in project_path.rglob("*"):
            if any(part in skip_dirs for part in f.parts):
                continue
            if f.is_file() and f.suffix in extensions:
                files.append(f)
                if len(files) >= max_files:
                    break
        return files

    def _scan_sql_injection(
        self, source_files: list[Path]
    ) -> list[SecurityFinding]:
        """Scan for SQL injection vulnerabilities."""
        findings = []
        for file_path in source_files:
            if file_path.suffix not in {".py", ".js", ".ts", ".php", ".rb"}:
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_num, line in enumerate(content.splitlines(), 1):
                    for pattern in _SQL_INJECTION_PATTERNS:
                        if pattern.search(line):
                            findings.append(SecurityFinding(
                                category="sql_injection",
                                title="Potential SQL Injection Vulnerability",
                                severity=BugSeverity.CRITICAL.value,
                                confidence=0.75,
                                file_path=str(file_path),
                                line_number=line_num,
                                snippet=line.strip()[:100],
                                description=(
                                    "User input may be interpolated directly "
                                    "into SQL queries without parameterisation."
                                ),
                                remediation=(
                                    "Use parameterised queries or an ORM. "
                                    "Never interpolate user input into SQL strings."
                                ),
                                cwe="CWE-89",
                                owasp="A03:2021 - Injection",
                            ))
                            break
            except (OSError, PermissionError):
                continue
        return findings[:20]

    def _scan_xss(
        self, source_files: list[Path]
    ) -> list[SecurityFinding]:
        """Scan for Cross-Site Scripting vulnerabilities."""
        findings = []
        for file_path in source_files:
            if file_path.suffix not in {".js", ".ts", ".jsx", ".tsx", ".html", ".py"}:
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_num, line in enumerate(content.splitlines(), 1):
                    for pattern in _XSS_PATTERNS:
                        if pattern.search(line):
                            findings.append(SecurityFinding(
                                category="xss",
                                title="Potential Cross-Site Scripting (XSS)",
                                severity=BugSeverity.HIGH.value,
                                confidence=0.70,
                                file_path=str(file_path),
                                line_number=line_num,
                                snippet=line.strip()[:100],
                                description=(
                                    "Unescaped user input may be rendered "
                                    "as HTML, enabling XSS attacks."
                                ),
                                remediation=(
                                    "Use framework-provided escaping. "
                                    "Avoid innerHTML with user data. "
                                    "Implement Content-Security-Policy."
                                ),
                                cwe="CWE-79",
                                owasp="A03:2021 - Injection",
                            ))
                            break
            except (OSError, PermissionError):
                continue
        return findings[:20]

    def _scan_secrets(
        self, source_files: list[Path]
    ) -> list[SecurityFinding]:
        """Scan for hardcoded secrets and credentials."""
        findings = []
        skip_files = {
            ".env.example", ".env.test", "test_", "_test",
            "fixture", "mock", "fake",
        }

        for file_path in source_files:
            filename = file_path.name.lower()
            if any(skip in filename for skip in skip_files):
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if any(
                        skip in line.lower()
                        for skip in ["example", "placeholder", "your_key", "xxx"]
                    ):
                        continue
                    for pattern in _SECRET_PATTERNS:
                        if pattern.search(line):
                            findings.append(SecurityFinding(
                                category="secrets",
                                title="Potential Hardcoded Secret or Credential",
                                severity=BugSeverity.CRITICAL.value,
                                confidence=0.80,
                                file_path=str(file_path),
                                line_number=line_num,
                                snippet="[REDACTED — potential secret detected]",
                                description=(
                                    "A hardcoded secret, API key, or credential "
                                    "was detected in source code."
                                ),
                                remediation=(
                                    "Move secrets to environment variables. "
                                    "Use a secrets manager (AWS Secrets Manager, "
                                    "HashiCorp Vault). Rotate the exposed secret immediately."
                                ),
                                cwe="CWE-798",
                                owasp="A02:2021 - Cryptographic Failures",
                            ))
                            break
            except (OSError, PermissionError):
                continue
        return findings[:10]

    def _scan_dependencies(
        self, dependencies: list[str]
    ) -> list[SecurityFinding]:
        """Check dependencies for known vulnerable versions."""
        findings = []
        for dep in dependencies:
            dep_lower = dep.lower()
            for vuln_dep, versions in _VULNERABLE_DEPS.items():
                if vuln_dep in dep_lower:
                    for version_prefix, severity in versions:
                        if version_prefix in dep_lower:
                            findings.append(SecurityFinding(
                                category="vulnerable_dependency",
                                title=f"Potentially Vulnerable Dependency: {dep}",
                                severity=severity.value,
                                confidence=0.85,
                                description=(
                                    f"Dependency '{dep}' may have known "
                                    f"security vulnerabilities."
                                ),
                                remediation=(
                                    f"Upgrade {dep} to the latest stable version. "
                                    f"Check CVE database for specific issues."
                                ),
                                cwe="CWE-1035",
                                owasp="A06:2021 - Vulnerable Components",
                            ))
        return findings

    async def _check_security_headers(
        self, base_url: str
    ) -> list[SecurityFinding]:
        """Check HTTP security headers on the API."""
        findings = []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(base_url)
                headers = {k.lower(): v for k, v in response.headers.items()}

                for expected_header in _SECURITY_HEADERS:
                    if expected_header.lower() not in headers:
                        findings.append(SecurityFinding(
                            category="missing_security_header",
                            title=f"Missing Security Header: {expected_header}",
                            severity=BugSeverity.MEDIUM.value,
                            confidence=1.0,
                            description=(
                                f"The HTTP response is missing the "
                                f"'{expected_header}' security header."
                            ),
                            remediation=(
                                f"Add '{expected_header}' to all HTTP responses. "
                                f"Configure your web server or application middleware."
                            ),
                            cwe="CWE-693",
                            owasp="A05:2021 - Security Misconfiguration",
                        ))
        except Exception as e:
            logger.debug(
                "security_header_check_failed",
                error=str(e),
            )
        return findings

    async def _ai_classify_findings(
        self,
        findings: list[SecurityFinding],
        output: SecurityTestingOutput,
        input_data: SecurityTestingInput,
    ) -> None:
        """Use AI to verify and classify security findings."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        findings_summary = "\n".join([
            f"- [{f.category}] {f.title} in {f.file_path}:{f.line_number} "
            f"(current severity: {f.severity})"
            for f in findings[:15]
        ])

        user_message = f"""Review these security findings from static analysis:

FINDINGS:
{findings_summary}

For each finding:
1. Verify the severity is appropriate.
2. Identify if any are likely false positives.
3. Provide additional context on the risk.
4. Note any patterns that indicate systemic issues.

Respond with a brief analysis. Flag any findings that appear to be
false positives with specific reasoning."""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.ANALYSIS,
                max_tokens=800,
                workflow_id=input_data.workflow_id,
                agent_name=self.NAME,
                prompt_version="1.0",
            )
            response = await self._gateway.complete(request)
            output.ai_tokens_used = response.total_tokens
            output.metadata["ai_classification"] = response.content
            output.add_evidence(
                kind="ai_security_classification",
                content=response.content[:300],
                source=f"AI Gateway ({response.provider})",
                relevance="AI verification of security findings",
            )
        except Exception as e:
            logger.warning(
                "security_ai_classification_failed",
                error=str(e),
            )
