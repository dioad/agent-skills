---
description: 'Structured logging conventions using zerolog across HTTP handlers, middleware, and library code'
applyTo: '**/*.go'
---

# Structured Logging with zerolog

All logging uses `github.com/rs/zerolog`. Follow these conventions consistently across every package and codebase.

## Core Rule: Request-Scoped vs Construction-Time Loggers

The choice of where a logger lives determines how log events are correlated:

| Context | Pattern | Reason |
|---------|---------|--------|
| `net/http` handler or middleware | `zerolog.Ctx(r.Context())` | Carries request-scoped fields (request ID, auth info) through the full handler chain |
| Long-lived struct with fixed enrichment | `zerolog.Logger` field on the struct | Carries construction-time labels (component name, validator label) that never change |
| Program startup / `main()` | `log.Logger` (package-level) | No request context exists; acceptable at the outermost layer only |

Never store a `zerolog.Logger` on a struct that handles `net/http` requests just to avoid writing `zerolog.Ctx(r.Context())`. The stored logger will not carry dynamic request fields, and those fields will be silently absent from every log event.

## Application Startup: DefaultContextLogger and Root Context Injection

At the application entry point (`Exec` / `main`), do two things after configuring `log.Logger`:

1. **Set `zerolog.DefaultContextLogger`** to the enriched logger so that `zerolog.Ctx` works correctly on *any* context — including shutdown contexts derived from `context.Background()`.
2. **Inject the same logger into the root context** so all child contexts inherit the enrichment automatically.

Both must use the **same enriched logger**. Splitting them — setting `DefaultContextLogger` to the raw `log.Logger` while injecting an enriched version into `ctx` — means fallback-context paths (e.g. shutdown, periodic cleanup) log without the service label.

```go
// Correct — single enriched logger for both mechanisms
serviceLogger := log.Logger.With().Str("service", "my-service").Logger()
zerolog.DefaultContextLogger = &serviceLogger
ctx = serviceLogger.WithContext(ctx)

// Wrong — DefaultContextLogger lacks the service field
log.Logger = ...  // configured by CLI
zerolog.DefaultContextLogger = &log.Logger        // no service field
ctx = log.Logger.With().Str("service", "x").Logger().WithContext(ctx)  // enriched ctx only
```

With `DefaultContextLogger` set, `zerolog.Ctx(ctx)` is safe to use everywhere: it returns the configured logger even for contexts that have no embedded logger, making `log.*` calls unnecessary outside of program initialisation.

## Component Context Enrichment

When creating a long-lived sub-context for a component (manager, worker pool, background bridge), enrich it with a `component` label immediately after creating the derived context. All goroutines spawned from that context automatically emit log events with the label.

```go
func NewManager(ctx context.Context, ...) *Manager {
    managerCtx, cancel := context.WithCancel(ctx)

    // Enrich before storing — all goroutines inherit component=webhook.
    componentLogger := zerolog.Ctx(managerCtx).With().Str("component", "webhook").Logger()
    managerCtx = componentLogger.WithContext(managerCtx)

    m := &Manager{ctx: managerCtx, cancel: cancel}
    m.startWorkers(managerCtx)  // workers get component label for free
    ...
}
```

`context.WithCancel` (and `WithTimeout`, `WithDeadline`) preserve the value bag, so the embedded logger is inherited by all derived contexts automatically.

## Context Consistency Within a Function

When a function has both guard/early-return paths and a long-running goroutine, build the logger from the **same context** used by the goroutine. Building the logger from the caller's context for the guard checks and from a different context for the goroutine produces log events with inconsistent field sets — making them unrelatable in log aggregation.

```go
// Wrong — logger built from caller ctx (request-scoped, has request_id);
// goroutine logger built from m.ctx (component-scoped, has component=webhook).
// The two paths emit structurally different log events.
func (m *Manager) DeliverHistoricalEvents(ctx context.Context, ...) {
    logger := zerolog.Ctx(ctx).With().Str("subscription_id", sub.ID).Logger()
    if store == nil {
        logger.Warn()...  // has request_id, lacks component=webhook
        return
    }
    deliveryCtx := m.ctx
    go func() {
        logger := zerolog.Ctx(deliveryCtx).With().Str("subscription_id", sub.ID).Logger()
        logger.Debug()...  // has component=webhook, lacks request_id
    }()
}

// Correct — resolve the authoritative context first, build one logger from it,
// share it between guard checks and the goroutine.
func (m *Manager) DeliverHistoricalEvents(ctx context.Context, ...) {
    deliveryCtx := m.ctx  // resolve authoritative context first
    logger := zerolog.Ctx(deliveryCtx).With().Str("subscription_id", sub.ID).Logger()
    if store == nil {
        logger.Warn()...  // same fields as goroutine
        return
    }
    go func() {
        // logger captured from enclosing scope — no re-derivation needed.
        logger.Debug()...
    }()
}
```

The general rule: **if a goroutine runs under a different context than the caller, resolve that context before building the logger** so all log events for the operation carry a consistent field set.

## HTTP Response Writers and Background Write Goroutines

When spawning a goroutine to handle HTTP response writes (e.g. SSE, chunked streaming), pass `req.Context()` as the logging context — not the server or broker context. Write errors are per-stream, per-request events; they should carry the same `request_id`, `principal`, and other request-scoped fields as every other log line for that stream.

```go
// Wrong — broker context loses request_id and principal in write errors
writer := m.startWriter(serverCtx, w, streamID)

// Correct — request context preserves full per-request enrichment
writer := m.startWriter(req.Context(), w, streamID)
```

## Service Layer Functions

Service layer functions (business logic, managers, services) that accept `context.Context` and are called from HTTP handlers — directly or transitively — must use `zerolog.Ctx(ctx)` to emit logs. This ensures that request-scoped fields injected by middleware (request ID, trace ID, principal) are present in service layer log output.

```go
// Correct — request-scoped fields flow through the call stack
func (s *EventService) PublishEventsToTopic(ctx context.Context, topic string, events []event.Event) error {
    zerolog.Ctx(ctx).Info().Str("topic", topic).Msg("publishing events")
    ...
}

// Correct — audit log in a service method called from an HTTP handler
func (m *Manager) CreateSubscription(ctx context.Context, ...) (*Subscription, error) {
    ...
    zerolog.Ctx(ctx).Info().
        Str("subscription_id", subscription.ID).
        Str("action", "subscription_created").
        Msg("Audit: subscription created")
    return subscription, nil
}

// Wrong — global logger loses all request-scoped fields
func (m *Manager) CreateSubscription(ctx context.Context, ...) (*Subscription, error) {
    ...
    log.Info().Str("subscription_id", subscription.ID).Msg("Audit: subscription created") // missing request ID, trace, etc.
    return subscription, nil
}
```

**Background goroutines and lifecycle methods:** Functions that run outside the HTTP request lifetime (worker goroutines, shutdown handlers, pubsub bridge routines, periodic cleanup) use `zerolog.Ctx(ctx)` just like any other code. Their context is a process/manager context that carries component-level enrichment (e.g. `component=webhook`) but not request-scoped fields — which is correct, since those fields have no meaning outside a request.

With `zerolog.DefaultContextLogger` set at startup (see "Application Startup" section), `zerolog.Ctx(ctx)` is always safe to call even if the context has no embedded logger; the fallback returns the configured application logger. The global `log.*` package is therefore only needed before the application context is initialised (i.e. in `main` / `init`).

```go
// Correct — background worker uses context logger; inherits component=webhook
// from the manager's enriched context.
func (m *Manager) worker(ctx context.Context, id int) {
    logger := zerolog.Ctx(ctx).With().Int("worker_id", id).Logger()
    logger.Debug().Msg("Starting webhook worker")
    for {
        select {
        case job := <-m.eventQueue:
            m.processJob(ctx, job)
        case <-ctx.Done():
            logger.Debug().Msg("Stopping webhook worker")
            return
        }
    }
}

// Correct — lifecycle method uses context logger; DefaultContextLogger provides
// the configured logger when ctx is a fresh shutdown context.
func (m *Manager) Shutdown(ctx context.Context) error {
    zerolog.Ctx(ctx).Info().Msg("Shutting down webhook manager")
    ...
}
```

## HTTP Handlers

Always obtain the logger from the request context:

```go
// Correct
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    log := zerolog.Ctx(r.Context())
    log.Error().Err(err).Msg("token exchange failed")
}

// Correct — inline for single use
zerolog.Ctx(r.Context()).Error().Err(err).Msg("failed to generate state")

// Wrong — stored logger misses request-scoped fields
type Handler struct {
    logger zerolog.Logger // do not do this for HTTP handlers
}
```

`zerolog.Ctx` returns a no-op logger when no logger is in the context — it is always safe to call without a nil check.

For handlers that call the logger more than once, assign a short-lived local:

```go
log := zerolog.Ctx(r.Context())
if code == "" {
    log.Error().Msg("missing code in callback")
    http.Error(w, "missing code", http.StatusBadRequest)
    return
}
if state == "" {
    log.Error().Msg("missing state in callback")
    http.Error(w, "missing state", http.StatusBadRequest)
    return
}
```

## Middleware: Enrich the Context Logger with UpdateContext

Middleware that authenticates, enriches, or categorises a request should add structured fields to the context logger using `UpdateContext`. Fields added this way are present in all subsequent log events for the request — including deferred access log entries written after the handler returns.

```go
// Add a field unconditionally when auth succeeds
zerolog.Ctx(r.Context()).UpdateContext(func(c zerolog.Context) zerolog.Context {
    return c.Str("auth_source", "oidc_session")
})

// Add a field conditionally (e.g. only when a token was refreshed)
if refreshed {
    zerolog.Ctx(r.Context()).UpdateContext(func(c zerolog.Context) zerolog.Context {
        return c.Bool("token_refreshed", true)
    })
}

// Pass the enriched context to the next handler
next.ServeHTTP(w, r.WithContext(ctx))
```

`UpdateContext` mutates the logger stored in the context in-place. There is no need to create a new context or reassign `r` solely for the logger update; the mutation is visible to all code that subsequently calls `zerolog.Ctx` on the same context.

### Do Not Pass Loggers as Function Arguments to HTTP Handlers

Middleware and handlers should not accept a `zerolog.Logger` parameter for per-request logging. Use `zerolog.Ctx(r.Context())` inside the handler body. Passing a logger as an argument bypasses context-scoped enrichment.

```go
// Wrong
func NewHandler(validator Validator, cookieName string, logger zerolog.Logger) *Handler

// Correct
func NewHandler(validator Validator, cookieName string) *Handler
```

## Handlers: Add Extracted Identifiers to Context

Any HTTP handler that extracts an identifier or meaningful scope value from the request — path value, query parameter, or decoded body field — must add it to the context logger via `UpdateContext` as early as possible, so that all subsequent log events for the request automatically carry it. This includes deferred access log entries written after the handler returns.

```go
// Path value
tunnelID := req.PathValue("tunnelID")
zerolog.Ctx(req.Context()).UpdateContext(func(c zerolog.Context) zerolog.Context {
    return c.Str("tunnel_id", tunnelID)
})

// Body field (after decoding)
zerolog.Ctx(req.Context()).UpdateContext(func(c zerolog.Context) zerolog.Context {
    return c.Str("target_state", body.State)
})

// Multiple fields in one call
zerolog.Ctx(req.Context()).UpdateContext(func(c zerolog.Context) zerolog.Context {
    return c.
        Str("request_id", tc.RequestID).
        Str("connection_id", tc.ConnectionID.String()).
        Str("direction_type", string(cfg.DirectionType))
})
```

Add `UpdateContext` before any log events or calls to downstream handlers, so the fields are present in every event — not just the ones written after the update.

### What to add

Add identifiers and resource-scope labels that are safe to record for every request:

- **Path values** — resource identifiers such as `tunnel_id`, `provider`, `connection_id`
- **Non-sensitive body fields** — discriminators and state labels such as `tunnel_type`, `target_state`
- **Configuration scope** — fields that characterise the request class such as `service_type`, `direction_type`

### What NOT to add

Never add security-sensitive values to the context logger:

- OAuth `code` or `state` query parameters
- Passwords, API keys, shared secrets, HMAC signatures
- Session tokens, refresh tokens, or any bearer credential
- PII beyond what is already present via `principal` (e.g. full email addresses, raw claims)

When in doubt: if the value would be redacted in a security audit, do not log it.

### Deduplication across middleware layers

Some fields (`principal`, `auth_source`, `token_refreshed`) are already added to
context by upstream middleware. Do not repeat them in downstream handlers — check
what the middleware chain for the current handler sets before adding a field. See
"Avoid Duplicate Fields Across Layers" below for the general rule.

## Field Naming: Always snake_case

All log field names must use `snake_case`. This applies to both `Str`/`Bool`/`Int` calls in handlers and to fields added by `UpdateContext`.

```go
// Correct
log.Str("auth_source", "oidc_session")
log.Bool("token_refreshed", true)
log.Str("request_id", id)
log.Int("jwt_validators", count)

// Wrong — mixed naming breaks query consistency in log aggregation tools
log.Str("authSource", "oidc_session")    // camelCase
log.Bool("TokenRefreshed", true)         // PascalCase
log.Str("request-id", id)               // kebab-case
```

### Standard Field Names

Use these names consistently across all codebases:

| Field | Type | Set by | Meaning |
|-------|------|--------|---------|
| `service` | `string` | Application entry point (`Exec`) | Process-wide label identifying the service (e.g. `eventbroker`). Set once via `DefaultContextLogger` and root context injection so every log event carries it. |
| `component` | `string` | Component constructor (e.g. `NewManager`) | Subsystem label injected into a long-lived sub-context (e.g. `webhook`, `sse`, `cors`). Inherited by all goroutines spawned from that context. |
| `request_id` | `string` | Request-ID middleware | Unique ID per HTTP request |
| `auth_source` | `string` | Auth middleware | Which auth mechanism validated the request (`oidc_session`, `jwt`, `basic`, `github`, `hmac`) |
| `token_refreshed` | `bool` | OIDC session middleware | Set to `true` when a token was silently refreshed during the request |

## Avoid Duplicate Fields Across Layers

Before adding a field with `Str`/`Bool`/`Int` or via `UpdateContext`, check
whether a downstream dependency (`dioad/net`, `dioad/auth`, `dioad/cli`) or an
upstream middleware in this same request chain already attaches it. Fields
like `principal` and `auth_source` are frequently added once by a shared
middleware; re-adding them locally either duplicates the field in every log
line or, worse, silently shadows the shared value with a locally-computed one
that can drift out of sync.

When reviewing or touching logging code, check for duplicate/redundant
properties across the call chain and remove local additions that a shared
layer already provides. If a field's origin/ownership is ambiguous, prefer
attaching it to the context once, as high up the call chain as it is known,
over re-deriving it at each layer.

## Log Messages

- Use sentence case; start messages with a capital letter
- Keep messages lowercase — they are machine-readable strings, not prose
- Never end a message with punctuation
- Do not interpolate dynamic values into the message string; put them in typed fields

```go
// Correct
log.Error().Err(err).Msg("failed to refresh token")
log.Error().Err(err).Str("cookie", name).Msg("missing or invalid state cookie")

// Wrong
log.Error().Msgf("failed to refresh token: %v", err)  // swallows structured err field
log.Error().Msg("Failed to refresh token.")            // capital + punctuation
```

## Construction-Time Loggers

Validators, debuggers, and other long-lived components that carry a fixed label (e.g. the name of the OIDC issuer being validated) may hold a `zerolog.Logger` as a struct field. This is correct because the enrichment is set once at construction, not per-request.

```go
type ValidatorDebugger struct {
    inner  TokenValidator
    logger zerolog.Logger  // acceptable: enriched once with a fixed label
}

func NewValidatorDebugger(v TokenValidator, opts ...Option) *ValidatorDebugger {
    d := &ValidatorDebugger{inner: v, logger: zerolog.Nop()}
    for _, opt := range opts {
        opt(d)
    }
    return d
}

func WithLogger(l zerolog.Logger) Option {
    return func(d *ValidatorDebugger) { d.logger = l }
}
```

The key distinction: if the log enrichment is the same for every call (e.g. `label:"flyio"`), a stored logger is appropriate. If the enrichment depends on the in-flight request (e.g. `request_id`, `auth_source`), use `zerolog.Ctx`.

## Testing

Use `zerolog.Nop()` for construction-time loggers in tests:

```go
d := NewValidatorDebugger(validator, WithLogger(zerolog.Nop()))
```

For handlers and middleware under test, inject a logger into the request context:

```go
logger := zerolog.New(os.Stderr)
ctx := logger.WithContext(context.Background())
req = req.WithContext(ctx)
```

Or use `zerolog.Nop()` to suppress output in unit tests where log content is not being asserted:

```go
ctx := zerolog.Nop().WithContext(context.Background())
req = req.WithContext(ctx)
```

## Summary of Anti-Patterns

| Anti-pattern | Correct alternative |
|---|---|
| `logger zerolog.Logger` field on an HTTP handler struct | `zerolog.Ctx(r.Context())` in the handler body |
| Passing `zerolog.Logger` as an argument to handler constructors | Remove the parameter; read from context at call time |
| Using `log.Logger` (package-level) inside a handler or service function that accepts `context.Context` | `zerolog.Ctx(ctx)` — preserves request-scoped fields across the call stack |
| Setting `zerolog.DefaultContextLogger` to the raw `log.Logger` while injecting an enriched logger into `ctx` | Use the same enriched logger for both — split enrichment means fallback-context paths (shutdown, cleanup) log without the service label |
| Building the logger from the caller's request context in a function whose goroutine runs under a different (component) context | Resolve the authoritative context first, then build one logger from it and share it across guard checks and the goroutine |
| Passing the server/broker context to an HTTP response-writer goroutine | Pass `req.Context()` — write errors are per-request events and should carry request-scoped fields |
| Not enriching a component's sub-context with a `component` label before spawning workers | Call `zerolog.Ctx(ctx).With().Str("component", "name").Logger().WithContext(ctx)` immediately after `context.WithCancel` |
| `ctx.Done()` drop in a queue `select` with no metric or log | Record the drop identically to the capacity-full branch (metric increment + observer call + warn log) |
| camelCase or PascalCase field names | `snake_case` field names |
| `log.Msgf(...)` with `%v` for errors | `.Err(err).Msg(...)` to preserve structured error fields |
| Logging an error and then returning it | Choose one: log it here, or return it and let the caller log it |
| `UpdateContext` fields added after calling `next.ServeHTTP` | Add `UpdateContext` fields before calling `next.ServeHTTP` so they are present in the handler and in deferred access logs |
| Extracting a path value or body field in a handler without adding it to the context logger | Call `UpdateContext` with the identifier as early as possible, before any log events or downstream calls |
| Adding OAuth `code`/`state`, tokens, secrets, or signatures to the context logger | Only add non-sensitive identifiers and scope labels; anything that would be redacted in a security audit stays out |
