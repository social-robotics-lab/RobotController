[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$DependencyDirectory)

# Offline tests only. Mutations are confined to a newly created local clone.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$Root = Split-Path -Parent $PSScriptRoot
$DependencyDirectory = (Resolve-Path -LiteralPath $DependencyDirectory).ProviderPath
$Scratch = Join-Path ([IO.Path]::GetTempPath()) ('robotcontroller-dev-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Scratch | Out-Null
Write-Host "Test files retained at: $Scratch"
$Fixture = Join-Path $Scratch 'source'
& git -c core.autocrlf=false clone --no-hardlinks $Root $Fixture
if ($LASTEXITCODE -ne 0) { throw 'Local clone failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build_java_dev.ps1') -Destination "$Fixture\tools"
$Script = "$Fixture\tools\build_java_dev.ps1"
$Shell = Join-Path $PSHOME 'powershell.exe'
$OriginalJavaHome = $env:JAVA_HOME
$RealJdk = @{}
foreach ($name in @('java', 'javac', 'jar')) {
    $command = $name
    if ($env:JAVA_HOME) { $command = Join-Path $env:JAVA_HOME "bin\$name" }
    $RealJdk[$name] = (Get-Command $command -CommandType Application).Source
}
$script:Tests = 0
function Invoke-Build([string]$Output, [string]$Deps = $DependencyDirectory) {
    $ErrorActionPreference = 'Continue'
    $lines = @(& $Shell -NoProfile -ExecutionPolicy Bypass -File $Script -DependencyDirectory $Deps -OutputDirectory $Output 2>&1)
    return @{ Code = $LASTEXITCODE; Text = ($lines -join "`n") }
}
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Pass([string]$Label) { $script:Tests++; Write-Host "PASS: $Label" }
function Expect-Failure([string]$Label, [string]$Message, [string]$Output, [string]$Deps = $DependencyDirectory) {
    $result = Invoke-Build $Output $Deps
    $result.Text | Set-Content -LiteralPath (Join-Path $Scratch "failure-$($script:Tests).txt")
    Assert-True ($result.Code -ne 0 -and $result.Text.Contains($Message)) "$Label failed: $($result.Text)"
    $report = Join-Path $Output 'java-dev-build-report.txt'
    if (Test-Path -LiteralPath $report) {
        Assert-True (-not ([IO.File]::ReadAllText($report).Contains('Build status: PASS'))) "$Label recorded PASS"
    }
    Pass $Label
}
function Check-Success([string]$Label, [string]$Output) {
    $result = Invoke-Build $Output
    $result.Text | Set-Content -LiteralPath (Join-Path $Scratch "$Label.txt")
    Assert-True ($result.Code -eq 0) $result.Text
    $report = [IO.File]::ReadAllText((Join-Path $Output 'java-dev-build-report.txt'))
    foreach ($line in @('Build status: PASS', 'Production source count: 23', 'Generated class count: 49',
        'All compiled and packaged classes: Java 8 (major version 52) PASS',
        'Manifest Main-Class: main.App PASS', 'Manifest Class-Path: lib/core-2.2.jar',
        'Input files unchanged during build: PASS', 'not a release acceptance')) {
        Assert-True ($report.Contains($line)) "Missing report evidence: $line"
    }
    Assert-True (@(Get-ChildItem -LiteralPath "$Output\RobotController\lib" -Filter '*.jar').Count -eq 6) 'Dependency count mismatch'
    Assert-True (@(Get-ChildItem -LiteralPath "$Output\RobotController\native").Count -eq 0) 'Native output must be empty'
    Pass $Label
}
function Get-InputHashes([string]$SourceRoot) {
    $hashes = @{}
    foreach ($file in @(Get-ChildItem "$SourceRoot\src","$SourceRoot\native","$SourceRoot\test" -Recurse -File) +
        @(Get-Item "$SourceRoot\System.properties","$SourceRoot\tools\build_phase_g.ps1","$SourceRoot\tools\build_java.sh")) {
        $hashes[$file.FullName] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    }
    return $hashes
}
$OriginalHashes = Get-InputHashes $Root
try {
    $fixtureHashes = Get-InputHashes $Fixture
    Check-Success 'normal build' "$Scratch\normal output"
    foreach ($path in $fixtureHashes.Keys) {
        Assert-True ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -eq $fixtureHashes[$path]) "Input modified: $path"
    }
    Pass 'normal build leaves source and settings unchanged'
    $app = "$Fixture\src\main\App.java"
    $text = [IO.File]::ReadAllText($app)
    $changed = $text.Replace('public class App {', 'public class App { public static final String DEV_BUILD_MARKER = "uncommitted-source";')
    Assert-True ($text -ne $changed) 'Fixture marker insertion failed'
    [IO.File]::WriteAllText($app, $changed, (New-Object Text.UTF8Encoding($false)))
    Check-Success 'uncommitted changed source' "$Scratch\dirty output"
    $oldClass = (Get-FileHash "$Scratch\normal output\classes\main\App.class" -Algorithm SHA256).Hash
    $newClass = (Get-FileHash "$Scratch\dirty output\classes\main\App.class" -Algorithm SHA256).Hash
    Assert-True ($oldClass -ne $newClass) 'Current source was not compiled'
    Assert-True ([IO.File]::ReadAllText($app) -eq $changed) 'Dirty input modified'
    & git -C $Fixture add src/main/App.java
    if ($LASTEXITCODE -ne 0) { throw 'Fixture add failed' }
    & git -C $Fixture -c user.name='Offline Test' -c user.email='offline@example.invalid' commit -m 'Change source in isolated fixture'
    if ($LASTEXITCODE -ne 0) { throw 'Fixture commit failed' }
    Check-Success 'committed source differs from production baseline' "$Scratch\changed baseline output"

    $existing = "$Scratch\existing"
    New-Item -ItemType Directory -Path $existing | Out-Null
    'unchanged' | Set-Content "$existing\sentinel"
    Expect-Failure 'existing directory rejected' 'already exists' $existing
    Assert-True ((Get-Content "$existing\sentinel") -eq 'unchanged') 'Existing content overwritten'
    $existingFile = "$Scratch\existing-file"
    'unchanged' | Set-Content $existingFile
    Expect-Failure 'existing file rejected' 'already exists' $existingFile
    Assert-True ((Get-Content $existingFile) -eq 'unchanged') 'Existing file overwritten'
    Expect-Failure 'worktree output rejected' 'outside the Git worktree' "$Fixture\new-output"
    Expect-Failure 'normalized parent traversal rejected' 'outside the Git worktree' "$Fixture\tools\..\new-output"
    $otherRepo = "$Scratch\other-repository"
    & git init $otherRepo | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Fixture repository init failed' }
    Expect-Failure 'other Git repository rejected' 'outside every Git repository' "$otherRepo\output"
    $junction = "$Scratch\junction"
    New-Item -ItemType Junction -Path $junction -Target $Fixture | Out-Null
    Expect-Failure 'junction bypass rejected' 'junctions or symbolic links' "$junction\output"
    $missing = "$Scratch\missing-deps"
    New-Item -ItemType Directory -Path $missing | Out-Null
    Expect-Failure 'missing JAR rejected' 'Missing dependency' "$Scratch\missing-output" $missing
    Assert-True (-not (Test-Path "$Scratch\missing-output")) 'Missing-dependency output created'
    'wrong' | Set-Content "$missing\core-2.2.jar"
    Expect-Failure 'wrong JAR hash rejected' 'Dependency hash mismatch' "$Scratch\wrong-output" $missing
    Assert-True (-not (Test-Path "$Scratch\wrong-output")) 'Wrong-hash output created'

    $fakeHome = "$Scratch\fake-jdk"
    New-Item -ItemType Directory -Path "$fakeHome\bin" | Out-Null
    foreach ($name in @('java','javac','jar')) {
        @('@echo off', ('"' + $RealJdk[$name] + '" %*'), 'exit /b %errorlevel%') |
            Set-Content -LiteralPath "$fakeHome\bin\$name.cmd" -Encoding ASCII
    }
    $env:JAVA_HOME = $fakeHome
    @('@echo off', 'echo openjdk version "17.0.1"', 'exit /b 0') |
        Set-Content "$fakeHome\bin\java.cmd" -Encoding ASCII
    Expect-Failure 'non-Java-8 runtime rejected (mock)' 'Java 8 is required' "$Scratch\runtime-output"
    @('@echo off', ('"' + $RealJdk.java + '" %*'), 'exit /b %errorlevel%') |
        Set-Content "$fakeHome\bin\java.cmd" -Encoding ASCII
    @('@echo off', 'echo javac 17.0.1', 'exit /b 0') |
        Set-Content "$fakeHome\bin\javac.cmd" -Encoding ASCII
    Expect-Failure 'non-Java-8 compiler rejected (mock)' 'Javac 8 is required' "$Scratch\compiler-output"
    $env:JAVA_HOME = $OriginalJavaHome
    [IO.File]::AppendAllText($app, "`ninvalid java syntax`n")
    Expect-Failure 'compile errors fail build' 'javac failed' "$Scratch\compile-error-output"
    [IO.File]::WriteAllText($app, $changed, (New-Object Text.UTF8Encoding($false)))

    # Mutate only the test JAR via a wrapper, using an otherwise real Java 8 JDK.
    $poison = "$Scratch\poison-jar.ps1"
    @'
param([string]$JarPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$zip = [IO.Compression.ZipFile]::Open($JarPath, [IO.Compression.ZipArchiveMode]::Update)
try {
    $entry = $zip.GetEntry('main/App.class')
    $stream = $entry.Open()
    $memory = New-Object IO.MemoryStream
    try { $stream.CopyTo($memory); $bytes = $memory.ToArray() }
    finally { $stream.Dispose(); $memory.Dispose() }
    $entry.Delete()
    $bytes[7] = 51
    $stream = $zip.CreateEntry('main/App.class').Open()
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
} finally { $zip.Dispose() }
'@ | Set-Content -LiteralPath $poison -Encoding UTF8
    @('@echo off', ('"' + $RealJdk.javac + '" %*'), 'exit /b %errorlevel%') |
        Set-Content "$fakeHome\bin\javac.cmd" -Encoding ASCII
    @('@echo off', ('"' + $RealJdk.jar + '" %*'), 'if errorlevel 1 exit /b %errorlevel%',
        ('"' + $Shell + '" -NoProfile -ExecutionPolicy Bypass -File "' + $poison + '" %2'), 'exit /b %errorlevel%') |
        Set-Content "$fakeHome\bin\jar.cmd" -Encoding ASCII
    $env:JAVA_HOME = $fakeHome
    Expect-Failure 'packaged non-Java-8 class rejected' 'non-Java-8 class' "$Scratch\bad-class-output"
} finally {
    $env:JAVA_HOME = $OriginalJavaHome
    foreach ($path in $OriginalHashes.Keys) {
        Assert-True ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -eq $OriginalHashes[$path]) "Original worktree changed: $path"
    }
}
Pass 'original worktree production inputs unchanged'
Write-Host "ALL DEVELOPMENT BUILD TESTS PASSED ($script:Tests)"
