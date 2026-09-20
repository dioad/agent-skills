---
description: 'Composition-root conventions for a long-running Go service: Build/Run split, config validation, inert-config feedback, and metrics naming'
applyTo: '**/*.go'
---

# Service Composition and Lifecycle

These conventions apply to a service's composition root — the `main`/`Exec`
entry point that reads config, wires dependencies, and runs one or more
servers (an application server plus, commonly, a separate management server
for health/metrics/debug). They converged independently across several
services reviewed in isolation, which is the signal that they are conventions
rather than one project's taste.

See `zerolog.instructions.md` ("Application Startup") for
`zerolog.DefaultContextLogger` and root-context logger injection — that
happens inside `Build`, alongside the wiring below, but is documented there
in full and is not repeated here.

## Split `Build` from `Run`

Separate construction from starting:

- **`Build(ctx, cfg) (*Application, error)`** validates config, constructs
  every dependency (clients, registries, the enriched logger, metrics
  registration), and wires routes/handlers. It starts **no goroutine and
  binds no listener**. A `Build` that returns an error must not have left
  anything running that needs cleanup.
- **`Run(ctx) error`** starts every server and blocks until `ctx` is
  cancelled or a server reports a non-graceful exit, then shuts down
  cleanly and returns.

This split makes `Build` unit-testable without a network (construct an
`Application`, inspect its wiring, assert on config-rejection paths) and
keeps `Run` focused purely on the start/wait/shutdown sequence.

```go
// Build validates configuration and wires dependencies. No goroutines are
// started and no listener is bound — that happens in Run.
func Build(ctx context.Context, c *Config) (*Application, error) {
    c.SetDefaults()
    if err := c.Validate(); err != nil {
        return nil, fmt.Errorf("invalid configuration: %w", err)
    }
    // ... construct clients, registries, routes, metrics registration ...
    return &Application{ /* ... */ }, nil
}

func (a *Application) Run(ctx context.Context) error {
    // ... start every server, block on ctx.Done() or a server error, shut down ...
}
```

### Fan every server's failure into one channel

When a service runs more than one server (an application server and a
management server are the common pair), start each in its own goroutine and
have both report into a single buffered `error` channel, sized for the
number of servers so neither goroutine blocks on send if `Run` has already
returned:

```go
serverErr := make(chan error, 2)

go serve(logger, "management", mgmtAddr, mgmtServer, serverErr)
go serve(logger, "main", mainAddr, mainServer, serverErr)

select {
case <-ctx.Done():
    return shutdown()
case err := <-serverErr:
    shutdown()
    return err
}
```

A bind failure or unexpected exit on **either** server must reach `Run`'s
caller — do not let one server's `ListenAndServe` error be logged and
swallowed while `Run` waits only on the other server or on `ctx.Done()`.
Factor the `serve` helper (log start, call `ListenAndServe`, ignore
`http.ErrServerClosed`, wrap and forward any other error) once per module and
reuse it for every server the service starts, rather than duplicating the
same goroutine body per server.

### Register metrics before any server starts serving

Call `metrics.Register(...)` in `Build`, before constructing the management
server that will expose `/metrics`. Registering after the management server
starts serving creates a window where a scrape during startup misses the
service's own collectors.

## `Validate` must reject a configuration that makes the service a silent no-op

A configuration that parses cleanly but leaves the service with nothing to
do — no listen address configured, no event source configured for a
service that only reacts to events, etc. — is a validation error, not a
service that starts and does nothing forever. Either:

- reject it from `Config.Validate()`, or
- if there's a legitimate reason to allow it (e.g. a feature flag
  deliberately disables a subsystem), make the service fail readiness
  (`/health/ready` unhealthy) while inert, so an orchestrator does not route
  traffic to it and an operator has a concrete signal.

Pick one approach per service and apply it consistently — do not leave some
inert-configuration cases silently accepted while others are rejected.

## Surface populated-but-inert config keys

A config struct accumulates fields faster than the code that reads them.
When a field is parsed but currently has no effect for a given deployment —
deprecated, redundant with another block, or conditionally wired only in
some configurations — do not let it silently do nothing. Add a method that
lists the names of any such populated-but-inert blocks, and log one `Warn`
per block at startup:

```go
// InertReservedBlocks returns the names of config keys that are parsed but
// have no effect in this configuration, so Build can warn for each.
func (c *Config) InertReservedBlocks() []string {
    var blocks []string
    if c.DeprecatedField != "" {
        blocks = append(blocks, "deprecated-field (no longer used)")
    }
    return blocks
}

// in Build, after SetDefaults/Validate:
for _, block := range c.InertReservedBlocks() {
    logger.Warn().Str("config_block", block).
        Msg("configuration key is set but has no effect in this build")
}
```

This is cheaper than deleting the field outright when removal isn't safe yet
(a shared config struct, a deprecation window), and it turns a silent
misconfiguration into a startup log line an operator can act on. When a
whole family of related settings shares one gate (e.g. two listen addresses
that both depend on the same name/credential being configured), the
`Validate()` check for that gate must cover *every* setting in the family,
not just the one it was originally written for — a config combination that
passes `Validate()` cleanly but never gets wired into a route is exactly this
failure mode with no warning attached at all.

## Metrics naming convention

Name metrics `<service>_<operation>_total{result}` for counters and
`<service>_<operation>_duration_seconds` for latency histograms, with
`result` (or another low-cardinality outcome label) distinguishing success
from the specific failure modes worth alerting on separately. Apply this
consistently to every async or background data path a service runs — a
stale-data purge loop, a subscriber/consumer loop, a periodic
reconciliation job — not only to request-handling paths, since those are
exactly the paths with no request/response to alert on otherwise.

## Event-ingestion trust boundary

When `Build` wires a subscriber/consumer for a shared event bus (e.g.
`dioad/eventbroker`), the handler typically has no per-event caller identity
to authenticate — it trusts whatever the broker relays on the subscribed
topic. That trust decision must be explicit, not implicit:

- **State and justify it in the package doc and the service's
  `ARCHITECTURE.md`**: name the single authorized publisher, and record that
  the broker topic ACL (who is allowed to publish to this topic) is
  load-bearing for the service's security model. A reader should not have to
  infer the trust boundary from the absence of an auth check.
- **Grant the synthetic principal attached to relayed events only the roles
  its registered handlers actually need** — least privilege applies to a
  principal your own code constructs just as much as to one presented by a
  caller. A synthetic principal minted with broad roles "to be safe" widens
  the blast radius of any bug in event routing or a compromised publisher
  to every capability those roles carry, not just the ones this handler
  uses.
- **If the topic ACL cannot be solely relied on** (multiple publishers share
  the topic, or the broker's ACL enforcement isn't itself trusted end to
  end), verify a per-event signature or a broker-stamped origin claim in the
  handler before acting on the event, rather than accepting topic membership
  alone as authentication.

## Test the composition root

Give the composition root its own `main_test.go` (or equivalent) asserting,
at minimum:

- a bind failure on any server surfaces as an error from `Run`, rather than
  being logged and silently swallowed
- a clean `ctx` cancellation shuts down every server and `Run` returns `nil`
- a configuration that `Validate()` should reject actually does, with the
  specific error message pinned (see `go-testing.instructions.md` on
  asserting the specific check that fired, not just that some error did)
- `Build` performs no I/O and starts no goroutine — a `Build` on a config
  that would fail to bind must still succeed, because binding is `Run`'s job
