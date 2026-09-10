---
description: 'AST-aware Go repository navigation via gograph — use for symbol lookup and call-tree analysis instead of grep/find in *.go codebases'
applyTo: '**/*.go,**/go.mod,**/go.sum'
---

gograph: AST-aware Repository Navigation Tool for AI Agents

Use gograph whenever you need to find a symbol or analyse call trees in a Go
(*.go) codebase. Before answering architecture, dependency, or "where is X?"
questions about this repository, read `.gograph/GRAPH_REPORT.md` first — use
it as the repo map before searching raw files. Use `gograph query` and
`gograph callers` for symbol lookup.

━━━ READ FIRST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If this repository has an llm-wiki/ directory with curated context pages,
read them BEFORE writing any code or running any analysis:

  llm-wiki/README.md        → index of all wiki pages
  llm-wiki/project.md       → project identity, non-goals, correctness model
  llm-wiki/rules.md         → binding rules (git, build, testing, architecture)
  llm-wiki/agent-contract.md → session lifecycle and tool selection contract

To generate them (or refresh a stale set): gograph build . --precise && gograph wiki

━━━ PREREQUISITE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALL query commands read from .gograph/graph.json. If it does not exist, every
query fails. Build it once before anything else:

  gograph build .            fast, tolerates broken code — use during development
  gograph build . --precise  type-checked CHA — use before refactors (needs compilable code)

After build: graph.json + Markdown reports are written to .gograph/.
The .gograph/ ignore entry is appended to the Git repository root .gitignore
when available; outside Git, the build target .gitignore is used.
If no Go files are found after ignore filtering, build exits before writing artifacts.
  gograph stats   → counts (packages/files/symbols/calls/routes/SQL/tests)
  gograph stale   → lists source files newer than graph.json (shows newest source time/file)

Rebuild whenever source files change. The graph does NOT auto-update.

━━━ COMMON WORKFLOWS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Start of any session         → summary  (top hotspots + worst instability + highest complexity + orphan/god-obj counts in ONE call)
  Onboard to unfamiliar repo   → hotspot, skeleton, focus <pkg>
  Find where X is defined      → query <term>  then  source <sym> to read body
  Understand a symbol (raw)    → context <sym>  (callers+callees+source+tests in one call)
  Understand all changed syms  → context --uncommitted  (all contexts bundled — use after plan --uncommitted)
  Understand a symbol (deep)   → explain <sym>  (role, complexity, SQL, env, routes, interfaces)
  Before editing any symbol    → plan <sym>     (callers, tests, SQL/env/route risk)
  After editing, before commit → review --uncommitted  then  build . --precise
  Before a package refactor    → dependents <pkg>  (every consumer of this package)
  Full blast radius of change  → impact <sym>  or  impact --uncommitted  or  impact --since <ref>
  PR / branch scope review     → changes --git main
  HTTP endpoint deep-dive      → endpoint <handler>  (route + call chain + SQL + env)
  Error root-cause trace       → errorflow <err_str>
  Dead code sweep              → orphans
  Test coverage gaps (codebase) → untested  (callers but zero test edges — one sweep, sorted by risk)
  External symbol signature    → doc <pkg.Symbol>  (stdlib/third-party — no graph required)
  API breaking-change check    → api --since <ref>
  CI enforcement               → gate, check --since <ref>

━━━ WHEN TO USE WHAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINDING THINGS — three different scopes:
  query <term>      broad: searches symbol names, file paths, package names, import paths, call sites
  node <sym>        exact: AST metadata for one named symbol (kind, file, line, signature, doc)
  source <sym>      body: extracts the actual source code block — use instead of reading the file

CALL GRAPH — two different depths:
  callers/callees <sym> [--depth N]   bounded: 1 hop (default) up to 10 — use for focused exploration
  impact <sym>                         unbounded: full BFS to ALL transitive callers — can be large on hotspots
  <sym> can be a short name ("Validate" — fuzzy substring match), a standard Go package-qualified
    name ("graph.Graph" or "graph.Graph.Build" — standard dot-notation), or a fully-qualified
    ID ("pkg/path::(*Service).Validate" — exact match, no same-name conflation). Use
    the dot or FQ form to disambiguate overloads/duplicates. Requires --precise build for
    full effect. Works for callers, callees, impact, and path (both endpoints).

SYMBOL UNDERSTANDING — two different outputs:
  context <sym>   structured data: node + source + callers + callees + tests — fast, token-efficient
  explain <sym>   narrative: role classification, prod vs test split, complexity, SQL, env, routes, interfaces
                  → use context when you need lists to act on; use explain when you need to understand purpose

PACKAGE RELATIONS — three different questions:
  deps <pkg>           what does this package import? (outgoing)
  dependents <pkg>     what imports this package? (incoming) — essential before refactoring a package
  imports <path>       which files import this specific import path? — for tracing one external dependency

STRUCT / TYPE — five different angles:
  fields <struct>        what fields does this struct have?
  embeds <struct>        which structs embed this struct?
  constructors <struct>  which functions return this struct? (New*, factory functions)
  literals <struct>      where is this struct initialized as Foo{...}? (run before adding a required field)
  implementers <iface>   which structs satisfy this interface?
  interfaces <struct>    which interfaces does this struct satisfy? (inverse of implementers)
  usages <type>          where is this type used? (param/return types, struct fields, iface methods)
                         → use before changing any interface or type — shows the full blast radius

PACKAGE vs SYMBOL scope:
  focus <pkg>    everything in a package: files, all symbols, internal calls, imports
  public <pkg>   exported symbols only: the package's API surface
  context <sym>  one symbol only: deep slice of a single function/struct/interface

ERRORS — two different questions:
  errors              where are all errors defined and returned in the codebase?
  errorflow <term>    how does this specific error reach the HTTP layer? (definition → return sites → entry point)

━━━ OUTPUT FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All search/navigation commands support four output modes:

  (default)       [kind] Name — detail  (file:line)  — one result per line
  --json          {"ok":true,"cmd":"...","query":"...","count":N,"data":[...]}
  --files-only    flat deduplicated list of file paths — use for checklists
  --mermaid       visual dependency/call diagrams in Mermaid format
                  (supported by deps, dependents, coupling, callers, callees, path, impact, endpoint)

Use --json when piping output to another tool or when you need structured data.
Use --files-only when you only need to know which files are involved.

━━━ STATIC ANALYSIS LIMITATIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Know these before trusting results:

  Interface dispatch    callers/callees may miss calls through interface variables unless
                        'build . --precise' was used (enables type-checked CHA call graph)
  errorflow             heuristic AST traversal — NOT SSA/data-flow. Useful for navigation,
                        not proof. Confidence rating (HIGH/MEDIUM) is a heuristic estimate.
  endpoint              route patterns only resolve flat string literals. Gin/Echo/Chi
                        Group() prefixes are lost at AST level — always search by handler
                        symbol name, not route string.
  impact / skeleton     can produce very large output on hotspot symbols or large repos.
                        Use callers --depth N for bounded traversal instead of impact.
  All results           reflect the state of graph.json at last build. Run 'gograph stale'
                        to confirm the index is current before structural analysis.
  Subdirectory safe     all query commands auto-discover the project root (walks up to
                        the nearest .gograph/ directory). No need to cd back to the repo
                        root before running plan, review, or any other query.

━━━ COMMANDS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AGENT WORKFLOW RULES (CRITICAL):
1. BEFORE editing: run 'gograph plan <symbol>' — callers, tests, SQL/env/route risk in one call
2. AFTER editing:  run 'gograph build . --precise' then 'gograph review --uncommitted'

INDEXING:
build . [--precise]  : parse AST, write graph.json + GRAPH_REPORT.md to .gograph/
                       Skips .git, vendor, testdata, .claude, .cursor, .agents, and
                       any directories listed in .gitignore (via git check-ignore).
stale                : list source files newer than graph.json (shows newest source time/file)
stats                : schema version, build time, symbol/call/route counts

QUERY COMMANDS:
boundaries [--config] : verify package architecture constraints using boundaries.json
boundaries --create   : auto-generate a baseline boundaries.json from the current repo
callees <fn> [--no-tests] [--depth N]: what fn calls (depth=1 direct; --depth 2+ expands N hops, max 10)
callers <fn> [--no-tests] [--depth N]: who calls fn (depth=1 direct; --depth 2+ expands N hops, max 10)
complexity [sym]     : cyclomatic complexity estimate per function (highest first)
concurrency [str]    : goroutines/channels/mutexes
coupling [pkg]       : fan-in, fan-out, and instability per package
diagram [--group-by package|module|service|file] [--max-depth N] [--include-stdlib]
                     : Mermaid architecture diagram of package dependency graph
embeds <struct>      : structs embedding this struct
envs [str]           : os.Getenv/viper reads
errors [--no-tests]  : custom errors/panics
fields <struct>      : fields/types of struct
focus <pkg>          : all files, symbols, calls, imports for one package
godobj               : god-object struct candidates (--methods N --fields N --calls N --top N)
impact <sym>         : full transitive blast radius — WARNING: can be large on hotspot symbols
impact --uncommitted : blast radius of all uncommitted changes
impact --since <ref> : blast radius of all symbols changed since a git ref (e.g. main, HEAD~5)
implementers <iface> [--test-only] : structs implementing iface (--test-only = test/mock files only)
imports <path>       : files importing a specific import path
interfaces <struct>  : interfaces satisfied by this struct (inverse of implementers)
node <sym>           : AST metadata for one symbol (kind, file, line, signature, doc)
orphans              : symbols unreachable from any entry point via BFS (main, routes, exports)
path <from> <to>     : shortest call chain between two symbols (BFS)
public <pkg>         : exported symbols only
query <str>          : broad search — symbols, files, packages, imports, call sites
routes               : all HTTP REST routes. Annotates unresolvable handlers.
source <sym>         : exact source code — USE THIS instead of reading files
sql                  : raw SQL queries mapped to their functions
tests <sym>          : test functions exercising this symbol

TOKEN SAVERS (COMPOSED COMMANDS — each replaces 3-8 separate calls):
api --since <ref>    : breaking API/contract changes since a git reference
arity [--min 5]      : functions with too many arguments
changes              : symbols modified/new/deleted since last build
changes --git <ref>  : symbols in files changed since a git ref (e.g. main, HEAD~5, v1.4.50)
constructors <struct>: factory functions returning this struct
literals <struct>    : composite literal sites Foo{...} — run before adding/removing a required field
usages <type>        : where a type appears in signatures and fields (param/return/field/iface method)
returnusage <fn>     : how each caller uses the return value of fn (discarded/assigned/returned/passed)
risk <sym>           : risk evaluation — blast radius, complexity, tests, SQL/env (0-100 score + verdict)
risk --uncommitted   : risk evaluation for all uncommitted changes
context <sym> [--limit N]: node+source+callers+callees+tests — raw structured data
context --uncommitted    : context for ALL uncommitted symbols in one call (replaces 5-8 sequential context calls)
                           NOTE: every context response now includes 'role' (architectural classification)
dependents <pkg>     : packages that import this package (run before any package refactor)
deps <pkg> [--transitive]: import dependency tree (add --transitive for full BFS closure)
endpoint <handler>   : route + handler + full call chain + SQL + env reads
                       INPUT: handler symbol name (always works) or flat route string (flat routers only)
errorflow <term> [--no-tests]: error definition → return sites → likely HTTP entry point path
explain <sym>        : narrative summary — role, complexity, SQL, env, routes, interfaces, tests
                       (use explain for understanding; use context for raw data to act on)
fixtures <pkg>       : test helper structs and functions in test files
globals <pkg>        : package-level vars, consts, and functions mutating them
hotspot [--top N]    : functions ranked by incoming call count — study these first
mocks <iface>        : alias for 'implementers --test-only' (kept for compatibility)
mutate <field>       : functions that mutate a specific struct field — covers direct assignments, ++/+= (--precise only), and indirect mutations via method calls (atomic.*/sync.Map/sync.Mutex/channels/user wrappers; --precise only). Indirect rows show via=<method>.
plan <sym>           : change plan — callers, tests, SQL/env/route risk, public API impact
plan <sym> --with-context : plan + full context for every inspect_first symbol (saves N follow-up context calls)
plan --uncommitted   : change plan for all currently uncommitted modified symbols
review <sym>         : post-edit review — test coverage, complexity, risk profile
review --uncommitted : post-edit review for all uncommitted changes
risk <sym>           : change risk profile — blast radius, complexity, test coverage, SQL/env dependencies
risk --uncommitted   : change risk profile for all uncommitted changes
schema <table>       : structs mapped to a DB table via struct tags
skeleton             : full repository API signatures with bodies stripped — WARNING: large on big repos
trace <err_str>      : alias for errorflow (kept for compatibility)
doc <pkg[.Symbol]>  : "go doc <query>" — signature + doc comment for any stdlib or third-party symbol.
                       No graph required. Examples: doc fmt.Errorf  doc net/http.HandleFunc  doc io.Reader
                       doc github.com/jackc/pgx/v5.Conn.QueryRow
httpcalls [term]     : all outbound HTTP client calls via net/http (Get, Post, PostForm, Head).
                       Filter by method or URL substring.
untested [--pkg <n>] [--top N] : production functions with callers but zero test edges — coverage gaps
                       sorted by caller count (highest risk first). Replaces N 'tests <sym>' calls.
check [--since ref]  : static policy checks (boundaries, api_drift, test requirements)
gate                 : CI/CD enforcement against .gograph.yml thresholds
snapshot <subcmd>    : architectural metric snapshots (save, diff, list, drop)
mcp [path]           : start MCP server over stdio
gograph session <action>     : start/end audit sessions (create [word], end, audit, cleanup)
                               NOTE: MCP tool calls (gograph_plan, gograph_review) are
                               now correctly recorded in session audit counters.
add-claude-plugin    : install MCP plugin + CLAUDE.md rules + PreToolUse hook
hook-guard           : PreToolUse hook — blocks grep on Go symbols, redirects to gograph
