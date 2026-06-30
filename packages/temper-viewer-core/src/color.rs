use crate::types::ComponentType;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rgb(pub u8, pub u8, pub u8);

impl Rgb {
    pub const fn new(r: u8, g: u8, b: u8) -> Self {
        Self(r, g, b)
    }

    pub fn as_hex(&self) -> String {
        format!("#{:02x}{:02x}{:02x}", self.0, self.1, self.2)
    }

    pub fn to_f32_array(&self) -> [f32; 3] {
        [self.0 as f32 / 255.0, self.1 as f32 / 255.0, self.2 as f32 / 255.0]
    }
}

pub fn component_color(component_type: ComponentType) -> Rgb {
    match component_type {
        ComponentType::Ic => Rgb(0x33, 0x77, 0xEE),
        ComponentType::Connector => Rgb(0xEE, 0xBB, 0x33),
        ComponentType::Resistor => Rgb(0x33, 0xAA, 0x55),
        ComponentType::Capacitor => Rgb(0xEE, 0x77, 0x33),
        ComponentType::Inductor => Rgb(0x99, 0x55, 0xCC),
        ComponentType::Diode => Rgb(0xDD, 0x44, 0x44),
        ComponentType::Transistor => Rgb(0x33, 0xAA, 0xBB),
        ComponentType::Other => Rgb(0x88, 0x88, 0x88),
    }
}

pub fn layer_color(layer: &str) -> Rgb {
    match layer {
        "F.Cu" => Rgb(0xDD, 0xAA, 0x33),
        "B.Cu" => Rgb(0x33, 0x55, 0xCC),
        "In1.Cu" => Rgb(0xDD, 0x66, 0x44),
        "In2.Cu" => Rgb(0x44, 0xCC, 0x44),
        "F.Silkscreen" => Rgb(0xEE, 0xEE, 0xEE),
        "B.Silkscreen" => Rgb(0xCC, 0xCC, 0xCC),
        "Edge.Cuts" => Rgb(0xFF, 0xFF, 0x66),
        _ => Rgb(0xAA, 0xAA, 0xAA),
    }
}

pub fn status_color(status: &crate::types::ConstraintBinding) -> Rgb {
    match status {
        crate::types::ConstraintBinding::Ok => Rgb(0x33, 0xAA, 0x55),
        crate::types::ConstraintBinding::Warning => Rgb(0xEE, 0xAA, 0x33),
        crate::types::ConstraintBinding::Error => Rgb(0xDD, 0x44, 0x44),
    }
}

pub const BOARD_BACKGROUND: Rgb = Rgb(0x2D, 0x5A, 0x3D);
pub const CANVAS_BACKGROUND: Rgb = Rgb(0xF0, 0xF0, 0xF0);
pub const GRID_DOT: Rgb = Rgb(0x50, 0x80, 0x60);
pub const RULER_TICK: Rgb = Rgb(0x66, 0x66, 0x66);
pub const RATSNEST_LINE: Rgb = Rgb(0x99, 0x99, 0x99);
pub const PIN1_MARKER: Rgb = Rgb(0xFF, 0xFF, 0xFF);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn component_colors_are_distinct() {
        let types = [
            ComponentType::Ic, ComponentType::Connector, ComponentType::Resistor,
            ComponentType::Capacitor, ComponentType::Inductor, ComponentType::Diode,
            ComponentType::Transistor,
        ];
        let colors: Vec<Rgb> = types.iter().map(|t| component_color(*t)).collect();
        let unique: std::collections::HashSet<(u8, u8, u8)> = colors.iter().map(|c| (c.0, c.1, c.2)).collect();
        assert_eq!(unique.len(), types.len(), "Each component type must have a unique color");
    }

    #[test]
    fn layer_colors_match_existing_scheme() {
        assert_eq!(layer_color("F.Cu"), Rgb(0xDD, 0xAA, 0x33));
        assert_eq!(layer_color("B.Cu"), Rgb(0x33, 0x55, 0xCC));
        assert_eq!(layer_color("In1.Cu"), Rgb(0xDD, 0x66, 0x44));
        assert_eq!(layer_color("In2.Cu"), Rgb(0x44, 0xCC, 0x44));
    }

    #[test]
    fn unknown_layer_returns_gray() {
        assert_eq!(layer_color("Unknown.Layer"), Rgb(0xAA, 0xAA, 0xAA));
    }

    #[test]
    fn rgb_to_f32_array_normalizes() {
        let c = Rgb(255, 128, 0);
        let arr = c.to_f32_array();
        assert!((arr[0] - 1.0).abs() < 0.01);
        assert!((arr[1] - 0.502).abs() < 0.01, "got {}", arr[1]);
        assert!((arr[2] - 0.0).abs() < 0.01);
    }
}
