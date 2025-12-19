"""Tests for ECO client functionality."""


from temper_workflow.gpbm.eco_client import EcoClient, EcoConfig


class TestEcoConfig:
    """Test EcoConfig configuration."""

    def test_config_has_default_values(self):
        """Verify config has non-empty defaults."""
        config = EcoConfig()
        assert config.SHARED
        assert config.LEGACY
        assert len(config.ROLES) > 0
        assert len(config.DOMAINS) > 0

    def test_role_user_ids_exist(self):
        """Verify expected roles have user IDs."""
        config = EcoConfig()
        expected_roles = ["architect", "coder", "tester", "human"]
        for role in expected_roles:
            assert role in config.ROLES, f"Missing role: {role}"

    def test_domain_user_ids_exist(self):
        """Verify expected domains have user IDs."""
        config = EcoConfig()
        expected_domains = ["firmware", "placer", "pcb"]
        for domain in expected_domains:
            assert domain in config.DOMAINS, f"Missing domain: {domain}"

    def test_get_user_id_for_role(self):
        """get_user_id should return role-specific ID."""
        config = EcoConfig()
        user_id = config.get_user_id(role="architect")
        assert user_id == "temper-architect"

    def test_get_user_id_for_domain(self):
        """get_user_id should return domain-specific ID."""
        config = EcoConfig()
        user_id = config.get_user_id(domain="firmware")
        assert user_id == "temper-firmware"


class TestEcoClient:
    """Test EcoClient class."""

    def test_client_initialization(self):
        """Client should initialize with default config."""
        client = EcoClient()
        assert client.config.base_url
        assert "eco" in client.config.base_url.lower()

    def test_client_custom_config(self):
        """Client should accept custom config."""
        custom_config = EcoConfig(base_url="https://custom.example.com")
        client = EcoClient(config=custom_config)
        assert client.config.base_url == "https://custom.example.com"


# Smoke test for imports
def test_imports():
    """Verify all expected modules can be imported."""
    from temper_workflow.agents import assign, auto_assign
    from temper_workflow.gpbm import gather, measure, plan

    assert gather
    assert plan
    assert measure
    assert assign
    assert auto_assign
