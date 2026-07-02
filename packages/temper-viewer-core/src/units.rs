#[derive(Debug, Clone)]
pub struct RulerTicks {
    pub major: Vec<f32>,
    pub minor: Vec<f32>,
}

pub fn compute_ruler_ticks(board_size: f32, major_interval: f32, minor_interval: f32) -> RulerTicks {
    let count = (board_size / minor_interval) as usize + 1;
    let mut major = Vec::with_capacity((board_size / major_interval) as usize + 1);
    let mut minor = Vec::with_capacity(count);
    let steps = (board_size / minor_interval) as usize;
    for i in 0..=steps {
        let pos = i as f32 * minor_interval;
        if (pos / major_interval).fract().abs() < 0.001 || ((pos / major_interval).fract() - 1.0).abs() < 0.001 {
            major.push(pos);
        }
        minor.push(pos);
    }
    if !major.contains(&board_size) {
        major.push(board_size);
    }
    if !minor.contains(&board_size) {
        minor.push(board_size);
    }
    RulerTicks { major, minor }
}

pub fn mm_to_world(mm: f32) -> f32 {
    mm
}

pub fn world_to_mm(world: f32) -> f32 {
    world
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ruler_ticks_for_100mm_board() {
        let ticks = compute_ruler_ticks(100.0, 10.0, 1.0);
        assert_eq!(ticks.major.len(), 11);
        assert!(ticks.major.contains(&0.0));
        assert!(ticks.major.contains(&50.0));
        assert!(ticks.major.contains(&100.0));
        assert_eq!(ticks.minor.len(), 101);
    }

    #[test]
    fn ruler_ticks_for_150mm_board() {
        let ticks = compute_ruler_ticks(150.0, 10.0, 1.0);
        assert_eq!(ticks.major.len(), 16);
        assert!(ticks.major.contains(&0.0));
        assert!(ticks.major.contains(&70.0));
        assert!(ticks.major.contains(&80.0));
        assert!(ticks.major.contains(&150.0));
        assert_eq!(ticks.minor.len(), 151);
    }

    #[test]
    fn ruler_ticks_with_custom_intervals() {
        let ticks = compute_ruler_ticks(50.0, 5.0, 0.5);
        assert!(ticks.major.contains(&0.0));
        assert!(ticks.major.contains(&25.0));
        assert!(ticks.major.contains(&50.0));
    }
}
