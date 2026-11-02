#!/bin/sh
# Offline integration checks using a local clone and the real accepted JARs.
# No robot, network, application startup, or native library loading.
set -eu
[ "$#" -eq 1 ] || { echo 'Usage: sh tools/test_build_java.sh DEPENDENCY_DIR' >&2; exit 2; }
deps=$(CDPATH= cd -P "$1" && pwd)
root=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d "${TMPDIR:-/tmp}/robotcontroller-build-test.XXXXXX")
printf 'Test files retained at: %s\n' "$scratch"
git -c core.autocrlf=false clone --no-hardlinks "$root" "$scratch/source" > "$scratch/clone.log" 2>&1
cp "$root/tools/build_java.sh" "$scratch/source/tools/build_java.sh"
git -C "$scratch/source" -c core.autocrlf=false add tools/build_java.sh
git -C "$scratch/source" -c user.name='Offline Test' -c user.email='offline@example.invalid' \
    commit --allow-empty -m 'Prepare local offline build fixture' > "$scratch/commit.log"
script=$scratch/source/tools/build_java.sh
sh -n "$script"
echo 'PASS: shell syntax'
expect_error() {
    label=$1; message=$2; shift 2
    if "$@" > "$scratch/error.log" 2>&1; then
        echo "FAIL: $label unexpectedly succeeded" >&2; exit 1
    fi
    grep -F "$message" "$scratch/error.log" >/dev/null || { cat "$scratch/error.log"; exit 1; }
    printf 'PASS: %s\n' "$label"
}
expect_error 'unknown option' 'Unknown argument' sh "$script" --unknown
expect_error 'missing value' 'Missing value' sh "$script" --output-dir
expect_error 'required options' 'Both directory options' sh "$script"
expect_error 'duplicate option' 'Duplicate' sh "$script" --dependency-dir "$deps" --dependency-dir "$deps"
mkdir "$scratch/existing"
printf 'unchanged\n' > "$scratch/existing/sentinel"
expect_error 'existing output' 'Output already exists' sh "$script" --dependency-dir "$deps" --output-dir "$scratch/existing"
[ "$(cat "$scratch/existing/sentinel")" = unchanged ]
expect_error 'output in worktree' 'outside the Git worktree' sh "$script" --dependency-dir "$deps" --output-dir "$scratch/source/new-output"
mkdir "$scratch/missing-deps"
expect_error 'missing dependency' 'Missing dependency' sh "$script" --dependency-dir "$scratch/missing-deps" --output-dir "$scratch/no-output"
[ ! -e "$scratch/no-output" ]
printf 'wrong bytes\n' > "$scratch/missing-deps/core-2.2.jar"
expect_error 'wrong dependency hash' 'Dependency hash mismatch' sh "$script" --dependency-dir "$scratch/missing-deps" --output-dir "$scratch/no-output"
[ ! -e "$scratch/no-output" ]
mkdir "$scratch/fake-jdk" "$scratch/fake-jdk/bin"
for name in java javac jar; do
    printf '#!/bin/sh\necho '\''openjdk version "17.0.1"'\'' >&2\n' > "$scratch/fake-jdk/bin/$name"
    chmod +x "$scratch/fake-jdk/bin/$name"
done
(
    JAVA_HOME=$scratch/fake-jdk
    export JAVA_HOME
    expect_error 'non-Java-8 runtime' 'Java 8 is required' sh "$script" --dependency-dir "$deps" --output-dir "$scratch/no-output"
)
[ ! -e "$scratch/no-output" ]
printf '#!/bin/sh\necho '\''openjdk version "1.8.0_502"'\'' >&2\n' > "$scratch/fake-jdk/bin/java"
(
    JAVA_HOME=$scratch/fake-jdk
    export JAVA_HOME
    expect_error 'non-Java-8 compiler' 'Javac 8 is required' sh "$script" --dependency-dir "$deps" --output-dir "$scratch/no-output"
)
if ln -s "$scratch/existing" "$scratch/output-link" 2>/dev/null; then
    expect_error 'symlink output' 'Output already exists' sh "$script" --dependency-dir "$deps" --output-dir "$scratch/output-link"
else
    echo 'SKIP: symlink creation unavailable'
fi
printf 'untracked\n' > "$scratch/source/src/untracked.txt"
expect_error 'untracked protected input' 'Production/test inputs contain' sh "$script" --dependency-dir "$deps" --output-dir "$scratch/no-output"
# Remove only this explicitly created file, never a directory tree.
rm "$scratch/source/src/untracked.txt"
printf '// test change\n' >> "$scratch/source/src/main/App.java"
expect_error 'changed baseline input' 'differ from baseline' sh "$script" --dependency-dir "$deps" --output-dir "$scratch/no-output"
git -C "$scratch/source" restore -- src/main/App.java
# Build from a different CWD with spaces in the output path.
sh "$script" --dependency-dir "$deps" --output-dir "$scratch/java output" > "$scratch/build.log" 2>&1 || { cat "$scratch/build.log"; exit 1; }
grep -F 'Build status: PASS' "$scratch/java output/java-build-report.txt" >/dev/null
grep -F 'Generated class count: 49' "$scratch/java output/java-build-report.txt" >/dev/null
test -f "$scratch/java output/RobotController/RobotController.jar"
test -z "$(find "$scratch/java output/RobotController/native" -type f)"
expect_error 'successful output never reused' 'Output already exists' sh "$script" --dependency-dir "$deps" --output-dir "$scratch/java output"
echo 'PASS: actual Java 8 compile, 49 classes, manifest, copied dependencies, no overwrite'
echo 'PASS: all offline checks (macOS/Edison execution remains untested)'
