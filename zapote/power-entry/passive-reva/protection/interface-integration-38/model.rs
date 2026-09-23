//! Logical Rev38 source/receiver and retained-hardware model.
//!
//! Events enter after decoding and electrical qualification. This is an
//! ordering oracle, not a UART, EEPROM, latch-timing, isolator or analog model.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    Lockout,
    Preparing,
    Ready,
    StartPending,
    Running,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Reject {
    NotDisarmed,
    BadState,
    WrongSession,
    WrongIntent,
    Expired,
    HardwareInvalid,
    NoFreshPress,
    SourceReset,
    StorageFault,
    NoProgress,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InterruptedReservation {
    BeforeCommit,
    AfterCommit,
    Corrupt,
}

#[derive(Debug)]
pub struct Model {
    state: State,
    highwater: u64,
    storage_fault: bool,
    session: Option<u64>,
    intent: Option<u32>,
    start_deadline: Option<u64>,
    start_window: u64,
    prepare_deadline: Option<u64>,
    prepare_window: u64,
    now: u64,
    source_q: bool,
    physical_permit: bool,
    source_seen_high: bool,
    hot_seen_high: bool,
    session_q: bool,
    run_q: bool,
    abort_n: bool,
    rails_good: bool,
    external_fault: bool,
    prep_abort: bool,
    disarm_seen_after_trip: bool,
    disarm_acknowledged: bool,
    revalidate_level: bool,
    revalidate_consumed: bool,
    button_released: bool,
    fresh_press: bool,
    source_alive: bool,
    reset_lockout: bool,
    committed_start: Option<(u64, u32)>,
    source_wdi_last: u64,
    source_watchdog_window: u64,
    local_progress: u64,
    local_progress_fed: u64,
    link_sequence: u64,
    link_sequence_fed: u64,
}

impl Model {
    pub fn new(
        highwater: u64,
        prepare_window: u64,
        start_window: u64,
        source_watchdog_window: u64,
    ) -> Self {
        assert!(prepare_window > 0 && start_window > 0 && source_watchdog_window > 0);
        Self {
            state: State::Lockout,
            highwater,
            storage_fault: false,
            session: None,
            intent: None,
            start_deadline: None,
            start_window,
            prepare_deadline: None,
            prepare_window,
            now: 0,
            source_q: false,
            physical_permit: false,
            source_seen_high: false,
            hot_seen_high: false,
            session_q: false,
            run_q: false,
            abort_n: false,
            rails_good: true,
            external_fault: false,
            prep_abort: false,
            disarm_seen_after_trip: false,
            disarm_acknowledged: false,
            revalidate_level: false,
            revalidate_consumed: false,
            button_released: false,
            fresh_press: false,
            source_alive: true,
            reset_lockout: false,
            committed_start: None,
            source_wdi_last: 0,
            source_watchdog_window,
            local_progress: 0,
            local_progress_fed: 0,
            link_sequence: 0,
            link_sequence_fed: 0,
        }
    }

    pub fn state(&self) -> State {
        self.state
    }
    pub fn highwater(&self) -> u64 {
        self.highwater
    }
    pub fn session_ok(&self) -> bool {
        self.session_q
    }
    pub fn running(&self) -> bool {
        self.run_q
    }
    pub fn source_permit(&self) -> bool {
        self.source_q
    }
    pub fn abort_asserted(&self) -> bool {
        !self.abort_n
    }
    pub fn preparation_aborted(&self) -> bool {
        self.prep_abort
    }
    pub fn source_wdi_last(&self) -> u64 {
        self.source_wdi_last
    }

    fn invalidate(&mut self) {
        self.state = State::Lockout;
        self.session = None;
        self.intent = None;
        self.start_deadline = None;
        self.prepare_deadline = None;
        self.source_q = false;
        self.physical_permit = false;
        self.session_q = false;
        self.run_q = false;
        self.abort_n = false;
        self.fresh_press = false;
        self.button_released = false;
        self.committed_start = None;
        self.disarm_seen_after_trip = false;
        self.disarm_acknowledged = false;
        // Seen-high bits remain until controlled preparation. A brief wire
        // recovery therefore cannot remove the remembered loss condition.
    }

    pub fn at(&mut self, now: u64) {
        assert!(now >= self.now);
        self.now = now;
        if self
            .prepare_deadline
            .is_some_and(|deadline| now >= deadline)
            || self.start_deadline.is_some_and(|deadline| now >= deadline)
        {
            self.invalidate();
        }
        if self.state != State::Lockout
            && now.saturating_sub(self.source_wdi_last) >= self.source_watchdog_window
        {
            self.invalidate();
        }
    }

    /// A write interrupted before publication either leaves the old maximum,
    /// advances it without a challenge, or makes the store unusable.
    pub fn interrupt_reservation(&mut self, phase: InterruptedReservation) {
        assert_eq!(self.state, State::Lockout);
        match phase {
            InterruptedReservation::BeforeCommit => {}
            InterruptedReservation::AfterCommit => {
                if let Some(next) = self.highwater.checked_add(1) {
                    self.highwater = next;
                } else {
                    self.storage_fault = true;
                }
            }
            InterruptedReservation::Corrupt => self.storage_fault = true,
        }
    }

    /// Publication follows durable reservation. Both PERMIT nodes must have
    /// been observed low after the preceding invalidation.
    pub fn reserve_session(&mut self) -> Result<u64, Reject> {
        if self.storage_fault || self.highwater == u64::MAX {
            return Err(Reject::StorageFault);
        }
        if self.state != State::Lockout {
            return Err(Reject::BadState);
        }
        if self.source_q
            || self.physical_permit
            || !self.disarm_seen_after_trip
            || !self.disarm_acknowledged
            || self.reset_lockout
        {
            return Err(Reject::NotDisarmed);
        }
        if !self.rails_good || self.external_fault {
            return Err(Reject::HardwareInvalid);
        }
        let deadline = self
            .now
            .checked_add(self.prepare_window)
            .ok_or(Reject::Expired)?;
        let id = self.highwater + 1;
        self.highwater = id;
        self.session = Some(id);
        self.state = State::Preparing;
        self.prepare_deadline = Some(deadline);
        self.prep_abort = false;
        self.revalidate_consumed = false;
        self.source_seen_high = false;
        self.hot_seen_high = false;
        self.local_progress_fed = self.local_progress;
        self.link_sequence = 0;
        self.link_sequence_fed = 0;
        Ok(id)
    }

    pub fn disarm_ack(&mut self, id: u64) -> Result<(), Reject> {
        if self.state != State::Preparing {
            return Err(Reject::BadState);
        }
        if self.session != Some(id) {
            return Err(Reject::WrongSession);
        }
        if self.prep_abort
            || self.source_q
            || self.physical_permit
            || !self.disarm_seen_after_trip
            || self.external_fault
            || !self.rails_good
        {
            return Err(Reject::HardwareInvalid);
        }
        self.abort_n = true;
        Ok(())
    }

    /// Only a new low-to-high request while eligible can issue a one-shot
    /// clock. Holding it through a fault or recovery creates no new edge.
    pub fn revalidation_level(&mut self, high: bool) {
        let edge = high && !self.revalidate_level;
        self.revalidate_level = high;
        if !edge
            || self.revalidate_consumed
            || self.state != State::Preparing
            || !self.abort_n
            || self.prep_abort
            || self.external_fault
            || !self.rails_good
            || self.physical_permit
        {
            return;
        }
        self.revalidate_consumed = true;
        self.session_q = true;
        self.state = State::Ready;
        self.prepare_deadline = None;
    }

    pub fn button_release(&mut self) {
        if self.state == State::Ready && self.source_alive {
            self.button_released = true;
        }
    }

    pub fn button_press(&mut self) -> Result<(), Reject> {
        if self.state != State::Ready || !self.source_alive {
            return Err(Reject::BadState);
        }
        if !self.button_released {
            return Err(Reject::NoFreshPress);
        }
        self.fresh_press = true;
        self.button_released = false;
        Ok(())
    }

    pub fn raise_permit(&mut self) -> Result<(), Reject> {
        if self.state != State::Ready
            || !self.fresh_press
            || !self.source_alive
            || !self.session_q
            || !self.rails_good
            || self.external_fault
            || !self.abort_n
        {
            return Err(Reject::HardwareInvalid);
        }
        self.source_q = true;
        self.physical_permit = true;
        self.source_seen_high = true;
        self.hot_seen_high = true;
        Ok(())
    }

    pub fn request(&mut self, id: u64, intent: u32) -> Result<(), Reject> {
        if self.state != State::Ready {
            return Err(Reject::BadState);
        }
        if self.session != Some(id) {
            return Err(Reject::WrongSession);
        }
        if !self.fresh_press
            || !self.source_alive
            || !self.physical_permit
            || !self.source_q
            || !self.session_q
            || !self.abort_n
            || self.external_fault
            || !self.rails_good
        {
            return Err(Reject::HardwareInvalid);
        }
        let deadline = self
            .now
            .checked_add(self.start_window)
            .ok_or(Reject::Expired)?;
        self.intent = Some(intent);
        self.start_deadline = Some(deadline);
        self.state = State::StartPending;
        self.fresh_press = false;
        Ok(())
    }

    /// Called only once the source has committed the frame to transmission.
    pub fn commit_start(&mut self, id: u64, intent: u32) -> Result<(), Reject> {
        if !self.source_alive || self.reset_lockout {
            return Err(Reject::SourceReset);
        }
        if self.state != State::StartPending {
            return Err(Reject::BadState);
        }
        if self.session != Some(id) {
            return Err(Reject::WrongSession);
        }
        if self.intent != Some(intent) {
            return Err(Reject::WrongIntent);
        }
        if self.committed_start.is_some() {
            return Err(Reject::BadState);
        }
        self.committed_start = Some((id, intent));
        Ok(())
    }

    /// Represents the single physical RUN-set boundary, after a fresh sample
    /// of independent hardware conditions and the fixed receiver deadline.
    pub fn deliver_start(&mut self, id: u64, intent: u32) -> Result<(), Reject> {
        if self.state != State::StartPending {
            return Err(Reject::BadState);
        }
        if self.session != Some(id) {
            return Err(Reject::WrongSession);
        }
        if self.intent != Some(intent) || self.committed_start != Some((id, intent)) {
            return Err(Reject::WrongIntent);
        }
        if self
            .start_deadline
            .is_none_or(|deadline| self.now >= deadline)
        {
            self.invalidate();
            return Err(Reject::Expired);
        }
        if !self.source_q
            || !self.physical_permit
            || !self.session_q
            || !self.abort_n
            || self.external_fault
            || !self.rails_good
        {
            self.invalidate();
            return Err(Reject::HardwareInvalid);
        }
        self.committed_start = None;
        self.start_deadline = None;
        self.run_q = true;
        self.state = State::Running;
        Ok(())
    }

    pub fn physical_permit(&mut self, high: bool) {
        self.physical_permit = high;
        if high {
            self.hot_seen_high = true;
        } else if self.hot_seen_high || self.source_seen_high {
            self.invalidate();
        }
    }

    pub fn source_readback(&mut self, high: bool) {
        if high {
            self.source_seen_high = true;
        } else if self.source_seen_high {
            self.invalidate();
        }
    }

    pub fn external_trip(&mut self) {
        self.external_fault = true;
        if self.state == State::Preparing {
            self.prep_abort = true;
        }
        self.invalidate();
    }

    pub fn clear_external_fault(&mut self) {
        self.external_fault = false;
    }
    pub fn stop(&mut self) {
        self.invalidate();
    }
    pub fn receiver_reset(&mut self) {
        self.invalidate();
    }

    pub fn rail_good(&mut self, good: bool) {
        self.rails_good = good;
        if !good {
            self.invalidate();
        }
    }

    /// CPU-only reset does not magically alter retained GPIO or HOT state.
    /// A frame already committed above remains in the transport.
    pub fn unexpected_source_reset(&mut self) {
        self.source_alive = false;
        self.reset_lockout = true;
        self.fresh_press = false;
        self.button_released = false;
    }

    /// Boot does not service WDI or resend a START. Physical disarm must
    /// occur before a fresh session and feed service are possible.
    pub fn source_boot(&mut self) {
        self.source_alive = true;
        self.disarm_seen_after_trip = false;
        self.disarm_acknowledged = false;
    }

    pub fn local_safety_cycle(&mut self) {
        self.local_progress = self.local_progress.saturating_add(1);
    }

    pub fn fresh_link_exchange(&mut self, sequence: u64) {
        if sequence > self.link_sequence {
            self.link_sequence = sequence;
        }
    }

    pub fn feed_source_wdi(&mut self) -> Result<(), Reject> {
        if !self.source_alive || self.reset_lockout {
            return Err(Reject::SourceReset);
        }
        if self.local_progress == self.local_progress_fed
            || (self.state != State::Lockout && self.link_sequence == self.link_sequence_fed)
        {
            return Err(Reject::NoProgress);
        }
        self.local_progress_fed = self.local_progress;
        self.link_sequence_fed = self.link_sequence;
        self.source_wdi_last = self.now;
        Ok(())
    }

    pub fn observe_disarm_low(&mut self) -> Result<(), Reject> {
        if self.source_q || self.physical_permit || self.run_q || self.session_q {
            return Err(Reject::NotDisarmed);
        }
        self.disarm_seen_after_trip = true;
        Ok(())
    }

    pub fn acknowledge_physical_disarm(&mut self) -> Result<(), Reject> {
        if self.source_q
            || self.physical_permit
            || self.run_q
            || self.session_q
            || !self.disarm_seen_after_trip
        {
            return Err(Reject::NotDisarmed);
        }
        self.disarm_acknowledged = true;
        self.reset_lockout = false;
        Ok(())
    }

    pub fn deliberate_restart(&mut self) -> Result<(), Reject> {
        if self.state != State::Lockout
            || !self.disarm_acknowledged
            || self.source_q
            || self.physical_permit
            || self.run_q
            || self.session_q
        {
            return Err(Reject::NotDisarmed);
        }
        self.source_alive = false;
        self.reset_lockout = true;
        Ok(())
    }
}
