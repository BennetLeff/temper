"""Tests for validation.drc_result module (Check classes)."""

from temper_placer.validation.drc_result import (
    Check,
    ClearanceCheck,
    ComponentOverlapCheck,
    CourtyardCheck,
    CreepageCheck,
    FloatingPinsCheck,
    GroundPlaneCheck,
    HVLVSeparationCheck,
    IsolationCheck,
    LoopAreaCheck,
    NetConnectivityCheck,
    NoiseCouplingCheck,
    PowerDomainCheck,
    TraceClearanceCheck,
    ViaSpacingCheck,
    ZoneContainmentCheck,
)


class _MinimalCheck(Check):
    """Minimal concrete Check for testing the ABC."""

    @property
    def name(self) -> str:
        return "minimal"

    @property
    def category(self) -> str:
        return "drc"

    def run(self, placement, constraints, modified_regions=None):
        from temper_placer.validation.drc_result import CheckResult
        return CheckResult(check_name=self.name, passed=True)


class TestCheckABC:
    """Tests for the Check ABC default properties."""

    def test_code_prefix(self):
        c = _MinimalCheck()
        assert c.code_prefix == "DRC_MIN_"

    def test_description_default(self):
        c = _MinimalCheck()
        assert c.description == ""

    def test_supports_incremental_default(self):
        c = _MinimalCheck()
        assert c.supports_incremental is False

    def test_is_applicable_default(self):
        c = _MinimalCheck()
        assert c.is_applicable(None, None) is True


class TestStubChecks:
    """Smoke tests for each check stub class."""

    @staticmethod
    def _assert_check_stub(check: Check, expected_name: str, expected_category: str):
        """Common assertions for a check stub."""
        assert check.name == expected_name, f"{type(check).__name__}: name mismatch"
        assert check.category == expected_category, f"{type(check).__name__}: category mismatch"
        # description should be a non-empty string
        desc = check.description
        assert isinstance(desc, str)
        # code_prefix is derived
        assert check.code_prefix
        # supports_incremental default is fine
        assert isinstance(check.supports_incremental, bool)

    def test_clearance_check(self):
        self._assert_check_stub(ClearanceCheck(), "drc_clearance", "drc")

    def test_component_overlap_check(self):
        c = ComponentOverlapCheck()
        assert c.name == "drc_component_overlap"
        assert c.category == "drc"
        # ComponentOverlapCheck overrides supports_incremental
        assert c.supports_incremental is True

    def test_courtyard_check(self):
        self._assert_check_stub(CourtyardCheck(), "drc_courtyard", "drc")

    def test_creepage_check(self):
        self._assert_check_stub(CreepageCheck(), "safety_creepage", "safety")

    def test_floating_pins_check(self):
        self._assert_check_stub(FloatingPinsCheck(), "erc_floating_pins", "erc")

    def test_ground_plane_check(self):
        self._assert_check_stub(GroundPlaneCheck(), "emc_ground_plane", "emc")

    def test_hv_lv_separation_check(self):
        self._assert_check_stub(HVLVSeparationCheck(), "safety_hv_lv_separation", "safety")

    def test_isolation_check(self):
        self._assert_check_stub(IsolationCheck(), "safety_isolation", "safety")

    def test_loop_area_check(self):
        self._assert_check_stub(LoopAreaCheck(), "emc_loop_area", "emc")

    def test_net_connectivity_check(self):
        self._assert_check_stub(NetConnectivityCheck(), "erc_net_connectivity", "erc")

    def test_noise_coupling_check(self):
        self._assert_check_stub(NoiseCouplingCheck(), "emc_noise_coupling", "emc")

    def test_power_domain_check(self):
        self._assert_check_stub(PowerDomainCheck(), "erc_power_domain", "erc")

    def test_trace_clearance_check(self):
        self._assert_check_stub(TraceClearanceCheck(), "drc_trace_clearance", "drc")

    def test_via_spacing_check(self):
        self._assert_check_stub(ViaSpacingCheck(), "drc_via_spacing", "drc")

    def test_zone_containment_check(self):
        self._assert_check_stub(ZoneContainmentCheck(), "drc_zone_containment", "drc")

    def test_all_checks_have_nonempty_name(self):
        checks = [
            ClearanceCheck(),
            ComponentOverlapCheck(),
            CourtyardCheck(),
            CreepageCheck(),
            FloatingPinsCheck(),
            GroundPlaneCheck(),
            HVLVSeparationCheck(),
            IsolationCheck(),
            LoopAreaCheck(),
            NetConnectivityCheck(),
            NoiseCouplingCheck(),
            PowerDomainCheck(),
            TraceClearanceCheck(),
            ViaSpacingCheck(),
            ZoneContainmentCheck(),
        ]
        for check in checks:
            assert check.name, f"{type(check).__name__} has empty name"
            assert check.category, f"{type(check).__name__} has empty category"
