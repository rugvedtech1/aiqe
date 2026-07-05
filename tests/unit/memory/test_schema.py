"""Unit tests for MemoryKeys schema."""
from aiqe.memory.schema import MemoryKeys, MemoryKey


class TestMemoryKeys:
    def test_project_analysis_result_key(self):
        key = MemoryKeys.PROJECT_ANALYSIS_RESULT
        assert isinstance(key, MemoryKey)
        assert key.key == "project_analysis.result"
        assert key.writer == "project_analysis"
        assert str(key) == "project_analysis.result"

    def test_all_keys_returns_list(self):
        keys = MemoryKeys.all_keys()
        assert len(keys) > 0
        assert all(isinstance(k, MemoryKey) for k in keys)

    def test_keys_for_agent_returns_writes_and_reads(self):
        result = MemoryKeys.keys_for_agent("project_analysis")
        assert "writes" in result
        assert "reads" in result
        write_keys = [k.key for k in result["writes"]]
        assert "project_analysis.result" in write_keys

    def test_all_keys_have_unique_key_strings(self):
        keys = MemoryKeys.all_keys()
        key_strings = [k.key for k in keys]
        assert len(key_strings) == len(set(key_strings)), "Duplicate memory keys found"

    def test_wildcard_reader(self):
        result = MemoryKeys.keys_for_agent("any_random_agent")
        read_keys = [k.key for k in result["reads"]]
        assert "system.workflow_metadata" in read_keys
