#!/bin/sh
set -eu
cd "$(dirname "$0")"
UNIT=$(pwd)
STUDY_ROOT=${TEMPER_GLASS_STUDY_ROOT:-$(cd ../.. && pwd)}
rm -f results/inputs.sha256
(cd "$STUDY_ROOT" && shasum -a 256 -c "$UNIT/inputs.sha256")
rustfmt --check adapter.rs
BUILD=$(mktemp -d /private/tmp/temper-r7-calibration.XXXXXX)
trap 'rm -rf "$BUILD"' EXIT
printf '#[allow(dead_code)]\nmod bench {\n' > "$BUILD/main.rs"
cat "$STUDY_ROOT/bench_validation/bench.rs" adapter.rs >> "$BUILD/main.rs"
printf '\n}\nfn main() -> Result<(), Box<dyn std::error::Error>> { bench::run_r7() }\n' >> "$BUILD/main.rs"
rustc --edition=2021 -D warnings --test "$BUILD/main.rs" -o "$BUILD/tests"
"$BUILD/tests" > "$BUILD/tests.txt"
clippy-driver --edition=2021 -D warnings "$BUILD/main.rs" -o "$BUILD/clippy"
rustc --edition=2021 -O -D warnings "$BUILD/main.rs" -o "$BUILD/evaluate"
if [ "$#" -gt 0 ]; then
    "$BUILD/evaluate" "$@"
    exit
fi
rustc --edition=2021 -O -D warnings "$STUDY_ROOT/bench_validation/synthetic.rs" -o "$BUILD/synthetic"
"$BUILD/synthetic" "$BUILD/data"
add_identities() {
    for meta in "$1/"*.txt; do
        cat >> "$meta" <<'IDENTITY'
geometry_sha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
bom_sha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
bond_batch_id=SYNTHETIC-demo-bond
join_process_revision=SYNTHETIC-demo-join
IDENTITY
    done
}
add_identities "$BUILD/data"
mkdir -p "$BUILD/results"
for case in holdout weak_contact hidden_dynamics; do
    "$BUILD/evaluate" "$BUILD/data/SYNTHETIC-fit.csv" "$BUILD/data/SYNTHETIC-fit.txt" "$BUILD/data/SYNTHETIC-$case.csv" "$BUILD/data/SYNTHETIC-$case.txt" > "$BUILD/results/SYNTHETIC-$case.txt"
done
sed 's/reference_transition_s=0.01/reference_transition_s=0.25/' "$BUILD/data/SYNTHETIC-holdout.txt" > "$BUILD/slow-reference.txt"
"$BUILD/evaluate" "$BUILD/data/SYNTHETIC-fit.csv" "$BUILD/data/SYNTHETIC-fit.txt" "$BUILD/data/SYNTHETIC-holdout.csv" "$BUILD/slow-reference.txt" > "$BUILD/results/SYNTHETIC-slow-reference.txt"
rg -q 'r7_response_screen=INDETERMINATE' "$BUILD/results/SYNTHETIC-slow-reference.txt"
rg -q 'surrogate_transfer=SURROGATE_WITHIN_DECLARED_UNCERTAINTY'  "$BUILD/results/SYNTHETIC-holdout.txt"
rg -q 'r7_error_screen=OUTSIDE_PROPOSED_SCREEN' "$BUILD/results/SYNTHETIC-holdout.txt"
rg -q 'r7_response_screen=OUTSIDE_PROPOSED_SCREEN' "$BUILD/results/SYNTHETIC-holdout.txt"
rg -q 'surrogate_transfer=REJECT_TRANSFER' "$BUILD/results/SYNTHETIC-weak_contact.txt"
rg -q 'surrogate_transfer=REJECT_TRANSFER' "$BUILD/results/SYNTHETIC-hidden_dynamics.txt"
sed 's/pan_id=SYNTHETIC-pan-160/pan_id=SYNTHETIC-pan-100/' "$BUILD/data/SYNTHETIC-holdout.txt" > "$BUILD/same-pan.txt"
if "$BUILD/evaluate" "$BUILD/data/SYNTHETIC-fit.csv" "$BUILD/data/SYNTHETIC-fit.txt" "$BUILD/data/SYNTHETIC-holdout.csv" "$BUILD/same-pan.txt" > "$BUILD/reject.stdout" 2> "$BUILD/results/same-pan-rejection.txt"; then
    echo 'ERROR: same-pan holdout accepted' >&2; exit 1
fi
rg -q 'whole-pan holdout' "$BUILD/results/same-pan-rejection.txt"
# These pairs pass the earlier pan/configuration checks, then violate one
# independent-acquisition requirement at a time.
for fault in run_id raw_origin identical_bytes; do
    csv="$BUILD/data/SYNTHETIC-holdout.csv"
    meta="$BUILD/data/SYNTHETIC-holdout.txt"
    case "$fault" in
        run_id)
            sed 's/run_id=SYNTHETIC-holdout/run_id=SYNTHETIC-fit/' "$meta" > "$BUILD/reused.txt"
            meta="$BUILD/reused.txt" ;;
        raw_origin)
            sed 's/raw_origin=SYNTHETIC-analytic-holdout/raw_origin=SYNTHETIC-analytic-fit/' "$meta" > "$BUILD/reused.txt"
            meta="$BUILD/reused.txt" ;;
        identical_bytes) csv="$BUILD/data/SYNTHETIC-fit.csv" ;;
    esac
    if "$BUILD/evaluate" "$BUILD/data/SYNTHETIC-fit.csv" "$BUILD/data/SYNTHETIC-fit.txt" "$csv" "$meta" > "$BUILD/reject.stdout" 2> "$BUILD/results/$fault-rejection.txt"; then
        echo "ERROR: reused acquisition accepted: $fault" >&2; exit 1
    fi
    rg -q 'holdout acquisition must have independent run, origin and bytes' "$BUILD/results/$fault-rejection.txt"
done
# Parameterize a temporary copy of the pinned analytic generator. The original
# source and original slow/biased rejection fixture remain unchanged.
sed -e 's/("fit", "fit", 100., 1.5, 0.98, 0.)/("fit", "fit", 100., 0.5, 1.0, 0.)/' -e 's/("holdout", "holdout", 160., 1.5, 0.98, 0.001)/("holdout", "holdout", 160., 0.5, 1.0, 0.001)/' "$STUDY_ROOT/bench_validation/synthetic.rs" > "$BUILD/fast.rs"
rustc --edition=2021 -O -D warnings "$BUILD/fast.rs" -o "$BUILD/fast"
"$BUILD/fast" "$BUILD/fast-data"
add_identities "$BUILD/fast-data"
"$BUILD/evaluate" "$BUILD/fast-data/SYNTHETIC-fit.csv" "$BUILD/fast-data/SYNTHETIC-fit.txt" "$BUILD/fast-data/SYNTHETIC-holdout.csv" "$BUILD/fast-data/SYNTHETIC-holdout.txt" > "$BUILD/results/SYNTHETIC-passing.txt"
rg -q 'r7_error_screen=WITHIN_PROPOSED_SCREEN' "$BUILD/results/SYNTHETIC-passing.txt"
rg -q 'r7_response_screen=WITHIN_PROPOSED_SCREEN' "$BUILD/results/SYNTHETIC-passing.txt"
rg -q 'physical_validation=NOT_RUN' "$BUILD/results/SYNTHETIC-passing.txt"
if "$BUILD/evaluate" "$STUDY_ROOT/bench_validation/templates/samples.csv" "$STUDY_ROOT/bench_validation/templates/run.txt" "$BUILD/data/SYNTHETIC-holdout.csv" "$BUILD/data/SYNTHETIC-holdout.txt" > "$BUILD/reject.stdout" 2> "$BUILD/results/empty-template-rejection.txt"; then
    echo 'ERROR: empty template accepted' >&2; exit 1
fi
rg -q 'NOT_RUN' "$BUILD/results/empty-template-rejection.txt"
mkdir -p results
cp "$BUILD/results/"*.txt results/
sed '${/^$/d;}' "$BUILD/tests.txt" > results/tests.txt
shasum -a 256 adapter.rs run.sh results/*.txt > results/inputs.sha256
cat results/SYNTHETIC-holdout.txt
