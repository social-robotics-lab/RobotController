#!/bin/sh
# Build only; never load RobotController or the JNI library.
set -eu
LC_ALL=C
export LC_ALL
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
    printf '%s\n' 'Usage: sh tools/build_java.sh --dependency-dir DIR --output-dir NEW_DIR' \
        'Java 8 JDK: set JAVA_HOME, or put java, javac, jar on PATH.' \
        'NEW_DIR must not exist and must be outside this worktree.'
}
deps=
out=
while [ "$#" -gt 0 ]; do
    case $1 in
        --dependency-dir|--output-dir)
            [ "$#" -ge 2 ] && [ -n "$2" ] || fail "Missing value for $1"
            case $2 in --*) fail "Missing value for $1" ;; esac
            case $1 in
                --dependency-dir) [ -z "$deps" ] || fail 'Duplicate --dependency-dir'; deps=$2 ;;
                --output-dir) [ -z "$out" ] || fail 'Duplicate --output-dir'; out=$2 ;;
            esac
            shift 2 ;;
        --help) usage; exit 0 ;;
        *) fail "Unknown argument: $1" ;;
    esac
done
[ -n "$deps" ] && [ -n "$out" ] || { usage >&2; fail 'Both directory options are required'; }
root=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)
case $deps in /*) ;; *) deps=$PWD/$deps ;; esac
case $out in /*) ;; *) out=$PWD/$out ;; esac
# Resolve existing parents physically, including symlinks; never mkdir -p an output.
[ -d "$deps" ] || fail "Dependency directory is missing: $deps"
deps=$(CDPATH= cd -P "$deps" && pwd)
[ ! -e "$out" ] && [ ! -L "$out" ] || fail "Output already exists: $out"
parent=$(CDPATH= cd -P "$(dirname "$out")" && pwd) || fail 'Output parent must exist'
name=$(basename "$out")
case $name in ''|.|..) fail 'Invalid output name' ;; esac
out=$parent/$name
case $out in "$root"|"$root"/*) fail 'Output must be outside the Git worktree' ;; esac
# Colon is the Unix classpath separator; newline paths are not supported.
case $deps$out$root in *:*) fail 'Paths must not contain a colon' ;; esac
case $deps$out$root in *'
'*) fail 'Paths must not contain a newline' ;; esac
for tool in git find sort awk od cmp cp date tr sed; do
    command -v "$tool" >/dev/null 2>&1 || fail "Required command is unavailable: $tool"
done
if command -v sha256sum >/dev/null 2>&1; then
    hash_tool=sha256sum
elif command -v shasum >/dev/null 2>&1; then
    hash_tool=shasum
elif command -v openssl >/dev/null 2>&1; then
    hash_tool=openssl
else
    fail 'sha256sum, shasum or openssl is required'
fi
hash() {
    # Capture the producer's status before parsing; a pipeline would hide it.
    field=first
    case $hash_tool in
        sha256sum) raw=$(sha256sum < "$1") || fail "SHA-256 calculation failed: $1" ;;
        shasum) raw=$(shasum -a 256 < "$1") || fail "SHA-256 calculation failed: $1" ;;
        openssl)
            raw=$(openssl dgst -sha256 < "$1") || fail "OpenSSL SHA-256 calculation failed: $1"
            field=last ;;
    esac
    printf '%s\n' "$raw" | awk -v field="$field" '
        NR==1 {digest=(field=="last" ? $NF : $1)}
        END {
            if (NR!=1 || length(digest)!=64 || digest !~ /^[0-9a-fA-F]+$/) exit 1
            print toupper(digest)
        }' || fail "Invalid SHA-256 output from $hash_tool: $1"
}
if [ -n "${JAVA_HOME:-}" ]; then
    java=$JAVA_HOME/bin/java; javac=$JAVA_HOME/bin/javac; jar=$JAVA_HOME/bin/jar
else
    java=java; javac=javac; jar=jar
fi
for tool in "$java" "$javac" "$jar"; do
    command -v "$tool" >/dev/null 2>&1 || fail "JDK tool is unavailable: $tool"
done
java_version=$("$java" -version 2>&1) || fail 'java -version failed'
javac_version=$("$javac" -version 2>&1) || fail 'javac -version failed'
printf '%s\n' "$java_version" | awk '/version "1[.]8[."]/{ok=1} END {exit !ok}' || fail "Java 8 is required: $java_version"
case $javac_version in 'javac 1.8.'*) ;; *) fail "Javac 8 is required: $javac_version" ;; esac
baseline=bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6
cd "$root"
head=$(git rev-parse HEAD) || fail 'Cannot read HEAD'
git merge-base --is-ancestor "$baseline" HEAD || fail 'Production baseline is not an ancestor of HEAD (full history required)'
git diff --quiet "$baseline" -- src native test System.properties .classpath .project .settings || fail 'Production/test inputs differ from baseline'
protected_status=$(git status --porcelain --untracked-files=all -- src native test System.properties .classpath .project .settings) || fail 'Cannot inspect protected inputs'
[ -z "$protected_status" ] || fail 'Production/test inputs contain uncommitted or untracked changes'
status=$(git status --porcelain --untracked-files=all) || fail 'Cannot read worktree status'
# As with the Windows build, require a clean checkout for a release candidate.
[ -z "$status" ] || fail 'Worktree must be clean; commit build/documentation changes and use a separate clean clone'
dependencies='core-2.2.jar C6963B3DDC11B8A1FF4EBF65E93314CC6AF341685F70C98C752094FA59BEF492
gson-2.8.5.jar 233A0149FC365C9F6EDBD683CFE266B19BDC773BE98EABDAF6B3C924B48E7D81
javase-2.2.jar CC32F41B3FCFF840BCDD08F14D24E7C170E382BD5C5A81A072AC075E66CC8426
jna-4.1.0.jar 1AA37E9EA6BAA0EE152D89509F758F0847EAC66EC179B955CAFE0919E540A92E
json-20180813.jar 518080049BA83181914419D11A25D9BC9833A2D729B6A6E7469FA52851356DA8
sotalib.jar 7C3B45F42139A651E2C5D021C18EBF217CDB9BE5AF25569E910221D88D71BFFA'
classpath=
manifest_cp=
old_ifs=$IFS
IFS='
'
for entry in $dependencies; do
    IFS=$old_ifs
    dep=${entry%% *}; expected=${entry#* }
    [ -f "$deps/$dep" ] || fail "Missing dependency: $deps/$dep"
    actual=$(hash "$deps/$dep")
    [ "$actual" = "$expected" ] || fail "Dependency hash mismatch: $dep ($actual)"
    classpath=${classpath:+$classpath:}$deps/$dep
    manifest_cp=${manifest_cp:+$manifest_cp }lib/$dep
done
IFS=$old_ifs
# Atomic reservation: an existing directory (even empty) is never reused.
mkdir "$out" || fail "Cannot reserve new output: $out"
trap 'printf "ERROR: Build interrupted/failed; incomplete output retained: %s\n" "$out" >&2' 1 2 3 15
candidate=$out/RobotController
mkdir "$candidate" "$candidate/lib" "$candidate/native" "$out/classes" "$out/inspect"
report=$out/java-build-report.txt
{
    printf 'Build status: INCOMPLETE\nRepository HEAD: %s\nProduction baseline: %s\n' "$head" "$baseline"
    printf 'Production baseline integrity: PASS\nWorktree: CLEAN\nUTC: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'Java: %s\nJavac: %s\n' "$java_version" "$javac_version"
} > "$report"
find src -type f -name '*.java' | sort > "$out/sources.txt"
set --
while IFS= read -r source; do set -- "$@" "$source"; done < "$out/sources.txt"
[ "$#" -gt 0 ] || fail 'No production Java sources'
printf 'Production source count: %s\n' "$#" >> "$report"
if "$javac" -encoding UTF-8 -source 1.8 -target 1.8 -Xlint:all -cp "$classpath" -d "$out/classes" "$@" > "$out/javac.log" 2>&1; then
    cat "$out/javac.log"
else
    cat "$out/javac.log" >&2; fail "javac failed; see $out/javac.log"
fi
printf 'Manifest-Version: 1.0\nMain-Class: main.App\nClass-Path: %s\n\n' "$manifest_cp" > "$out/MANIFEST.MF"
artifact=$candidate/RobotController.jar
"$jar" cfm "$artifact" "$out/MANIFEST.MF" -C "$out/classes" . > "$out/jar.log" 2>&1 || fail "jar failed; see $out/jar.log"
"$jar" tf "$artifact" > "$out/jar-entries.txt" || fail 'Cannot list JAR'
(cd "$out/inspect" && "$jar" xf "$artifact") || fail 'Cannot extract generated JAR'
# Compare every packaged class to the compiler output and check Java 8 major version.
(cd "$out/classes" && find . -type f -name '*.class' | sort) > "$out/classes.txt"
(cd "$out/inspect" && find . -type f -name '*.class' | sort) > "$out/packaged-classes.txt"
cmp "$out/classes.txt" "$out/packaged-classes.txt" || fail 'JAR class inventory mismatch'
class_count=0
while IFS= read -r class; do
    cmp "$out/classes/$class" "$out/inspect/$class" || fail "Packaged class mismatch: $class"
    version=$(od -An -tu1 -j 6 -N 2 "$out/inspect/$class" | awk '{$1=$1;print}')
    [ "$version" = '0 52' ] || fail "Non-Java-8 class: $class ($version)"
    class_count=$((class_count + 1))
done < "$out/classes.txt"
[ -f "$out/inspect/main/App.class" ] || fail 'main/App.class is missing'
awk '{sub(/\r$/, "")} /^ / {line=line substr($0,2); next} {if (NR>1) print line; line=$0} END {print line}' \
    "$out/inspect/META-INF/MANIFEST.MF" > "$out/manifest-unfolded.txt"
awk -v cp="$manifest_cp" '$0=="Main-Class: main.App" {m++} $0=="Class-Path: " cp {c++} END {exit !(m==1 && c==1)}' \
    "$out/manifest-unfolded.txt" || fail 'Manifest mismatch'
cp "$root/System.properties" "$candidate/System.properties"
cmp "$root/System.properties" "$candidate/System.properties" || fail 'Properties copy mismatch'
IFS='
'
for entry in $dependencies; do
    IFS=$old_ifs
    dep=${entry%% *}; expected=${entry#* }
    cp "$deps/$dep" "$candidate/lib/$dep"
    actual=$(hash "$candidate/lib/$dep")
    [ "$actual" = "$expected" ] || fail "Copied dependency hash mismatch: $dep"
    printf '%s SHA-256 %s PASS\n' "$dep" "$actual" >> "$report"
done
IFS=$old_ifs
jar_hash=$(hash "$artifact") || fail 'Cannot hash generated JAR'
properties_hash=$(hash "$candidate/System.properties") || fail 'Cannot hash copied properties'
{
    printf 'Generated class count: %s\nClass inventory and all major versions (52): PASS\nCompiler errors: 0\n' "$class_count"
    printf 'Manifest Main-Class: main.App PASS\nManifest Class-Path: %s PASS\n' "$manifest_cp"
    printf 'RobotController.jar SHA-256: %s\nSystem.properties SHA-256: %s\n' "$jar_hash" "$properties_hash"
    printf 'Native directory: EMPTY\nBuild status: PASS\n'
} >> "$report"
trap - 1 2 3 15
cat "$report"
printf 'Candidate directory: %s\n' "$candidate"
