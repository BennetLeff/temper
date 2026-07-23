pub struct BoundaryViolation {
    pub left: f64,
    pub right: f64,
    pub bottom: f64,
    pub top: f64,
}

impl BoundaryViolation {
    pub fn has_violation(&self) -> bool {
        self.left > 0.0 || self.right > 0.0 || self.bottom > 0.0 || self.top > 0.0
    }

    pub fn max_violation(&self) -> f64 {
        self.left
            .max(self.right)
            .max(self.bottom)
            .max(self.top)
    }

    pub fn total_violation(&self) -> f64 {
        self.left + self.right + self.bottom + self.top
    }
}

pub struct ValidBounds {
    pub x_min: f64,
    pub x_max: f64,
    pub y_min: f64,
    pub y_max: f64,
}

impl ValidBounds {
    pub fn clamp_point(&self, x: f64, y: f64) -> (f64, f64) {
        (
            x.clamp(self.x_min, self.x_max),
            y.clamp(self.y_min, self.y_max),
        )
    }

    pub fn contains_point(&self, x: f64, y: f64) -> bool {
        self.x_min <= x && x <= self.x_max && self.y_min <= y && y <= self.y_max
    }
}

pub fn compute_valid_bounds(
    component_half_width: f64,
    component_half_height: f64,
    region_x_min: f64,
    region_y_min: f64,
    region_x_max: f64,
    region_y_max: f64,
    margin: f64,
) -> ValidBounds {
    let x_min = region_x_min + component_half_width + margin;
    let x_max = region_x_max - component_half_width - margin;
    let y_min = region_y_min + component_half_height + margin;
    let y_max = region_y_max - component_half_height - margin;

    let (x_min, x_max) = if x_min > x_max {
        let center = (region_x_min + region_x_max) / 2.0;
        (center, center)
    } else {
        (x_min, x_max)
    };

    let (y_min, y_max) = if y_min > y_max {
        let center = (region_y_min + region_y_max) / 2.0;
        (center, center)
    } else {
        (y_min, y_max)
    };

    ValidBounds {
        x_min,
        x_max,
        y_min,
        y_max,
    }
}

#[allow(clippy::too_many_arguments)]
pub fn compute_boundary_violation(
    position_x: f64,
    position_y: f64,
    component_half_width: f64,
    component_half_height: f64,
    board_x_min: f64,
    board_y_min: f64,
    board_x_max: f64,
    board_y_max: f64,
) -> BoundaryViolation {
    let comp_x_min = position_x - component_half_width;
    let comp_x_max = position_x + component_half_width;
    let comp_y_min = position_y - component_half_height;
    let comp_y_max = position_y + component_half_height;

    let left = (board_x_min - comp_x_min).max(0.0);
    let right = (comp_x_max - board_x_max).max(0.0);
    let bottom = (board_y_min - comp_y_min).max(0.0);
    let top = (comp_y_max - board_y_max).max(0.0);

    BoundaryViolation {
        left,
        right,
        bottom,
        top,
    }
}

#[allow(clippy::too_many_arguments)]
pub fn is_within_bounds(
    position_x: f64,
    position_y: f64,
    component_half_width: f64,
    component_half_height: f64,
    region_x_min: f64,
    region_y_min: f64,
    region_x_max: f64,
    region_y_max: f64,
    tolerance: f64,
) -> bool {
    let comp_x_min = position_x - component_half_width;
    let comp_x_max = position_x + component_half_width;
    let comp_y_min = position_y - component_half_height;
    let comp_y_max = position_y + component_half_height;

    comp_x_min >= region_x_min - tolerance
        && comp_x_max <= region_x_max + tolerance
        && comp_y_min >= region_y_min - tolerance
        && comp_y_max <= region_y_max + tolerance
}

pub fn compute_zone_distance(
    position_x: f64,
    position_y: f64,
    zone_x_min: f64,
    zone_y_min: f64,
    zone_x_max: f64,
    zone_y_max: f64,
) -> f64 {
    let clamped_x = if position_x < zone_x_min {
        zone_x_min
    } else if position_x > zone_x_max {
        zone_x_max
    } else {
        position_x
    };
    let clamped_y = if position_y < zone_y_min {
        zone_y_min
    } else if position_y > zone_y_max {
        zone_y_max
    } else {
        position_y
    };

    let dx = position_x - clamped_x;
    let dy = position_y - clamped_y;

    if clamped_x == position_x && clamped_y == position_y {
        let dist_to_left = position_x - zone_x_min;
        let dist_to_right = zone_x_max - position_x;
        let dist_to_bottom = position_y - zone_y_min;
        let dist_to_top = zone_y_max - position_y;
        -dist_to_left
            .min(dist_to_right)
            .min(dist_to_bottom)
            .min(dist_to_top)
    } else {
        (dx * dx + dy * dy).sqrt()
    }
}

pub fn point_in_zone(
    position_x: f64,
    position_y: f64,
    zone_x_min: f64,
    zone_y_min: f64,
    zone_x_max: f64,
    zone_y_max: f64,
) -> bool {
    zone_x_min <= position_x
        && position_x <= zone_x_max
        && zone_y_min <= position_y
        && position_y <= zone_y_max
}
