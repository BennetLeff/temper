use temper_geometry::congestion_tensor::CongestionTensor;

fn python_cost(max_cost: f32, usage: f32) -> f32 {
    if usage <= 0.0 { 1.0 }
    else {
        let raw = 1.0_f32 + usage.ln_1p();
        if raw > max_cost { max_cost } else { raw }
    }
}

#[test]
fn tdd_new_allocates_flat_zeroed_vec() {
    let ct = CongestionTensor::new(3, 5, 100.0, 1.0);
    for r in 0..3 { for c in 0..5 { assert_eq!(ct.cost(r, c), 1.0); } }
}

#[test]
fn tdd_increment_matches_python() {
    let mut ct = CongestionTensor::new(2, 2, 100.0, 1.0);
    ct.increment(0, 0, 3.0);
    let expected = python_cost(100.0, 3.0);
    assert!((ct.cost(0, 0) - expected).abs() < 1e-5);
}

#[test]
fn tdd_cost_respects_cap() {
    // Need raw > e^49 ≈ 1.9e21 to exceed cap of 50. Use f32::MAX.
    let mut ct = CongestionTensor::new(1, 2, 50.0, 1.0);
    ct.increment(0, 0, f32::MAX);
    assert_eq!(ct.cost(0, 0), 50.0);
}

#[test]
fn tdd_reset_matches_python() {
    let mut ct = CongestionTensor::new(2, 2, 100.0, 1.0);
    ct.increment(0, 0, 5.0);
    ct.reset();
    for r in 0..2 { for c in 0..2 { assert_eq!(ct.cost(r, c), 1.0); } }
}

// PBT properties (5 required by plan)
#[test]
fn pbt_cost_always_at_least_one() {
    for usage in [0.0_f32, 1.0, 10.0, 100.0, 1000.0, f32::MAX] {
        let mut ct = CongestionTensor::new(1, 2, 1000.0, 1.0);
        ct.increment(0, 0, usage);
        assert!(ct.cost(0, 0) >= 1.0, "cost({}) = {} < 1.0", usage, ct.cost(0, 0));
    }
}

#[test]
fn pbt_cost_monotonically_increasing() {
    let mut ct = CongestionTensor::new(1, 1, 100.0, 1.0);
    let mut prev = ct.cost(0, 0);
    for w in [0.1_f32, 1.0, 10.0, 100.0] {
        ct.increment(0, 0, w);
        let curr = ct.cost(0, 0);
        assert!(curr >= prev, "cost decreased: {} -> {}", prev, curr);
        prev = curr;
    }
}

#[test]
fn pbt_decay_one_is_identity() {
    let mut ct = CongestionTensor::new(1, 1, 100.0, 1.0);
    ct.increment(0, 0, 5.0);
    let before = ct.cost(0, 0);
    ct.decay(1.0);
    assert_eq!(ct.cost(0, 0), before);
}

#[test]
fn pbt_cost_scales_with_weight() {
    let mut ct1 = CongestionTensor::new(1, 1, 100.0, 1.0);
    let mut ct2 = CongestionTensor::new(1, 1, 100.0, 1.0);
    ct1.increment(0, 0, 5.0);
    ct2.increment(0, 0, 10.0);
    assert!(ct2.cost(0, 0) >= ct1.cost(0, 0));
}

#[test]
fn pbt_reset_all_zeros() {
    let mut ct = CongestionTensor::new(4, 4, 100.0, 1.0);
    for r in 0..4 { for c in 0..4 { ct.increment(r, c, (r * c + 1) as f32); } }
    ct.reset();
    for r in 0..4 { for c in 0..4 { assert_eq!(ct.cost(r, c), 1.0); } }
}
