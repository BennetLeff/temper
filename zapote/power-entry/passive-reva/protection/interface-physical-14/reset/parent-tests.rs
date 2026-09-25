#[cfg(test)]
mod parent_review {
    use super::*;
    fn running() -> (Boundary, Start) {
        let mut b = Boundary::new();
        let start = arm(&mut b, 0);
        assert!(b.start_at(3, start));
        (b, start)
    }
    #[test]
    fn repeated_low_cannot_postpone_first_deadline() {
        let (mut b, _) = running();
        b.source_ok_at(4, false);
        b.source_ok_at(5, false);
        b.source_ok_at(6, false);
        assert!(!b.output_enabled());
        assert!(b.fault_low_observed);
    }
    #[test]
    fn captured_short_pulse_trips_even_after_source_recovers() {
        let (mut b, _) = running();
        b.source_ok_at(4, false);
        b.source_ok_at(5, true);
        b.advance_to(6);
        assert!(!b.output_enabled());
        assert!(b.fault_low_observed);
    }
    #[test]
    fn invalid_requests_at_deadline_do_not_delay_hardware() {
        for kind in 0..3 {
            let (mut b, start) = running();
            b.source_ok_at(4, false);
            match kind {
                0 => {
                    assert!(!b.request_at(6, start.session, start.intent));
                }
                1 => {
                    assert!(b.fresh_intent_at(6).is_none());
                }
                _ => {
                    assert!(b.install_session_at(6).is_none());
                }
            }
            assert!(
                !b.output_enabled(),
                "request kind {kind} delayed independent inhibit"
            );
            assert!(b.fault_low_observed);
        }
    }
    #[test]
    fn opening_default_low_conductor_trips_even_when_source_stays_high() {
        let (mut b, old) = running();
        b.reset_conductor_at(4, ResetConductor::Open);
        b.advance_to(6);
        assert!(!b.output_enabled());
        assert!(b.fault_low_observed);
        b.reset_conductor_at(7, ResetConductor::Healthy);
        b.advance_to(9);
        assert!(!b.start_at(10, old));
        assert!(!b.output_enabled());
    }
    #[test]
    fn held_await_start_cannot_rearm_after_hardware_recovers() {
        let mut b = Boundary::new();
        let old = arm(&mut b, 0);
        b.source_ok_at(4, false);
        b.advance_to(6);
        b.source_ok_at(7, true);
        b.advance_to(9);
        assert!(!b.start_at(10, old));
        assert!(!b.output_enabled());
        b.decoder_reset_at(11);
        let fresh = arm(&mut b, 12);
        assert_ne!(fresh.session, old.session);
        assert!(b.start_at(15, fresh));
        assert!(b.output_enabled());
    }
}
