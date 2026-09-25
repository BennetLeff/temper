# Revision 28 command boundary model

This isolated Rust harness composes the frozen Revision 13 logical receiver
with a small adapter contract for Revision 11's maintained clear and ARM
boundary. It demonstrates one discrete model tick of ARM after an accepted
matching START; ARM is low while idle. A modeled maintained permission is
`permit_wire AND link_healthy AND source_healthy`, so independent link or
source-health loss forces it low even if the PERMIT conductor is stuck high.
The latch model clears on permission loss and does not restart when permission
returns without a new ARM edge.

The in-flight START case is tested after the source-reset indication has
reached the adapter boundary. This does not establish how quickly hardware
would detect or propagate that reset. The tests model logical ordering only;
they do not specify actual pulse width, voltage, isolator behavior, latch
propagation, relay/gate turn-off, metastability, or an electrical implementation.

## Reproduce

From the worktree root:

```sh
cat \
  zapote/power-entry/passive-reva/protection/interface-handshake-13/command/handshake.rs \
  zapote/power-entry/passive-reva/protection/interface-integration-28/command-model/adapter-tests.rs \
  > /tmp/temper-rev28-command-adapter.rs
rustc --edition=2021 --test /tmp/temper-rev28-command-adapter.rs \
  -o /tmp/temper-rev28-command-adapter
/tmp/temper-rev28-command-adapter
```
