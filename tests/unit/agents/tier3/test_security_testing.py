"""Unit tests for Security Testing Agent."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.security_testing.agent import (
    SecurityTestingAgent,
    SecurityTestingInput,
    SecurityTestingOutput,
    SecurityFinding,
)


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def vulnerable_project(tmp_path):
    """Project with intentional security issues."""
    src = tmp_path / "src"
    src.mkdir()

    # SQL injection
    (src / "db.py").write_text("""
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id={user_id}"
    return db.execute(query)
""")

    # XSS
    (src / "template.js").write_text("""
function render(data) {
    element.innerHTML = data.userInput;
    document.write(data.name);
}
""")

    # Hardcoded secret (not in example/test file)
    (src / "config.py").write_text("""
database_password = "supersecret123"
api_key = "sk-abcdefghijklmnop12345"
""")

    return tmp_path


class TestSecurityTestingClassVars:
    def test_name(self):
        assert SecurityTestingAgent.NAME == "security_testing"

    def test_tier(self):
        assert SecurityTestingAgent.TIER == 3

    def test_dependencies(self):
        assert "project_analysis" in SecurityTestingAgent.DEPENDENCIES


class TestSecurityTestingExecution:
    @pytest.mark.asyncio
    async def test_detects_sql_injection(
        self, mock_memory, vulnerable_project
    ):
        agent = SecurityTestingAgent(memory_store=mock_memory)
        input_data = SecurityTestingInput(
            workflow_id="wf_001",
            project_path=str(vulnerable_project),
            scan_xss=False,
            scan_secrets=False,
            scan_dependencies=False,
            scan_headers=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        sql_findings = [
            f for f in output.findings
            if f.get("category") == "sql_injection"
        ]
        assert len(sql_findings) > 0

    @pytest.mark.asyncio
    async def test_detects_xss(self, mock_memory, vulnerable_project):
        agent = SecurityTestingAgent(memory_store=mock_memory)
        input_data = SecurityTestingInput(
            workflow_id="wf_001",
            project_path=str(vulnerable_project),
            scan_sql_injection=False,
            scan_secrets=False,
            scan_dependencies=False,
            scan_headers=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        xss_findings = [
            f for f in output.findings
            if f.get("category") == "xss"
        ]
        assert len(xss_findings) > 0

    @pytest.mark.asyncio
    async def test_detects_secrets(self, mock_memory, vulnerable_project):
        agent = SecurityTestingAgent(memory_store=mock_memory)
        input_data = SecurityTestingInput(
            workflow_id="wf_001",
            project_path=str(vulnerable_project),
            scan_sql_injection=False,
            scan_xss=False,
            scan_dependencies=False,
            scan_headers=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        secret_findings = [
            f for f in output.findings
            if f.get("category") == "secrets"
        ]
        assert len(secret_findings) > 0

    @pytest.mark.asyncio
    async def test_secrets_are_redacted_in_output(
        self, mock_memory, vulnerable_project
    ):
        agent = SecurityTestingAgent(memory_store=mock_memory)
        input_data = SecurityTestingInput(
            workflow_id="wf_001",
            project_path=str(vulnerable_project),
            scan_sql_injection=False,
            scan_xss=False,
            scan_dependencies=False,
            scan_headers=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        for finding in output.findings:
            snippet = finding.get("snippet", "")
            assert "supersecret" not in snippet
            assert "sk-abc" not in snippet

    @pytest.mark.asyncio
    async def test_detects_vulnerable_dependency(self, mock_memory, tmp_path):
        mock_memory.get = AsyncMock(side_effect=[
            {
                "language": "python",
                "dependencies": ["django==1.11.0", "flask>=0.12.0"],
                "has_database": False,
            }
        ])
        agent = SecurityTestingAgent(memory_store=mock_memory)
        input_data = SecurityTestingInput(
            workflow_id="wf_001",
            project_path=str(tmp_path),
            scan_sql_injection=False,
            scan_xss=False,
            scan_secrets=False,
            scan_headers=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        dep_findings = [
            f for f in output.findings
            if f.get("category") == "vulnerable_dependency"
        ]
        assert len(dep_findings) > 0

    @pytest.mark.asyncio
    async def test_writes_to_memory(self, mock_memory, tmp_path):
        agent = SecurityTestingAgent(memory_store=mock_memory)
        input_data = SecurityTestingInput(
            workflow_id="wf_001",
            project_path=str(tmp_path),
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 1

    @pytest.mark.asyncio
    async def test_findings_have_cwe(
        self, mock_memory, vulnerable_project
    ):
        agent = SecurityTestingAgent(memory_store=mock_memory)
        input_data = SecurityTestingInput(
            workflow_id="wf_001",
            project_path=str(vulnerable_project),
            scan_headers=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        for finding in output.findings:
            if finding.get("category") != "vulnerable_dependency":
                assert finding.get("cwe"), f"Missing CWE in {finding}"

    @pytest.mark.asyncio
    async def test_clean_project_has_no_findings(
        self, mock_memory, tmp_path
    ):
        src = tmp_path / "src"
        src.mkdir()
        (src / "clean.py").write_text("""
from sqlalchemy import text

def get_user(user_id: int):
    query = text("SELECT * FROM users WHERE id = :user_id")
    return db.execute(query, {"user_id": user_id})
""")
        agent = SecurityTestingAgent(memory_store=mock_memory)
        input_data = SecurityTestingInput(
            workflow_id="wf_001",
            project_path=str(tmp_path),
            scan_headers=False,
            scan_dependencies=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        sql_findings = [
            f for f in output.findings
            if f.get("category") == "sql_injection"
        ]
        assert len(sql_findings) == 0


class TestSecurityFinding:
    def test_auto_id(self):
        finding = SecurityFinding(category="xss", title="XSS found")
        assert finding.id.startswith("sec_")

    def test_to_dict_redacts_snippet(self):
        finding = SecurityFinding(
            category="secrets",
            snippet="password = 'supersecret123'",
        )
        d = finding.to_dict()
        assert len(d["snippet"]) <= 200
