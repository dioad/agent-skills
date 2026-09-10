#!/usr/bin/env bash
# measure.sh -- collect the raw inputs test_quality.py turns into artifacts.
#
# Produces, under .analysis/test-quality/ :
#   coverage.out          whole-suite Go statement coverage profile
#   mutation-report.json  gomutants outcomes (incremental via .gomutants-cache)
#   mutation-report.html  interactive Stryker viewer
#   gocognit.jsonl        cognitive complexity per function   (if gocognit present)
#   per-test/*.out        one coverage profile per test        (--per-test PKG)
#
# Then renders:
#   .analysis/test-quality/scorecard.md
#   .analysis/test-quality/contribution.md + contribution.json   (if --per-test)
#   doc/test-quality-findings.md
#
# Usage:
#   .claude/skills/test-quality/measure.sh                       # full, ./internal/...
#   .claude/skills/test-quality/measure.sh --scope ./sdk/...
#   .claude/skills/test-quality/measure.sh --delta               # only lines changed vs master
#   .claude/skills/test-quality/measure.sh --per-test ./internal/cmd/entitlements/service
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

OUT=".analysis/test-quality"
SCOPE="./internal/..."
CHANGED_SINCE=""
TIMEOUT_POLICY="exclude"
PER_TEST_PKGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --scope)          SCOPE="$2"; shift 2 ;;
    --delta)          CHANGED_SINCE="master"; shift ;;
    --changed-since)  CHANGED_SINCE="$2"; shift 2 ;;
    --timeout-policy) TIMEOUT_POLICY="$2"; shift 2 ;;
    --per-test)       PER_TEST_PKGS+=("$2"); shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$OUT/per-test"
# go.work makes `go list -m` print every workspace module; read the local one.
MODULE="$(awk '/^module /{print $2; exit}' go.mod)"

echo "==> whole-suite coverage ($SCOPE)"
go test -count=1 -covermode=set -coverprofile="$OUT/coverage.out" "$SCOPE" \
  >"$OUT/coverage.test.log" 2>&1 || {
    echo "    (some packages failed to build/test -- see $OUT/coverage.test.log)"; }

echo "==> mutation testing ($SCOPE)"
GOMUTANTS_ARGS=(
  -cache "$OUT/.gomutants-cache.json"
  -output "$OUT/mutation-report.json"
  -html-output "$OUT/mutation-report.html"
  -quiet
)
[ -n "$CHANGED_SINCE" ] && GOMUTANTS_ARGS+=(-changed-since "$CHANGED_SINCE")
gomutants "${GOMUTANTS_ARGS[@]}" "$SCOPE" || true   # non-zero exit = thresholds, not failure

if command -v gocognit >/dev/null 2>&1; then
  echo "==> cognitive complexity"
  SCOPE_DIR="${SCOPE%/...}"; SCOPE_DIR="${SCOPE_DIR#./}"
  gocognit -json "${SCOPE_DIR:-.}" > "$OUT/gocognit.jsonl" 2>/dev/null || true
fi

for PKG in "${PER_TEST_PKGS[@]:-}"; do
  [ -z "$PKG" ] && continue
  SLUG="$(echo "$PKG" | sed 's#^\./##; s#\.\.\.##; s#/#_#g; s#_$##')"
  echo "==> per-test coverage: $PKG"
  TESTS="$(go test -list '^Test' "$PKG" 2>/dev/null | grep -E '^Test' || true)"
  echo "    $(printf '%s\n' "$TESTS" | grep -c . || true) tests"
  printf '%s\n' "$TESTS" | while IFS= read -r T; do
    [ -z "$T" ] && continue
    go test -count=1 -covermode=set -run "^${T}\$" \
      -coverprofile="$OUT/per-test/${SLUG}__${T}.out" "$PKG" \
      >/dev/null 2>&1 || rm -f "$OUT/per-test/${SLUG}__${T}.out"
  done
done

echo "==> rendering artifacts"
python3 "$HERE/test_quality.py" --module "$MODULE" --scope "$SCOPE" \
  scorecard --mutation "$OUT/mutation-report.json" --coverage "$OUT/coverage.out" \
  --timeout-policy "$TIMEOUT_POLICY" --out "$OUT/scorecard.md"

CONTRIB_ARG=()
if compgen -G "$OUT/per-test/*.out" >/dev/null; then
  python3 "$HERE/test_quality.py" --module "$MODULE" --scope "$SCOPE" \
    contribution --covdir "$OUT/per-test" --mutation "$OUT/mutation-report.json" \
    --out-md "$OUT/contribution.md" --out-json "$OUT/contribution.json"
  CONTRIB_ARG=(--contribution "$OUT/contribution.json")
fi

python3 "$HERE/test_quality.py" --module "$MODULE" --scope "$SCOPE" \
  findings --mutation "$OUT/mutation-report.json" \
  --covdir "$OUT/per-test" --gocognit "$OUT/gocognit.jsonl" \
  "${CONTRIB_ARG[@]}" --out doc/test-quality-findings.md

echo
echo "scorecard : $OUT/scorecard.md"
[ -f "$OUT/contribution.md" ] && echo "contribution: $OUT/contribution.md"
echo "findings  : doc/test-quality-findings.md"
echo "html      : $OUT/mutation-report.html"
