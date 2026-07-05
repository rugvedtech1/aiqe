"""Unit tests for Database Validation Agent."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.database_validation.agent import (
    DatabaseValidationAgent,
    DatabaseValidationInput,
    DatabaseValidationOutput,
    DatabaseIssue,
)


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def project_with_migrations(tmp_path):
    """Project with database migrations including dangerous ones."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()

    (migrations / "0001_initial.py").write_text("""
def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String()),
    )

def downgrade():
    op.drop_table('users')
""")

    (migrations / "0002_add_products.py").write_text("""
def upgrade():
    op.create_table('products',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String()),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
    )
    # WARNING: DROP TABLE old_products
    op.DROP TABLE old_data

def downgrade():
    op.drop_table('products')
""")

    src = tmp_path / "src"
    src.mkdir()
    (src / "views.py").write_text("""
def get_all_users():
    users = User.objects.all()
    for user in users:
        orders = user.orders.all()
    return users
""")

    return tmp_path


class TestDatabaseValidationClassVars:
    def test_name(self):
        assert DatabaseValidationAgent.NAME == "database_validation"

    def test_tier(self):
        assert DatabaseValidationAgent.TIER == 3

    def test_dependencies(self):
        assert "project_analysis" in DatabaseValidationAgent.DEPENDENCIES


class TestDatabaseValidationExecution:
    @pytest.mark.asyncio
    async def test_detects_dangerous_migration(
        self, mock_memory, project_with_migrations
    ):
        mock_memory.get = AsyncMock(side_effect=[
            {"nodes": {}, "edges": []},
            {"has_database": True, "dependencies": ["sqlalchemy"]},
        ])
        agent = DatabaseValidationAgent(memory_store=mock_memory)
        input_data = DatabaseValidationInput(
            workflow_id="wf_001",
            project_path=str(project_with_migrations),
            check_n_plus_one=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.has_dangerous_migrations is True
        assert len(output.dangerous_migration_files) > 0

    @pytest.mark.asyncio
    async def test_detects_n_plus_one(
        self, mock_memory, project_with_migrations
    ):
        mock_memory.get = AsyncMock(side_effect=[
            {"nodes": {}, "edges": []},
            {"has_database": True},
        ])
        agent = DatabaseValidationAgent(memory_store=mock_memory)
        input_data = DatabaseValidationInput(
            workflow_id="wf_001",
            project_path=str(project_with_migrations),
            check_migrations=False,
            check_constraints=False,
            check_indexes=False,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        n1_issues = [
            i for i in output.issues
            if i.get("category") == "n_plus_one"
        ]
        assert len(n1_issues) > 0

    @pytest.mark.asyncio
    async def test_no_database_skips_validation(
        self, mock_memory, tmp_path
    ):
        mock_memory.get = AsyncMock(side_effect=[
            {"nodes": {}, "edges": []},
            {"has_database": False},
        ])
        agent = DatabaseValidationAgent(memory_store=mock_memory)
        input_data = DatabaseValidationInput(
            workflow_id="wf_001",
            project_path=str(tmp_path),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.total_issues == 0
        assert "skipped" in output.reasoning.lower()

    @pytest.mark.asyncio
    async def test_writes_to_memory(self, mock_memory, tmp_path):
        mock_memory.get = AsyncMock(side_effect=[
            {"nodes": {}, "edges": []},
            {"has_database": True},
        ])
        agent = DatabaseValidationAgent(memory_store=mock_memory)
        input_data = DatabaseValidationInput(
            workflow_id="wf_001",
            project_path=str(tmp_path),
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 1

    @pytest.mark.asyncio
    async def test_migration_count_tracked(
        self, mock_memory, project_with_migrations
    ):
        mock_memory.get = AsyncMock(side_effect=[
            {"nodes": {}, "edges": []},
            {"has_database": True},
        ])
        agent = DatabaseValidationAgent(memory_store=mock_memory)
        input_data = DatabaseValidationInput(
            workflow_id="wf_001",
            project_path=str(project_with_migrations),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.migration_files_checked >= 2


class TestDatabaseIssue:
    def test_auto_id(self):
        issue = DatabaseIssue(category="n_plus_one")
        assert issue.id.startswith("db_")

    def test_to_dict(self):
        issue = DatabaseIssue(
            category="dangerous_migration",
            title="DROP TABLE detected",
            severity="High",
            confidence=0.95,
            is_blocking=True,
        )
        d = issue.to_dict()
        assert d["is_blocking"] is True
        assert d["severity"] == "High"
        assert d["confidence"] == 0.95


class TestRegistrySetupTier3:
    def test_all_ten_agents_in_registry(self):
        from aiqe.workflow.registry import AgentRegistry
        from aiqe.agents.registry_setup import register_all_agents
        import aiqe.agents.registry_setup as setup_mod
        import aiqe.workflow.registry as reg_mod

        fresh = AgentRegistry()
        orig = reg_mod.agent_registry
        reg_mod.agent_registry = fresh
        setup_mod.agent_registry = fresh

        try:
            register_all_agents()
            assert fresh.count == 10

            tier1 = fresh.get_tier(1)
            tier2 = fresh.get_tier(2)
            tier3 = fresh.get_tier(3)

            assert len(tier1) == 4
            assert len(tier2) == 3
            assert len(tier3) == 3

            assert fresh.is_registered("security_testing")
            assert fresh.is_registered("performance")
            assert fresh.is_registered("database_validation")
        finally:
            reg_mod.agent_registry = orig
            setup_mod.agent_registry = orig
