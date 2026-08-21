[CmdletBinding()]
param(
    [string]$DependencyDirectory,
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$ProductionSourceBaseline = "bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6"
$ProductionInputPaths = @(
    "src",
    "native",
    "test",
    "System.properties",
    ".classpath",
    ".project",
    ".settings"
)
$ExpectedDependencies = [ordered]@{
    "core-2.2.jar"       = "C6963B3DDC11B8A1FF4EBF65E93314CC6AF341685F70C98C752094FA59BEF492"
    "gson-2.8.5.jar"     = "233A0149FC365C9F6EDBD683CFE266B19BDC773BE98EABDAF6B3C924B48E7D81"
    "javase-2.2.jar"     = "CC32F41B3FCFF840BCDD08F14D24E7C170E382BD5C5A81A072AC075E66CC8426"
    "jna-4.1.0.jar"      = "1AA37E9EA6BAA0EE152D89509F758F0847EAC66EC179B955CAFE0919E540A92E"
    "json-20180813.jar"  = "518080049BA83181914419D11A25D9BC9833A2D729B6A6E7469FA52851356DA8"
    "sotalib.jar"        = "7C3B45F42139A651E2C5D021C18EBF217CDB9BE5AF25569E910221D88D71BFFA"
}
$ManifestClassPath = ($ExpectedDependencies.Keys | ForEach-Object { "lib/$_" }) -join " "

function Assert-CommandAvailable([string]$Name) {
    if ($null -eq (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is unavailable: $Name"
    }
}

function Get-FullPath([string]$Path, [string]$BasePath) {
    if ([IO.Path]::IsPathRooted($Path)) {
        return [IO.Path]::GetFullPath($Path)
    }
    return [IO.Path]::GetFullPath((Join-Path $BasePath $Path))
}

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = [IO.Path]::GetFullPath((Join-Path $ScriptDirectory ".."))
$RepositoryParent = Split-Path -Parent $RepositoryRoot
if ([string]::IsNullOrWhiteSpace($DependencyDirectory)) {
    $DependencyDirectory = Join-Path $RepositoryParent "lib"
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $RepositoryParent "RobotController-phase-g-bd299ae"
}
$DependencyDirectory = Get-FullPath $DependencyDirectory $RepositoryRoot
$OutputDirectory = Get-FullPath $OutputDirectory $RepositoryRoot

if ($OutputDirectory.StartsWith($RepositoryRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase) -or
        $OutputDirectory.Equals($RepositoryRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDirectory must be outside the Git worktree: $OutputDirectory"
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "OutputDirectory already exists; use a new empty path: $OutputDirectory"
}

Assert-CommandAvailable "git"
Assert-CommandAvailable "java"
Assert-CommandAvailable "javac"
Assert-CommandAvailable "jar"

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $JavaVersion = (& java -version 2>&1) -join " | "
    $JavaVersionExitCode = $LASTEXITCODE
    $JavacVersion = (& javac -version 2>&1) -join " | "
    $JavacVersionExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}
if ($JavaVersionExitCode -ne 0 -or
        $JavaVersion -notmatch '\bversion "1\.8(?:\.|\")') {
    throw "Java 8 is required; observed: $JavaVersion"
}
if ($JavacVersionExitCode -ne 0 -or
        $JavacVersion -notmatch '(?:^|\|\s*)javac 1\.8(?:\.|$)') {
    throw "Javac 8 is required; observed: $JavacVersion"
}

$RepositoryHead = (& git -c "safe.directory=$($RepositoryRoot.Replace('\', '/'))" -C $RepositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read Git HEAD."
}
& git -c "safe.directory=$($RepositoryRoot.Replace('\', '/'))" -C $RepositoryRoot `
    merge-base --is-ancestor $ProductionSourceBaseline HEAD
$AncestorExitCode = $LASTEXITCODE
if ($AncestorExitCode -eq 1) {
    throw "Production source baseline is not an ancestor of HEAD: $ProductionSourceBaseline"
}
if ($AncestorExitCode -ne 0) {
    throw "Unable to verify production source baseline ancestry."
}

& git -c "safe.directory=$($RepositoryRoot.Replace('\', '/'))" -C $RepositoryRoot `
    diff --quiet $ProductionSourceBaseline -- @($ProductionInputPaths)
$ProductionDiffExitCode = $LASTEXITCODE
if ($ProductionDiffExitCode -eq 1) {
    throw "Production/test inputs differ from baseline $ProductionSourceBaseline."
}
if ($ProductionDiffExitCode -ne 0) {
    throw "Unable to compare production/test inputs with the baseline."
}
$ProductionInputStatus = @(& git -c "safe.directory=$($RepositoryRoot.Replace('\', '/'))" `
    -C $RepositoryRoot status --porcelain --untracked-files=all -- @($ProductionInputPaths))
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect production/test input status."
}
if ($ProductionInputStatus.Count -ne 0) {
    throw "Production/test inputs contain uncommitted or untracked changes: $($ProductionInputStatus -join '; ')"
}
$Status = @(& git -c "safe.directory=$($RepositoryRoot.Replace('\', '/'))" -C $RepositoryRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read Git status."
}
$AllowedPhaseGChanges = @(
    "docs/phase-g-acceptance.md",
    "docs/phase-g-result-template.md",
    "tools/build_phase_g.ps1",
    "tools/phase_g_audio_client.py",
    "tools/test_phase_g_audio_client.py"
)
$UnexpectedStatus = @($Status | Where-Object {
    $Line = $_
    if ($Line.Length -lt 4 -or $Line.Contains(" -> ")) { return $true }
    $Path = $Line.Substring(3).Replace('\', '/')
    return $AllowedPhaseGChanges -notcontains $Path
})
if ($UnexpectedStatus.Count -ne 0) {
    throw "Worktree has changes outside the Phase G preparation files: $($UnexpectedStatus -join '; ')"
}
$RepositoryWorktreeState = if ($Status.Count -eq 0) {
    "CLEAN"
} else {
    "DEVELOPMENT: only the five Phase G preparation files differ"
}

$DependencyPaths = New-Object System.Collections.Generic.List[string]
$DependencyReport = New-Object System.Collections.Generic.List[string]
foreach ($Name in $ExpectedDependencies.Keys) {
    $Path = Join-Path $DependencyDirectory $Name
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing dependency: $Path"
    }
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
    if ($ActualHash -ne $ExpectedDependencies[$Name]) {
        throw "Dependency hash mismatch for $Name`: $ActualHash"
    }
    $DependencyPaths.Add($Path)
    $DependencyReport.Add("$Name SHA-256 $ActualHash PASS")
}

$CandidateDirectory = Join-Path $OutputDirectory "RobotController"
$ClassesDirectory = Join-Path $OutputDirectory "classes"
$ManifestPath = Join-Path $OutputDirectory "MANIFEST.MF"
$CompilerLogPath = Join-Path $OutputDirectory "javac.log"
$BuildReportPath = Join-Path $OutputDirectory "phase-g-build-report.txt"
New-Item -ItemType Directory -Path $CandidateDirectory | Out-Null
New-Item -ItemType Directory -Path (Join-Path $CandidateDirectory "lib") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $CandidateDirectory "native") | Out-Null
New-Item -ItemType Directory -Path $ClassesDirectory | Out-Null

$Sources = @(Get-ChildItem -LiteralPath (Join-Path $RepositoryRoot "src") -Recurse -Filter "*.java" |
    Sort-Object FullName)
if ($Sources.Count -eq 0) {
    throw "No Java production sources found."
}
$ClassPath = [string]::Join([IO.Path]::PathSeparator, $DependencyPaths.ToArray())
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $CompilerOutput = @(& javac -encoding UTF-8 -source 1.8 -target 1.8 -Xlint:all `
        -cp $ClassPath -d $ClassesDirectory @($Sources.FullName) 2>&1)
    $CompilerExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}
$CompilerOutput | Set-Content -Encoding UTF8 -LiteralPath $CompilerLogPath
$CompilerOutput | ForEach-Object { Write-Host $_ }
if ($CompilerExitCode -ne 0) {
    throw "javac failed with exit code $CompilerExitCode."
}

$ManifestLines = @(
    "Manifest-Version: 1.0",
    "Main-Class: main.App",
    "Class-Path: $ManifestClassPath",
    ""
)
$ManifestLines | Set-Content -Encoding ASCII -LiteralPath $ManifestPath
$JarPath = Join-Path $CandidateDirectory "RobotController.jar"
& jar cfm $JarPath $ManifestPath -C $ClassesDirectory .
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $JarPath -PathType Leaf)) {
    throw "RobotController.jar generation failed."
}

Copy-Item -LiteralPath (Join-Path $RepositoryRoot "System.properties") -Destination $CandidateDirectory
foreach ($DependencyPath in $DependencyPaths) {
    Copy-Item -LiteralPath $DependencyPath -Destination (Join-Path $CandidateDirectory "lib")
}

$JarEntries = @(& jar tf $JarPath)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect generated JAR."
}
if ($JarEntries -notcontains "main/App.class") {
    throw "Generated JAR does not contain main/App.class."
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [IO.Compression.ZipFile]::OpenRead($JarPath)
try {
    $Entry = $Archive.GetEntry("META-INF/MANIFEST.MF")
    if ($null -eq $Entry) { throw "Generated JAR has no manifest." }
    $Reader = New-Object IO.StreamReader($Entry.Open(), [Text.Encoding]::UTF8)
    try { $ManifestOutput = $Reader.ReadToEnd() } finally { $Reader.Dispose() }
} finally {
    $Archive.Dispose()
}
$UnfoldedManifest = $ManifestOutput -replace "`r?`n ", "" 
if ($UnfoldedManifest -notmatch "(?m)^Main-Class: main\.App\s*$") {
    throw "Generated manifest has an unexpected Main-Class."
}
if ($UnfoldedManifest -notmatch "(?m)^Class-Path: $([Regex]::Escape($ManifestClassPath))\s*$") {
    throw "Generated manifest has an unexpected Class-Path."
}

$ClassCount = @(Get-ChildItem -LiteralPath $ClassesDirectory -Recurse -Filter "*.class").Count
$JarHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $JarPath).Hash.ToUpperInvariant()
$WarningCount = @($CompilerOutput | Where-Object { $_ -match "\[[a-z]+\]" }).Count
$Report = @(
    "Phase G candidate build report",
    "Repository HEAD: $RepositoryHead",
    "Production source baseline: $ProductionSourceBaseline",
    "Production source baseline integrity: PASS",
    "Repository working tree state: $RepositoryWorktreeState",
    "Java: $JavaVersion",
    "Javac: $JavacVersion",
    "Production source count: $($Sources.Count)",
    "Generated class count: $ClassCount",
    "Compiler errors: 0",
    "Compiler warnings: $WarningCount (see javac.log)",
    "Compiler log: javac.log",
    "RobotController.jar SHA-256: $JarHash",
    "Manifest Main-Class: main.App PASS",
    "Manifest Class-Path: $ManifestClassPath PASS",
    "Native directory: EMPTY (native binary is never copied by this script)",
    "",
    "Dependencies:"
)
$Report += $DependencyReport.ToArray()
$Report | Set-Content -Encoding UTF8 -LiteralPath $BuildReportPath
$Report | ForEach-Object { Write-Host $_ }
Write-Host "Candidate directory: $CandidateDirectory"
