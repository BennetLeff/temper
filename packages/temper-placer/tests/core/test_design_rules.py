"""Tests for design rules module."""


from temper_placer.core.design_rules import (
    SAFETY_CONSTANT_AUTHORITY,
    SAFETY_CONSTANT_AUTHORITY_FIELDS,
    SAFETY_CONSTANT_AUTHORITY_NET_CLASSES,
    TEMPER_NET_CLASSES,
    DesignRules,
    NetClassRules,
    create_temper_design_rules,
)


class TestNetClassRules:
    """Tests for NetClassRules Pydantic model."""

    def test_create_basic_rules(self):
        """Test creating basic net class rules."""
        rules = NetClassRules(
            name="Signal",
            trace_width=0.2,
            clearance=0.15,
            dru_priority=100,
        )
        assert rules.name == "Signal"
        assert rules.trace_width == 0.2
        assert rules.clearance == 0.15
        assert rules.via_diameter == 0.6
        assert rules.via_drill == 0.3
        assert rules.target_impedance is None

    def test_create_controlled_impedance_rules(self):
        """Test creating rules with target impedance."""
        rules = NetClassRules(
            name="HighSpeed",
            trace_width=0.15,
            clearance=0.2,
            target_impedance=50.0,
            dru_priority=100,
        )
        assert rules.target_impedance == 50.0

    def test_create_high_current_rules(self):
        """Test creating rules for high-current traces."""
        rules = NetClassRules(
            name="HighCurrent",
            trace_width=2.0,
            clearance=0.5,
            via_diameter=1.2,
            via_drill=0.6,
            dru_priority=100,
        )
        assert rules.trace_width == 2.0
        assert rules.via_diameter == 1.2


class TestDesignRules:
    """Tests for DesignRules dataclass."""

    def test_default_rules(self):
        """Test default design rules."""
        rules = DesignRules()
        assert rules.default_trace_width == 0.2
        assert rules.default_clearance == 0.2
        assert rules.default_via_diameter == 0.6
        assert rules.default_via_drill == 0.3

    def test_get_rules_for_unknown_net(self):
        """Test that unknown nets get default rules."""
        design_rules = DesignRules()
        rules = design_rules.get_rules_for_net("UNKNOWN_NET")
        assert rules.name == "Default"
        assert rules.trace_width == design_rules.default_trace_width
        assert rules.clearance == design_rules.default_clearance

    def test_get_rules_for_net_class(self):
        """Test getting rules by net class."""
        power_class = NetClassRules(
            name="Power",
            trace_width=1.0,
            clearance=0.5,
            dru_priority=100,
        )
        design_rules = DesignRules(net_classes={"Power": power_class})
        rules = design_rules.get_rules_for_net("NET1", net_class="Power")
        assert rules.name == "Power"
        assert rules.trace_width == 1.0
        assert rules.clearance == 0.5

    def test_net_override_takes_priority(self):
        """Test that per-net overrides take priority over net class."""
        power_class = NetClassRules(
            name="Power",
            trace_width=1.0,
            clearance=0.5,
            dru_priority=100,
        )
        vcc_override = NetClassRules(
            name="VCC_Special",
            trace_width=1.5,
            clearance=0.6,
            dru_priority=100,
        )
        design_rules = DesignRules(
            net_classes={"Power": power_class},
            net_overrides={"VCC": vcc_override},
        )
        rules = design_rules.get_rules_for_net("VCC", net_class="Power")
        assert rules.name == "VCC_Special"
        assert rules.trace_width == 1.5
        assert rules.clearance == 0.6

    def test_power_net_pattern_recognition(self):
        """Test automatic detection of power net patterns."""
        design_rules = create_temper_design_rules()
        vcc_rules = design_rules.get_rules_for_net("VCC")
        assert vcc_rules.name == "Power"
        assert vcc_rules.trace_width == 0.5

    def test_ground_net_pattern_recognition(self):
        """Test automatic detection of ground net patterns."""
        design_rules = create_temper_design_rules()
        gnd_rules = design_rules.get_rules_for_net("GND")
        assert gnd_rules.name == "GND"
        assert gnd_rules.trace_width == 1.0


class TestTemperNetClasses:
    """Tests for Temper-specific net class definitions."""

    def test_all_expected_classes_defined(self):
        """Test that all 9 expected net classes are defined."""
        expected = [
            "ACMains", "HighVoltage", "FinePitch", "Power", "GateDrive",
            "GND", "HighSpeed", "Signal", "HighCurrent",
        ]
        for name in expected:
            assert name in TEMPER_NET_CLASSES

    def test_power_class_parameters(self):
        """Test Power class has appropriate parameters."""
        power = TEMPER_NET_CLASSES["Power"]
        assert power.trace_width == 0.5
        assert power.clearance == 0.25
        assert power.via_diameter == 0.8
        assert power.via_drill == 0.4

    def test_high_speed_class_has_impedance(self):
        """Test HighSpeed class has target impedance."""
        high_speed = TEMPER_NET_CLASSES["HighSpeed"]
        assert high_speed.target_impedance == 50.0
        assert high_speed.trace_width == 0.15

    def test_high_current_class_parameters(self):
        """Test HighCurrent class has wide traces."""
        high_current = TEMPER_NET_CLASSES["HighCurrent"]
        assert high_current.trace_width == 0.5
        assert high_current.via_diameter == 0.8


class TestCreateTemperDesignRules:
    """Tests for create_temper_design_rules factory function."""

    def test_creates_valid_rules(self):
        """Test that factory creates valid design rules."""
        rules = create_temper_design_rules()
        assert isinstance(rules, DesignRules)
        assert len(rules.net_classes) == 9

    def test_rules_are_independent(self):
        """Test that factory creates independent instances."""
        rules1 = create_temper_design_rules()
        rules2 = create_temper_design_rules()
        assert rules2.net_classes["Power"].trace_width == 0.5

    def test_can_add_custom_overrides(self):
        """Test that custom overrides can be added."""
        rules = create_temper_design_rules()
        rules.net_overrides["CRITICAL_SIGNAL"] = NetClassRules(
            name="Critical",
            trace_width=0.5,
            clearance=0.3,
            dru_priority=100,
        )
        critical = rules.get_rules_for_net("CRITICAL_SIGNAL")
        assert critical.name == "Critical"
        assert critical.trace_width == 0.5



class TestSafetyConstantAuthority:
    """Tests for SAFETY_CONSTANT_AUTHORITY (U1 - SSOT authority record)."""

    def test_import_succeeds(self):
        assert SAFETY_CONSTANT_AUTHORITY is not None

    def test_contains_exactly_four_triples(self):
        assert len(SAFETY_CONSTANT_AUTHORITY) == 4

    def test_authority_set_contents(self):
        expected = {
            ("ACMains", "clearance", 6.0),
            ("ACMains", "creepage_mm", 6.0),
            ("HighVoltage", "clearance", 6.0),
            ("HighVoltage", "creepage_mm", 6.0),
        }
        assert set(SAFETY_CONSTANT_AUTHORITY) == expected

    def test_derives_from_temper_net_classes(self):
        from temper_placer.core.design_rules import (
            TEMPER_NET_CLASSES,
        )
        old = TEMPER_NET_CLASSES["ACMains"].clearance
        try:
            object.__setattr__(TEMPER_NET_CLASSES["ACMains"], "clearance", 6.5)
            authority = tuple(
                (nc_name, field_name, float(getattr(nc, field_name)))
                for nc_name, nc in TEMPER_NET_CLASSES.items()
                if nc_name in SAFETY_CONSTANT_AUTHORITY_NET_CLASSES
                for field_name in SAFETY_CONSTANT_AUTHORITY_FIELDS
            )
            assert ("ACMains", "clearance", 6.5) in authority
        finally:
            object.__setattr__(TEMPER_NET_CLASSES["ACMains"], "clearance", old)

    def test_non_safety_class_excluded(self):
        values = {(nc, field) for (nc, field, _) in SAFETY_CONSTANT_AUTHORITY}
        assert ("FinePitch", "clearance") not in values
        assert ("Signal", "clearance") not in values

    def test_non_safety_field_excluded(self):
        values = {(nc, field) for (nc, field, _) in SAFETY_CONSTANT_AUTHORITY}
        assert ("ACMains", "trace_width") not in values
        assert ("HighVoltage", "via_diameter") not in values

    def test_net_class_frozenset_correct(self):
        assert frozenset({"ACMains", "HighVoltage"}) == SAFETY_CONSTANT_AUTHORITY_NET_CLASSES

    def test_field_frozenset_correct(self):
        assert frozenset({"clearance", "creepage_mm"}) == SAFETY_CONSTANT_AUTHORITY_FIELDS
