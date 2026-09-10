#!/usr/bin/env python3
"""test_quality.py -- turn raw measurements into test-quality artifacts.

This script does no measurement itself. `measure.sh` produces the inputs:

  * a gomutants JSON report           (mutation outcomes)
  * a whole-suite Go coverage profile  (statement reach)
  * one Go coverage profile per test   (per-test contribution)
  * optionally gocognit output         (cognitive complexity per function)

Sub-commands
------------
  scorecard     quantitative vector: statement / mutation coverage / efficacy
  findings      LLM-actionable doc: weak assertions, coverage gaps, risk
  contribution  per-test contribution map + greedy set-cover minimisation

Each writes Markdown (and, for contribution, JSON). Missing optional inputs
degrade gracefully -- a section is dropped, never faked.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# mutator weighting
# --------------------------------------------------------------------------- #
# A surviving mutant is a stronger smell in some classes than others: a
# survived conditional or return-value mutation means a real branch is
# unasserted; a survived counter increment on a metric is usually noise.
MUTATOR_WEIGHT = {
    "BRANCH_IF": 3, "BRANCH_ELSE": 3, "BRANCH_CASE": 3,
    "CONDITIONALS_NEGATION": 3, "CONDITIONALS_BOUNDARY": 3,
    "INVERT_LOGICAL": 3, "REMOVE_LOGICAL_NOT": 3, "INVERT_NEGATIVES": 3,
    "RETURN_ERROR_NIL": 3, "RETURN_TRUE": 3, "RETURN_FALSE": 3, "RETURN_ZERO": 3,
    "RANGE_BREAK": 3, "INVERT_LOOP_CTRL": 3,
    "STATEMENT_REMOVE": 2, "EXPRESSION_REMOVE": 2, "ERRORF_WRAP": 2,
    "ARITHMETIC_BASE": 1, "ARITHMETIC_ASSIGN": 1,
    "INTEGER_INCREMENT": 1, "INTEGER_DECREMENT": 1,
    "FLOAT_INCREMENT": 1, "FLOAT_DECREMENT": 1, "INCREMENT_DECREMENT": 1,
}
DEFAULT_WEIGHT = 2

KILLED, LIVED = "KILLED", "LIVED"
NOT_COVERED, NOT_VIABLE, TIMED_OUT = "NOT COVERED", "NOT VIABLE", "TIMED OUT"


# --------------------------------------------------------------------------- #
# mutation report
# --------------------------------------------------------------------------- #

@dataclass
class Mutant:
    id: str
    type: str
    status: str
    line: int
    column: int
    original: str
    replacement: str
    file: str
    func: str

    @property
    def weight(self) -> int:
        return MUTATOR_WEIGHT.get(self.type, DEFAULT_WEIGHT)


_ID_RE = re.compile(r"^(?P<file>.+?\.go):(?P<qual>[^:]*):(?P<mut>[A-Z_]+#\d+)$")


def _parse_id(mutant_id: str, fallback_file: str) -> tuple[str, str]:
    """(repo_relative_file, function_label) from a gomutants id.

        internal/x/y.go:(*Recv).Method:BRANCH_IF#2  -> (internal/x/y.go, (*Recv).Method)
        internal/x/y.go::STATEMENT_REMOVE#4         -> (internal/x/y.go, <package-level>)
    """
    m = _ID_RE.match(mutant_id)
    if not m:
        return fallback_file, "<unknown>"
    return m.group("file"), (m.group("qual").strip() or "<package-level>")


def load_mutants(path: str, source_root: str) -> list[Mutant]:
    with open(path) as fh:
        data = json.load(fh)
    out: list[Mutant] = []
    for f in data.get("files", []):
        fname = f.get("file_name", "")
        for mm in f.get("mutations", []):
            src, func = _parse_id(mm["id"], fname)
            # gomutants sometimes emits a basename in file_name and a full path
            # in the id; prefer whichever resolves on disk.
            if (not os.path.exists(os.path.join(source_root, src))
                    and fname and os.path.exists(os.path.join(source_root, fname))):
                src = fname
            out.append(Mutant(
                id=mm["id"], type=mm["type"], status=mm["status"],
                line=int(mm.get("line", 0)), column=int(mm.get("column", 0)),
                original=mm.get("original", ""), replacement=mm.get("replacement", ""),
                file=src, func=func,
            ))
    return out


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #

@dataclass
class MutationScores:
    killed: int = 0
    lived: int = 0
    not_covered: int = 0
    not_viable: int = 0
    timed_out: int = 0
    timeout_policy: str = "exclude"  # exclude | kill | survive

    @property
    def _timeout_killed(self) -> int:
        return self.timed_out if self.timeout_policy == "kill" else 0

    @property
    def _timeout_lived(self) -> int:
        return self.timed_out if self.timeout_policy == "survive" else 0

    @property
    def eff_killed(self) -> int:
        return self.killed + self._timeout_killed

    @property
    def eff_lived(self) -> int:
        return self.lived + self._timeout_lived

    @property
    def viable(self) -> int:
        return self.eff_killed + self.eff_lived + self.not_covered

    @property
    def reached(self) -> int:
        return self.eff_killed + self.eff_lived

    @property
    def efficacy(self) -> float:
        d = self.eff_killed + self.eff_lived
        return 100.0 * self.eff_killed / d if d else 0.0

    @property
    def mutation_coverage(self) -> float:
        return 100.0 * self.reached / self.viable if self.viable else 0.0


def score_mutants(mutants: list[Mutant], timeout_policy: str) -> MutationScores:
    c = collections.Counter(m.status for m in mutants)
    return MutationScores(
        killed=c[KILLED], lived=c[LIVED], not_covered=c[NOT_COVERED],
        not_viable=c[NOT_VIABLE], timed_out=c[TIMED_OUT],
        timeout_policy=timeout_policy,
    )


# --------------------------------------------------------------------------- #
# Go coverage profile
# --------------------------------------------------------------------------- #

_COV_RE = re.compile(r"^(?P<block>.+:\d+\.\d+,\d+\.\d+) (?P<n>\d+) (?P<hits>\d+)$")


@dataclass
class CoverProfile:
    """A parsed Go coverage profile. `blocks` maps a block key to (num_stmts,
    covered?) where covered means hit count > 0."""
    blocks: dict[str, tuple[int, bool]] = field(default_factory=dict)

    @classmethod
    def parse(cls, path: str) -> CoverProfile:
        p = cls()
        with open(path) as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln or ln.startswith("mode:"):
                    continue
                m = _COV_RE.match(ln)
                if not m:
                    continue
                key = m.group("block")
                n = int(m.group("n"))
                hit = int(m.group("hits")) > 0
                prev = p.blocks.get(key)
                # merge: covered if covered in any record
                p.blocks[key] = (n, hit or (prev[1] if prev else False))
        return p

    @property
    def covered_keys(self) -> set[str]:
        return {k for k, (_, hit) in self.blocks.items() if hit}

    @property
    def total_stmts(self) -> int:
        return sum(n for n, _ in self.blocks.values())

    @property
    def covered_stmts(self) -> int:
        return sum(n for n, hit in self.blocks.values() if hit)

    @property
    def statement_coverage(self) -> float:
        t = self.total_stmts
        return 100.0 * self.covered_stmts / t if t else 0.0

    def stmts_for(self, keys: set[str]) -> int:
        return sum(self.blocks[k][0] for k in keys if k in self.blocks)


# --------------------------------------------------------------------------- #
# per-test coverage -> contribution map + greedy set cover
# --------------------------------------------------------------------------- #

_PERTEST_RE = re.compile(r"^(?P<pkg>.+?)__(?P<test>Test[A-Za-z0-9_]+)\.out$")


def load_per_test(covdir: str) -> dict[str, set[str]]:
    """Map "pkg::TestName" -> set of covered block keys."""
    out: dict[str, set[str]] = {}
    if not os.path.isdir(covdir):
        return out
    for fn in sorted(os.listdir(covdir)):
        m = _PERTEST_RE.match(fn)
        if not m:
            continue
        name = f"{m.group('pkg').replace('_', '/')}::{m.group('test')}"
        prof = CoverProfile.parse(os.path.join(covdir, fn))
        out[name] = prof.covered_keys
    return out


def greedy_set_cover(sets: dict[str, set]) -> tuple[list[str], set]:
    """Return (chosen order, universe). Greedy: repeatedly take the set adding
    the most still-uncovered elements; ties broken by set size then name."""
    universe: set = set()
    for s in sets.values():
        universe |= s
    remaining = set(universe)
    chosen: list[str] = []
    pool = dict(sets)
    while remaining:
        best = None
        best_gain = -1
        for name, s in sorted(pool.items()):
            gain = len(s & remaining)
            if gain > best_gain or (gain == best_gain and best is not None
                                    and len(s) > len(pool[best])):
                best, best_gain = name, gain
        if best is None or best_gain <= 0:
            break
        chosen.append(best)
        remaining -= pool[best]
        del pool[best]
    return chosen, universe


@dataclass
class TestContribution:
    name: str
    covered: int = 0
    unique_blocks: int = 0    # coverage blocks no other test covers
    unique_mutants: int = 0   # killed mutants this test is the sole reacher of
    total_mutants: int = 0    # killed mutants this test reaches at all
    in_min_cover: bool = False

    @property
    def has_unique_evidence(self) -> bool:
        return self.unique_blocks > 0 or self.unique_mutants > 0

    @property
    def recommendation(self) -> str:
        if self.has_unique_evidence:
            return "KEEP"
        if self.in_min_cover:
            return "KEEP (set-cover essential)"
        return "REVIEW"


# --------------------------------------------------------------------------- #
# git / meta
# --------------------------------------------------------------------------- #

def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _today() -> str:
    return datetime.datetime.now(tz=datetime.UTC).date().isoformat()


def _meta(scope: str) -> str:
    return (f"_Measured: {_today()} — branch `{_git('rev-parse', '--abbrev-ref', 'HEAD')}` "
            f"({_git('rev-parse', '--short', 'HEAD')}) — scope: `{scope}`_")


# --------------------------------------------------------------------------- #
# command: scorecard
# --------------------------------------------------------------------------- #

def cmd_scorecard(a: argparse.Namespace) -> None:
    src_root = a.source_root
    mutants = load_mutants(a.mutation, src_root)
    ms = score_mutants(mutants, a.timeout_policy)

    lines = [f"# Test Quality Scorecard — `{a.module}`", "", _meta(a.scope), ""]
    lines += [
        "The three headline numbers move independently. Adding a test that",
        "executes code without asserting on it *raises* mutation coverage and",
        "*lowers* efficacy — that divergence is the signal, so they are never",
        "blended into one figure.", "",
        "| Metric | Value | Reads as |",
        "|---|---:|---|",
    ]
    if a.coverage and os.path.exists(a.coverage):
        cov = CoverProfile.parse(a.coverage)
        lines.append(
            f"| Statement coverage | {cov.statement_coverage:.1f}% | how much "
            f"code the suite executes ({cov.covered_stmts}/{cov.total_stmts} stmts) |")

    timeout_note = {
        "kill": "counted as killed",
        "survive": "counted as survived",
    }.get(a.timeout_policy, "excluded from efficacy")
    lines += [
        (f"| Mutation coverage | {ms.mutation_coverage:.1f}% | how much code the "
         f"suite executes, at mutant granularity "
         f"({ms.reached}/{ms.viable} viable mutants reached) |"),
        (f"| **Test efficacy** | **{ms.efficacy:.1f}%** | **assertion strength "
         f"where tests do reach — the headline** "
         f"({ms.eff_killed}/{ms.eff_killed + ms.eff_lived} reached mutants killed) |"),
        "",
        "## Mutant census", "",
        "| Outcome | Count | In denominators |",
        "|---|---:|---|",
        f"| Killed | {ms.killed} | efficacy numerator, mutation-coverage numerator |",
        f"| Survived (LIVED) | {ms.lived} | efficacy denominator |",
        f"| Not covered | {ms.not_covered} | mutation-coverage denominator only |",
        f"| Not viable | {ms.not_viable} | excluded from all denominators |",
        f"| Timed out | {ms.timed_out} | policy: **{a.timeout_policy}** ({timeout_note}) |",
        "",
    ]

    # per-package breakdown
    per_pkg: dict[str, MutationScores] = collections.defaultdict(
        lambda: MutationScores(timeout_policy=a.timeout_policy))
    for m in mutants:
        pkg = os.path.dirname(m.file) or "."
        s = per_pkg[pkg]
        if m.status == KILLED: s.killed += 1
        elif m.status == LIVED: s.lived += 1
        elif m.status == NOT_COVERED: s.not_covered += 1
        elif m.status == NOT_VIABLE: s.not_viable += 1
        elif m.status == TIMED_OUT: s.timed_out += 1

    lines += ["## Per-package", "",
              "| Package | Efficacy | Mutation cov | Killed | Survived | Not covered |",
              "|---|---:|---:|---:|---:|---:|"]
    for pkg in sorted(per_pkg):
        s = per_pkg[pkg]
        if s.viable == 0:  # only NOT VIABLE mutants -- no signal
            continue
        lines.append(f"| `{pkg}` | {s.efficacy:.0f}% | {s.mutation_coverage:.0f}% | "
                     f"{s.eff_killed} | {s.eff_lived} | {s.not_covered} |")
    lines.append("")

    _write(a.out, "\n".join(lines))


# --------------------------------------------------------------------------- #
# command: findings
# --------------------------------------------------------------------------- #

def _source_context(src_root: str, rel: str, line: int, radius: int = 4) -> str:
    path = os.path.join(src_root, rel)
    try:
        with open(path) as fh:
            all_lines = fh.readlines()
    except OSError:
        return ""
    lo = max(1, line - radius)
    hi = min(len(all_lines), line + radius)
    buf = []
    for n in range(lo, hi + 1):
        mark = ">>" if n == line else "  "
        buf.append(f"{mark} {n:5d}  {all_lines[n - 1].rstrip()}")
    return "\n".join(buf)


def _load_gocognit(path: str | None) -> dict[tuple[str, str], int]:
    """(file, funcName) -> complexity. gocognit -json emits one object per line
    OR a single JSON array; handle both."""
    out: dict[tuple[str, str], int] = {}
    if not path or not os.path.exists(path):
        return out
    with open(path) as fh:
        text = fh.read().strip()
    records = []
    if text.startswith("["):
        records = json.loads(text)
    else:
        for ln in text.splitlines():
            ln = ln.strip()
            if ln:
                records.append(json.loads(ln))
    for r in records:
        pos = r.get("Pos", {})
        fn = pos.get("Filename", "")
        # normalise to repo-relative-ish: keep from "internal/" or "sdk/" on
        idx = fn.find("/internal/")
        if idx == -1:
            idx = fn.find("/sdk/")
        rel = fn[idx + 1:] if idx != -1 else fn
        out[(rel, r.get("FuncName", ""))] = int(r.get("Complexity", 0))
    return out


def _cx(cognit: dict[tuple[str, str], int], ffile: str, func: str) -> int | None:
    """Look up cognitive complexity. gomutants func labels ((*Recv).Method,
    Func, <package-level>) match gocognit FuncName exactly; fall back to the
    trailing segment."""
    return cognit.get((ffile, func)) or cognit.get((ffile, func.split(".")[-1]))


def _covering_tests(func_file: str, per_test: dict[str, set[str]]) -> list[str]:
    """Best-effort: which per-test profiles touched any block in this file."""
    hits = []
    for name, keys in per_test.items():
        if any(k.startswith(func_file + ":") or ("/" + func_file + ":") in k for k in keys):
            hits.append(name.split("::")[-1])
    return sorted(set(hits))


def _tests_hitting_lines(spans: dict[str, list[tuple[str, int, int]]],
                         rel_file: str, lines: set[int]) -> list[str]:
    """Per-test names whose covered spans include any of `lines` in `rel_file`."""
    out = []
    for test, sp in spans.items():
        if any(_path_suffix_match(f, rel_file) and sl <= ln <= el
               for f, sl, el in sp for ln in lines):
            out.append(test)
    return sorted(out)


def cmd_findings(a: argparse.Namespace) -> None:
    src_root = a.source_root
    mutants = load_mutants(a.mutation, src_root)
    per_test = load_per_test(a.covdir) if a.covdir else {}
    spans = _per_test_spans(a.covdir) if a.covdir else {}
    cognit = _load_gocognit(a.gocognit)

    by_func: dict[tuple[str, str], list[Mutant]] = collections.defaultdict(list)
    for m in mutants:
        by_func[(m.file, m.func)].append(m)

    def weighted(ms: list[Mutant], status: str) -> int:
        return sum(x.weight for x in ms if x.status == status)

    lived_groups = sorted(
        ((k, v) for k, v in by_func.items() if any(m.status == LIVED for m in v)),
        key=lambda kv: weighted(kv[1], LIVED), reverse=True)
    gap_groups = sorted(
        ((k, v) for k, v in by_func.items() if any(m.status == NOT_COVERED for m in v)),
        key=lambda kv: sum(1 for m in kv[1] if m.status == NOT_COVERED), reverse=True)

    L = [f"# Test Quality Findings — `{a.module}`", "", _meta(a.scope), ""]
    L += [
        "Two independent fixes live here. **Section A** survivors need a",
        "*stronger or new assertion* on code that is already executed.",
        "**Section B** gaps need a *new test that exercises the function at all*.",
        "**Section C** lists tests with no unique quantitative contribution —",
        "consolidation candidates that need a human/LLM semantic call, never an",
        "automatic delete.", "",
        "## How to verify a fix", "",
        "After adding/strengthening a test, re-measure just the mutant — this",
        "skips the incremental cache so the verdict is fresh:", "",
        "```bash",
        "gomutants -run-mutant-id '<mutant id from the tables below>' \\",
        "  -o /tmp/gomutants-verify.json ./<package>",
        "```",
        "",
        "A genuine fix flips the mutant `LIVED → KILLED`. If it does not, the",
        "assertion is not actually pinning the mutated behaviour.", "",
        "---", "",
        "## A. Weak assertions — surviving mutants", "",
        "Ranked by weighted survivor count (logic/return mutants weigh 3,",
        "statement/expression removal 2, arithmetic/counters 1).", "",
    ]

    for i, ((ffile, func), ms) in enumerate(lived_groups, 1):
        survivors = [m for m in ms if m.status == LIVED]
        w = weighted(ms, LIVED)
        L.append(f"### A{i}. `{ffile}` · `{func}` — weighted {w}, {len(survivors)} survivor(s)")
        surv_lines = {m.line for m in survivors}
        cov_tests = _tests_hitting_lines(spans, ffile, surv_lines) or _covering_tests(ffile, per_test)
        if cov_tests:
            L.append(f"- Covering tests: {', '.join('`' + t + '`' for t in cov_tests[:12])}"
                     + (" …" if len(cov_tests) > 12 else ""))
        cx = _cx(cognit, ffile, func)
        if cx:
            L.append(f"- Cognitive complexity: {cx}")
        L.append("")
        L.append("| Line | Mutator | Change | Mutant id |")
        L.append("|---:|---|---|---|")
        for m in sorted(survivors, key=lambda m: m.line):
            orig = m.original.replace("\n", "\\n").replace("|", "\\|")[:60]
            repl = m.replacement.replace("\n", "\\n").replace("|", "\\|")[:40]
            L.append(f"| {m.line} | {m.type} | `{orig}` → `{repl}` | `{m.id}` |")
        L.append("")
        ctx = _source_context(src_root, ffile, survivors[0].line)
        if ctx:
            L += ["```go", ctx, "```", ""]
        L += ["**Recommended:** add or tighten an assertion in a covering test so",
              "that mutating the lines above changes an observed output or error.", "",
              ""]

    L += ["---", "", "## B. Coverage gaps — never-executed mutants", "",
          "These functions have mutants that no test reached. The fix is a new",
          "test that calls the function with inputs reaching the listed lines.", ""]
    for i, ((ffile, func), ms) in enumerate(gap_groups, 1):
        gaps = [m for m in ms if m.status == NOT_COVERED]
        L.append(f"### B{i}. `{ffile}` · `{func}` — {len(gaps)} uncovered mutant(s)")
        cx = _cx(cognit, ffile, func)
        if cx:
            L.append(f"- Cognitive complexity: {cx}")
        lines_hit = sorted({m.line for m in gaps})
        L.append(f"- Lines needing exercise: {', '.join(map(str, lines_hit))}")
        L.append("")

    # Section C: contribution / redundancy
    contrib_path = a.contribution
    if contrib_path and os.path.exists(contrib_path):
        with open(contrib_path) as fh:
            contrib = json.load(fh)
        mdim = contrib.get("mutation_dimension")
        review = [t for t in contrib.get("tests", []) if t["recommendation"] == "REVIEW"]
        L += ["---", "", "## C. Redundancy & consolidation candidates", "",
              f"{len(review)} test(s) contribute no unique coverage block"
              + (", no solely-reached killed mutant," if mdim else "")
              + " and are not in the greedy minimal set.", "",
              "**Expect most of these to be keeps.** Coverage overlap is not",
              "behavioural overlap: a test that names a distinct branch, error",
              "path, or contract (\"...WhenSecretConfigured\", \"...RejectsUnknownRole\")",
              "is unique evidence even at zero unique blocks. Only fold a test into",
              "a sibling and delete it when the sibling already exercises the same",
              "scenario and the name adds nothing a reader would miss.", "",
              "| Test | Unique blocks | " + ("Sole-kill | " if mdim else "")
              + "In minimal set | Call |",
              "|---|---:|" + ("---:|" if mdim else "") + ":---:|---|"]
        for t in sorted(review, key=lambda t: t["name"]):
            mins = "yes" if t.get("in_min_cover") else "no"
            row = f"| `{t['name']}` | {t['unique_blocks']} | "
            if mdim:
                row += f"{t.get('unique_mutants_solely_reached', 0)} | "
            row += f"{mins} | REVIEW |"
            L.append(row)
        L.append("")

    # Section D: risk
    risk = []
    for (ffile, func), ms in by_func.items():
        surv_w = weighted(ms, LIVED) + weighted(ms, NOT_COVERED)
        cx = _cx(cognit, ffile, func)
        if cx and cx >= 10 and surv_w > 0:
            risk.append((ffile, func, cx, surv_w,
                         sum(1 for m in ms if m.status in (LIVED, NOT_COVERED))))
    if risk:
        L += ["---", "", "## D. Risk — complex code, weak mutation coverage", "",
              "High cognitive complexity and surviving/uncovered mutants together.",
              "Prioritise these for new tests.", "",
              "| File · Function | Complexity | Survivors+gaps | Weighted |",
              "|---|---:|---:|---:|"]
        for ffile, func, cx, w, n in sorted(risk, key=lambda r: (r[2] * r[3]), reverse=True):
            L.append(f"| `{ffile}` · `{func}` | {cx} | {n} | {w} |")
        L.append("")

    _write(a.out, "\n".join(L))


# --------------------------------------------------------------------------- #
# command: contribution
# --------------------------------------------------------------------------- #

def cmd_contribution(a: argparse.Namespace) -> None:
    per_test = load_per_test(a.covdir)
    if not per_test:
        sys.exit(f"no per-test profiles found under {a.covdir}")

    # Optionally weight the "sole reacher of a killed mutant" signal: a killed
    # mutant whose line only one test's coverage profile reaches can only have
    # been killed by that test. Cheap -- derived from data already on disk.
    mutant_reach: dict[str, set[str]] = {}
    if a.mutation and os.path.exists(a.mutation):
        killed = [m for m in load_mutants(a.mutation, a.source_root)
                  if m.status == KILLED]
        spans = _per_test_spans(a.covdir)
        for m in killed:
            reachers = {name for name, blocks in spans.items()
                        if _spans_contain(blocks, m.file, m.line)}
            if reachers:
                mutant_reach[m.id] = reachers
    mutation_dim = bool(mutant_reach)

    names = sorted(per_test)
    contribs: dict[str, TestContribution] = {
        n: TestContribution(name=n.split("::")[-1], covered=len(per_test[n])) for n in names
    }

    # unique coverage
    for n in names:
        others: set[str] = set()
        for m in names:
            if m != n:
                others |= per_test[m]
        contribs[n].unique_blocks = len(per_test[n] - others)

    cover_order, cover_universe = greedy_set_cover(per_test)
    for n in cover_order:
        contribs[n].in_min_cover = True

    # sole-reacher of a killed mutant == uniquely enabled that kill
    if mutation_dim:
        by_name = {n.split("::")[-1]: n for n in names}
        for reachers in mutant_reach.values():
            for short in reachers:
                n = by_name.get(short)
                if n:
                    contribs[n].total_mutants += 1
            if len(reachers) == 1:
                only = next(iter(reachers))
                n = by_name.get(only)
                if n:
                    contribs[n].unique_mutants += 1

    total = len(names)
    review = [c for c in contribs.values() if c.recommendation == "REVIEW"]

    out_json = {
        "generated": _today(),
        "module": a.module,
        "scope": a.scope,
        "mutation_dimension": mutation_dim,
        "totals": {
            "tests": total,
            "coverage_universe_blocks": len(cover_universe),
            "minimal_cover_set_size": len(cover_order),
            "review_candidates": len(review),
            "keep": total - len(review),
        },
        "tests": [
            {
                "name": c.name,
                "covered_blocks": c.covered,
                "unique_blocks": c.unique_blocks,
                "unique_mutants_solely_reached": c.unique_mutants,
                "killed_mutants_reached": c.total_mutants,
                "in_min_cover": c.in_min_cover,
                "recommendation": c.recommendation,
            }
            for c in sorted(contribs.values(), key=lambda c: c.name)
        ],
    }
    _write(a.out_json, json.dumps(out_json, indent=2))

    L = [f"# Test Contribution Map — `{a.module}`", "", _meta(a.scope), "",
         f"- Tests analysed: **{total}**",
         f"- Coverage universe: {len(cover_universe)} statement blocks",
         (f"- Greedy minimal set preserving that coverage: **{len(cover_order)} "
          f"tests** ({total - len(cover_order)} outside it)"),
         ]
    if mutation_dim:
        L.append("- `Sole-kill` column: killed mutants whose line no other "
                 "test's coverage reaches — that test is the only possible killer")
    L += ["",
          "`REVIEW` = no unique coverage block"
          + (" and no solely-reached killed mutant" if mutation_dim else "")
          + " and not in the greedy minimal set. Not a delete order — coverage",
          "overlap is not behavioural overlap; a named branch or contract is",
          "unique evidence even at zero unique blocks.", "",
          "| Test | Blocks | Unique blocks | "
          + ("Sole-kill | " if mutation_dim else "")
          + "In min set | Recommendation |",
          "|---|---:|---:|" + ("---:|" if mutation_dim else "") + ":---:|---|"]
    for c in sorted(contribs.values(), key=lambda c: (c.recommendation != "REVIEW", c.name)):
        row = f"| `{c.name}` | {c.covered} | {c.unique_blocks} | "
        if mutation_dim:
            row += f"{c.unique_mutants} | "
        row += f"{'Y' if c.in_min_cover else '·'} | {c.recommendation} |"
        L.append(row)
    L.append("")
    _write(a.out_md, "\n".join(L))


_SPAN_RE = re.compile(r"^(?P<file>.+):(?P<sl>\d+)\.\d+,(?P<el>\d+)\.\d+ \d+ (?P<hits>\d+)$")


def _per_test_spans(covdir: str) -> dict[str, list[tuple[str, int, int]]]:
    """test short-name -> list of (file, start_line, end_line) it covers."""
    out: dict[str, list[tuple[str, int, int]]] = {}
    if not os.path.isdir(covdir):
        return out
    for fn in sorted(os.listdir(covdir)):
        m = _PERTEST_RE.match(fn)
        if not m:
            continue
        spans: list[tuple[str, int, int]] = []
        with open(os.path.join(covdir, fn)) as fh:
            for ln in fh:
                sm = _SPAN_RE.match(ln.strip())
                if sm and int(sm.group("hits")) > 0:
                    spans.append((sm.group("file"), int(sm.group("sl")), int(sm.group("el"))))
        out[m.group("test")] = spans
    return out


def _path_suffix_match(full: str, rel: str) -> bool:
    """True when `rel` is `full` or a path-segment-aligned suffix of it, so
    internal/x/c.go matches .../connect-control/internal/x/c.go but sdk/internal/
    x/c.go does not match internal/x/c.go."""
    return full == rel or full.endswith("/" + rel)


def _spans_contain(spans: list[tuple[str, int, int]], rel_file: str, line: int) -> bool:
    for f, sl, el in spans:
        if _path_suffix_match(f, rel_file) and sl <= line <= el:
            return True
    return False


# --------------------------------------------------------------------------- #

def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content.rstrip() + "\n")
    print(f"wrote {path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--module", default="github.com/dioad/connect-control")
    p.add_argument("--scope", default="./internal/...")
    p.add_argument("--source-root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scorecard")
    s.add_argument("--mutation", required=True)
    s.add_argument("--coverage")
    s.add_argument("--timeout-policy", choices=["exclude", "kill", "survive"],
                   default="exclude")
    s.add_argument("--out", default=".analysis/test-quality/scorecard.md")
    s.set_defaults(func=cmd_scorecard)

    f = sub.add_parser("findings")
    f.add_argument("--mutation", required=True)
    f.add_argument("--covdir", default=".analysis/test-quality/per-test")
    f.add_argument("--gocognit")
    f.add_argument("--contribution", default=".analysis/test-quality/contribution.json")
    f.add_argument("--out", default="doc/test-quality-findings.md")
    f.set_defaults(func=cmd_findings)

    c = sub.add_parser("contribution")
    c.add_argument("--covdir", default=".analysis/test-quality/per-test")
    c.add_argument("--mutation",
                   help="mutation report; enables the sole-reacher-of-a-killed-mutant column")
    c.add_argument("--out-md", default=".analysis/test-quality/contribution.md")
    c.add_argument("--out-json", default=".analysis/test-quality/contribution.json")
    c.set_defaults(func=cmd_contribution)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
