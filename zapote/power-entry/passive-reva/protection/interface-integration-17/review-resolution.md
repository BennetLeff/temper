# Revision17 parent review corrections

1. The watchdog handback mixed the legacy full-board source and current
   standalone interlock. Its claim that `InterlockWatchdog` repeated the legacy
   wrong pin map is false: the local definition already has RESET1/GND2. The
   legacy reversal was already documented in `zapote/interlock/MODEL.md`.
2. The standalone interlock already exports WDT_RESET_N on J2.8 and watchdog-
   qualified latched PERMIT on J2.6. The interlock, not the old U20 reference,
   is the relevant integration producer. Neither is part of the136-component
   power-entry compile.
3. A combined rail/watchdog output is not inherently unsuitable merely because
   it combines two reasons to clear. The real missing property is observing
   the source MCU's own reset while rails remain healthy. A second voltage
   supervisor alone does not supply that property.
4. Direct TPS3823 diagnostic fanout to a10kR pulldown was rejected. The30uA
   high-output test condition must be respected; “push-pull” is insufficient.
5. The capacitor handback's12.1uF census is useful, but its claim that this was
   the origin of revision16's12uF maximum example was inferred, not evidenced.
   That example was based on a hypothetical10uF+20% buck cap and was never a
   measured or complete assembly maximum. The new census supersedes it for
   integration planning.
6. TPS54202 EN rising1.21V is typical, not minimum. The0.7uA EN current and5ms
   soft-start are typical as well. Parent inspected the rendered table.
7. Buck startup during ongoing output charging is plausible, but startup
   switching below3V is inconsistent with its specified VIN UVLO. No additional
   sequencer is justified by that claim alone. Low-voltage passive charging,
   leakage and higher-voltage load steps remain unqualified.
8. Capacitor endurance is represented only by hypothetical sensitivity rows.
   Exact-part selection must determine whether its limits are independent,
   combined, typical or guaranteed. No physical rejection follows solely from
   the invented factor set.
