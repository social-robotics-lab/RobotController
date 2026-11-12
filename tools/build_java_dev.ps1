[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DependencyDirectory,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

# Development only: build the current sources without a clean/baseline check.
# Never start the application, load JNI, deploy, or change the input worktree.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function Get-FullPath([string]$Path) {
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path (Get-Location).ProviderPath $Path))
}

function Invoke-Jdk([string]$Command, [string[]]$Arguments) {
    # Windows PowerShell represents native stderr as ErrorRecord objects.
    $ErrorActionPreference = 'Continue'
    $lines = @(& $Command @Arguments 2>&1)
    $code = $LASTEXITCODE
    return @{ Output = @($lines | ForEach-Object { "$_" }); ExitCode = $code }
}

function Assert-Java8Class([IO.Stream]$Stream, [string]$Name) {
    $header = New-Object byte[] 8
    $offset = 0
    while ($offset -lt 8) {
        $read = $Stream.Read($header, $offset, 8 - $offset)
        if ($read -eq 0) { throw "Truncated class: $Name" }
        $offset += $read
    }
    if ($header[0] -ne 0xCA -or $header[1] -ne 0xFE -or
        $header[2] -ne 0xBA -or $header[3] -ne 0xBE -or
        $header[6] -ne 0 -or $header[7] -ne 52) {
        throw "Invalid or non-Java-8 class: $Name"
    }
}

$RepositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$DependencyDirectory = Get-FullPath $DependencyDirectory
$OutputDirectory = Get-FullPath $OutputDirectory
if ($OutputDirectory.Equals($RepositoryRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $OutputDirectory.StartsWith($RepositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDirectory must be outside the Git worktree.'
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'OutputDirectory already exists; choose a new path.' }
$OutputParent = Split-Path -Parent $OutputDirectory
if (-not (Test-Path -LiteralPath $OutputParent -PathType Container)) {
    throw 'OutputDirectory parent must already exist.'
}
# Resolve-Path does not resolve Windows junctions. Reject reparse ancestors rather
# than allowing an alias to bypass the worktree boundary (also covers symlinks).
$ancestor = Get-Item -LiteralPath $OutputParent -Force
while ($null -ne $ancestor) {
    if (($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'OutputDirectory ancestors must not be junctions or symbolic links.'
    }
    if (Test-Path -LiteralPath (Join-Path $ancestor.FullName '.git')) {
        throw 'OutputDirectory must be outside every Git repository.'
    }
    $ancestor = $ancestor.Parent
}
Get-Command git -ErrorAction Stop | Out-Null
$GitLocation = Invoke-Jdk 'git' @('-C', $OutputParent, 'rev-parse', '--is-inside-work-tree', '--is-bare-repository', '--is-inside-git-dir')
if ($GitLocation.ExitCode -eq 0 -and $GitLocation.Output -contains 'true') {
    throw 'OutputDirectory must be outside every Git repository.'
}

$ExpectedDependencies = [ordered]@{
    'core-2.2.jar' = 'C6963B3DDC11B8A1FF4EBF65E93314CC6AF341685F70C98C752094FA59BEF492'
    'gson-2.8.5.jar' = '233A0149FC365C9F6EDBD683CFE266B19BDC773BE98EABDAF6B3C924B48E7D81'
    'javase-2.2.jar' = 'CC32F41B3FCFF840BCDD08F14D24E7C170E382BD5C5A81A072AC075E66CC8426'
    'jna-4.1.0.jar' = '1AA37E9EA6BAA0EE152D89509F758F0847EAC66EC179B955CAFE0919E540A92E'
    'json-20180813.jar' = '518080049BA83181914419D11A25D9BC9833A2D729B6A6E7469FA52851356DA8'
    'sotalib.jar' = '7C3B45F42139A651E2C5D021C18EBF217CDB9BE5AF25569E910221D88D71BFFA'
}
$DependencyPaths = @()
foreach ($name in $ExpectedDependencies.Keys) {
    $path = Join-Path $DependencyDirectory $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing dependency: $name" }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $ExpectedDependencies[$name]) {
        throw "Dependency hash mismatch: $name"
    }
    $DependencyPaths += $path
}
$Jdk = @{}
foreach ($name in @('java', 'javac', 'jar')) {
    $command = $name
    if ($env:JAVA_HOME) { $command = Join-Path $env:JAVA_HOME "bin\$name" }
    $Jdk[$name] = (Get-Command $command -CommandType Application -ErrorAction Stop).Source
}
$JavaVersion = Invoke-Jdk $Jdk.java @('-version')
$JavacVersion = Invoke-Jdk $Jdk.javac @('-version')
if ($JavaVersion.ExitCode -ne 0 -or ($JavaVersion.Output -join ' ') -notmatch '\bversion "1\.8[."]') {
    throw 'Java 8 is required.'
}
if ($JavacVersion.ExitCode -ne 0 -or ($JavacVersion.Output -join ' ') -notmatch '^javac 1\.8\.') {
    throw 'Javac 8 is required.'
}
$Sources = @(Get-ChildItem -LiteralPath (Join-Path $RepositoryRoot 'src') -Recurse -Filter '*.java' -File |
    Sort-Object FullName)
if ($Sources.Count -eq 0) { throw 'No Java sources.' }
$Properties = Join-Path $RepositoryRoot 'System.properties'
$InputHashes = @{}
foreach ($path in @($Sources.FullName) + @($Properties)) {
    $InputHashes[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
}

# No -Force: reserve a new output directory, never reuse an existing one.
New-Item -ItemType Directory -Path $OutputDirectory -ErrorAction Stop | Out-Null
$ReportPath = Join-Path $OutputDirectory 'java-dev-build-report.txt'
'Build status: INCOMPLETE' | Set-Content -LiteralPath $ReportPath -Encoding UTF8
$Candidate = Join-Path $OutputDirectory 'RobotController'
$Classes = Join-Path $OutputDirectory 'classes'
foreach ($path in @($Candidate, $Classes, "$Candidate\lib", "$Candidate\native")) {
    New-Item -ItemType Directory -Path $path | Out-Null
}
$ClassPath = $DependencyPaths -join [IO.Path]::PathSeparator
$CompileArguments = @('-encoding', 'UTF-8', '-source', '1.8', '-target', '1.8', '-Xlint:all',
    '-cp', $ClassPath, '-d', $Classes) + @($Sources.FullName)
$Compile = Invoke-Jdk $Jdk.javac $CompileArguments
$Compile.Output | Set-Content -LiteralPath (Join-Path $OutputDirectory 'javac.log') -Encoding UTF8
if ($Compile.ExitCode -ne 0) { throw 'javac failed; see javac.log. Incomplete output retained.' }
$ManifestClassPath = ($ExpectedDependencies.Keys | ForEach-Object { "lib/$_" }) -join ' '
$Manifest = Join-Path $OutputDirectory 'MANIFEST.MF'
@('Manifest-Version: 1.0', 'Main-Class: main.App', "Class-Path: $ManifestClassPath", '') |
    Set-Content -LiteralPath $Manifest -Encoding ASCII
$JarPath = Join-Path $Candidate 'RobotController.jar'
$JarResult = Invoke-Jdk $Jdk.jar @('cfm', $JarPath, $Manifest, '-C', $Classes, '.')
$JarResult.Output | Set-Content -LiteralPath (Join-Path $OutputDirectory 'jar.log') -Encoding UTF8
if ($JarResult.ExitCode -ne 0) { throw 'jar failed; see jar.log. Incomplete output retained.' }

$Compiled = New-Object 'System.Collections.Generic.Dictionary[string,string]' ([StringComparer]::Ordinal)
foreach ($class in @(Get-ChildItem -LiteralPath $Classes -Recurse -Filter '*.class' -File)) {
    $stream = [IO.File]::OpenRead($class.FullName)
    try { Assert-Java8Class $stream $class.FullName } finally { $stream.Dispose() }
    $relative = $class.FullName.Substring($Classes.Length + 1).Replace('\', '/')
    $Compiled[$relative] = (Get-FileHash -LiteralPath $class.FullName -Algorithm SHA256).Hash
}
if ($Compiled.Count -eq 0 -or -not $Compiled.ContainsKey('main/App.class')) { throw 'Missing compiled main/App.class.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [IO.Compression.ZipFile]::OpenRead($JarPath)
try {
    $entries = @($Archive.Entries | Where-Object { $_.FullName -ceq 'META-INF/MANIFEST.MF' })
    if ($entries.Count -ne 1) { throw 'Missing or duplicate manifest.' }
    $reader = New-Object IO.StreamReader($entries[0].Open(), [Text.Encoding]::UTF8)
    try { $text = $reader.ReadToEnd() -replace "`r?`n ", '' } finally { $reader.Dispose() }
    $lines = $text -split "`r?`n"
    if (@($lines | Where-Object { $_ -ceq 'Main-Class: main.App' }).Count -ne 1 -or
        @($lines | Where-Object { $_ -ceq "Class-Path: $ManifestClassPath" }).Count -ne 1) {
        throw 'Manifest mismatch.'
    }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($entry in @($Archive.Entries | Where-Object { $_.FullName.EndsWith('.class') })) {
        if (-not $seen.Add($entry.FullName) -or -not $Compiled.ContainsKey($entry.FullName)) {
            throw "Unexpected/duplicate packaged class: $($entry.FullName)"
        }
        $stream = $entry.Open()
        try { Assert-Java8Class $stream $entry.FullName } finally { $stream.Dispose() }
        $stream = $entry.Open()
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $digest = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
        finally { $sha.Dispose(); $stream.Dispose() }
        if ($digest -ne $Compiled[$entry.FullName]) { throw "Packaged class mismatch: $($entry.FullName)" }
    }
    if ($seen.Count -ne $Compiled.Count -or -not $seen.Contains('main/App.class')) {
        throw 'JAR class inventory mismatch.'
    }
} finally { $Archive.Dispose() }

Copy-Item -LiteralPath $Properties -Destination $Candidate
foreach ($path in $DependencyPaths) {
    $name = Split-Path -Leaf $path
    $copy = Join-Path "$Candidate\lib" $name
    Copy-Item -LiteralPath $path -Destination $copy
    if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne $ExpectedDependencies[$name]) {
        throw "Copied dependency hash mismatch: $name"
    }
}
if ((Get-FileHash -LiteralPath "$Candidate\System.properties" -Algorithm SHA256).Hash -ne $InputHashes[$Properties]) {
    throw 'Properties copy mismatch.'
}
foreach ($path in $InputHashes.Keys) {
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $InputHashes[$path]) {
        throw "Input changed during build: $path"
    }
}
$Report = @(
    'RobotController DEVELOPMENT build (not a release acceptance)',
    "UTC: $([DateTime]::UtcNow.ToString('o'))",
    'Production baseline / clean worktree: NOT CHECKED (development build)',
    "Java: $($JavaVersion.Output -join ' | ')", "Javac: $($JavacVersion.Output -join ' | ')",
    "Production source count: $($Sources.Count)", "Generated class count: $($Compiled.Count)",
    'Compiler errors: 0', "Compiler warnings: $(@($Compile.Output | Where-Object { $_ -match '\[[a-z]+\]' }).Count) (see javac.log)",
    'All compiled and packaged classes: Java 8 (major version 52) PASS',
    'JAR class inventory and contents: PASS', 'Manifest Main-Class: main.App PASS',
    "Manifest Class-Path: $ManifestClassPath PASS", 'Input files unchanged during build: PASS',
    "RobotController.jar SHA-256: $((Get-FileHash -LiteralPath $JarPath -Algorithm SHA256).Hash)",
    'Native directory: EMPTY (JNI is not built, copied or loaded)'
)
foreach ($name in $ExpectedDependencies.Keys) { $Report += "$name SHA-256 $($ExpectedDependencies[$name]) PASS" }
$Report += 'Build status: PASS'
$Report | Set-Content -LiteralPath $ReportPath -Encoding UTF8
$Report | ForEach-Object { Write-Host $_ }
Write-Host "Development output: $Candidate"
