// Append to command/handshake.rs for independent private-state adversarial checks.
#[cfg(test)] mod parent_review {
    use super::*;
    fn at_phase(phase: u8) -> (Receiver, Frame, Frame) {
        let mut r = Receiver::new(PersistentCounter::new(1));
        r.boot().unwrap();
        let session = r.session.unwrap();
        let request = Frame::Request { session, intent: 1 };
        let start = Frame::Start { session, intent: 1 };
        if phase >= 1 { r.idle_sample(true,true); r.idle_sample(true,true); }
        if phase >= 2 { r.on_frame(request,true,true).unwrap(); }
        if phase >= 3 { r.on_frame(start,true,true).unwrap(); }
        (r,request,start)
    }
    #[test] fn every_actual_loss_path_invalidates_every_phase() {
        for phase in 0..4 { for fault in 0..4 {
            let (mut r,request,start)=at_phase(phase);
            match fault {
                0 => { let _=r.on_frame(start,false,true); },
                1 => r.idle_sample(false,true),
                2 => { let _=r.on_frame(start,true,false); },
                _ => r.idle_sample(true,false),
            }
            assert!(!r.running(),"phase {phase} fault {fault}");
            assert!(r.session.is_none(),"old session retained phase {phase} fault {fault}");
            r.idle_sample(true,true);r.idle_sample(true,true);
            assert!(r.on_frame(request,true,true).is_err());
            assert!(r.on_frame(start,true,true).is_err());
            r.boot().unwrap();r.idle_sample(true,true);r.idle_sample(true,true);
            assert_eq!(r.on_frame(request,true,true),Err(Reject::StaleSession));
            assert_eq!(r.on_frame(start,true,true),Err(Reject::StaleSession));
            assert!(!r.running());
        }}
    }
    #[test] fn duplicate_request_cannot_extend_exact_deadline() {
        let (mut r,request,start)=at_phase(2);
        for _ in 0..HANDSHAKE_TICKS { let _=r.on_frame(request,true,true);let _=r.tick(); }
        assert!(r.session.is_none(),"deadline must expire on bound, not next tick");
        assert!(r.on_frame(start,true,true).is_err());assert!(!r.running());
    }
    #[test] fn new_challenge_cannot_reuse_old_local_intent() {
        let mut r=Receiver::new(PersistentCounter::new(1));
        let old=r.boot().unwrap(); let mut s=Source::new();
        assert!(!s.fresh_start_intent());s.on_challenge(old);assert!(s.fresh_start_intent());
        let request=s.request_after_intent().unwrap();
        let new=r.boot().unwrap();s.on_challenge(new);
        r.idle_sample(true,true);r.idle_sample(true,true);
        assert_eq!(r.on_frame(request,true,true),Err(Reject::StaleSession));
        assert!(!r.running());
    }
    #[test] fn persisted_counter_survives_receiver_object_replacement() {
        let (r,request,start)=at_phase(3);
        let mut replacement=Receiver::new(r.counter);
        replacement.boot().unwrap();replacement.idle_sample(true,true);replacement.idle_sample(true,true);
        assert_eq!(replacement.on_frame(request,true,true),Err(Reject::StaleSession));
        assert_eq!(replacement.on_frame(start,true,true),Err(Reject::StaleSession));
        assert!(!replacement.running());
    }
}

// Positive witness of a physical-boundary limitation, not a safety acceptance.
#[cfg(test)] mod parent_boundary_witness {
    use super::*;
    #[test] fn source_reset_cannot_recall_start_before_receiver_detects_it() {
        let mut r=Receiver::new(PersistentCounter::new(1));
        let challenge=r.boot().unwrap();r.idle_sample(true,true);r.idle_sample(true,true);
        let mut s=Source::new();s.on_challenge(challenge);assert!(s.fresh_start_intent());
        let req=s.request_after_intent().unwrap();
        let ack=r.on_frame(req,true,true).unwrap().unwrap();let start=s.on_ack(ack).unwrap();
        s.reset();
        r.on_frame(start,true,true).unwrap();
        assert!(r.running(),"in-flight START remains valid until receiver observes fault or expiry");
        r.link_fault();assert!(!r.running());assert!(r.session.is_none());
    }
}
