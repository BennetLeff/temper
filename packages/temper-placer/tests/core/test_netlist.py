"""Tests for core.netlist module."""


from temper_placer.core.netlist import Component, Net, Netlist, Pin


class TestPin:
    """Tests for Pin dataclass."""

    def test_basic_pin(self):
        """Test basic pin creation."""
        pin = Pin("VCC", "1", (0.5, 0.5), net="VCC")
        assert pin.name == "VCC"
        assert pin.number == "1"
        assert pin.position == (0.5, 0.5)
        assert pin.net == "VCC"

    def test_unconnected_pin(self):
        """Test pin with no net connection."""
        pin = Pin("NC", "99", (0.0, 0.0))
        assert pin.net is None


class TestComponent:
    """Tests for Component dataclass."""

    def test_basic_component(self, simple_components):
        """Test basic component properties."""
        u1 = simple_components[0]
        assert u1.ref == "U1"
        assert u1.footprint == "SOIC-8"
        assert u1.width == 5.0
        assert u1.height == 4.0
        assert len(u1.pins) == 4

    def test_get_pin_by_name(self, simple_components):
        """Test getting pin by name."""
        u1 = simple_components[0]
        vcc_pin = u1.get_pin("VCC")
        assert vcc_pin is not None
        assert vcc_pin.number == "8"

    def test_get_pin_by_number(self, simple_components):
        """Test getting pin by number."""
        u1 = simple_components[0]
        pin1 = u1.get_pin("1")
        assert pin1 is not None
        assert pin1.name == "IN"

    def test_get_nonexistent_pin(self, simple_components):
        """Test getting nonexistent pin returns None."""
        u1 = simple_components[0]
        assert u1.get_pin("NONEXISTENT") is None

    def test_get_pins_for_net(self, simple_components):
        """Test getting all pins for a net."""
        u1 = simple_components[0]
        vcc_pins = u1.get_pins_for_net("VCC")
        assert len(vcc_pins) == 1
        assert vcc_pins[0].name == "VCC"


class TestNet:
    """Tests for Net dataclass."""

    def test_basic_net(self, simple_nets):
        """Test basic net properties."""
        vcc = simple_nets[0]
        assert vcc.name == "VCC"
        assert vcc.pin_count == 2
        assert vcc.net_class == "Power"
        assert vcc.weight == 1.0

    def test_get_component_refs(self, simple_nets):
        """Test getting unique component refs from net."""
        vcc = simple_nets[0]
        refs = vcc.get_component_refs()
        assert refs == {"U1", "C1"}


class TestNetlist:
    """Tests for Netlist dataclass."""

    def test_basic_netlist(self, simple_netlist):
        """Test basic netlist properties."""
        assert simple_netlist.n_components == 3
        assert simple_netlist.n_nets == 5

    def test_get_component_index(self, simple_netlist):
        """Test getting component index by ref."""
        assert simple_netlist.get_component_index("U1") == 0
        assert simple_netlist.get_component_index("R1") == 1
        assert simple_netlist.get_component_index("C1") == 2

    def test_get_component(self, simple_netlist):
        """Test getting component by ref."""
        u1 = simple_netlist.get_component("U1")
        assert u1.ref == "U1"
        assert u1.footprint == "SOIC-8"

    def test_get_net(self, simple_netlist):
        """Test getting net by name."""
        vcc = simple_netlist.get_net("VCC")
        assert vcc.name == "VCC"
        assert vcc.pin_count == 2

    def test_get_component_nets(self, simple_netlist):
        """Test getting nets connected to a component."""
        u1_nets = simple_netlist.get_component_nets("U1")
        assert set(u1_nets) == {"VCC", "GND", "SIG_IN", "SIG_OUT"}

    def test_get_net_pins(self, simple_netlist):
        """Test getting pins for a net."""
        vcc_pins = simple_netlist.get_net_pins("VCC")
        assert len(vcc_pins) == 2
        assert ("U1", "VCC") in vcc_pins
        assert ("C1", "1") in vcc_pins

    def test_get_bounds_array(self, simple_netlist):
        """Test getting bounds as JAX array."""
        bounds = simple_netlist.get_bounds_array()
        assert bounds.shape == (3, 2)
        assert bounds[0, 0] == 5.0  # U1 width
        assert bounds[0, 1] == 4.0  # U1 height

    def test_get_fixed_mask(self, simple_netlist):
        """Test getting fixed component mask."""
        mask = simple_netlist.get_fixed_mask()
        assert mask.shape == (3,)
        assert not any(mask)  # None are fixed in simple_netlist

    def test_validate_valid_netlist(self, simple_netlist):
        """Test validation of valid netlist."""
        errors = simple_netlist.validate()
        assert len(errors) == 0

    def test_validate_duplicate_refs(self):
        """Test validation catches duplicate refs."""
        components = [
            Component("U1", "SOIC-8", (5.0, 4.0)),
            Component("U1", "SOIC-8", (5.0, 4.0)),  # Duplicate!
        ]
        netlist = Netlist(components=components, nets=[])
        errors = netlist.validate()
        assert len(errors) > 0
        assert "Duplicate component refs" in errors[0]

    def test_validate_invalid_net_reference(self):
        """Test validation catches invalid component refs in nets."""
        components = [Component("U1", "SOIC-8", (5.0, 4.0))]
        nets = [Net("NET1", [("U99", "1")])]  # U99 doesn't exist
        netlist = Netlist(components=components, nets=nets)
        errors = netlist.validate()
        assert len(errors) > 0
        assert "unknown component" in errors[0]
