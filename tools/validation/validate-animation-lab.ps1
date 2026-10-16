param([Parameter(Mandatory=$true)][string]$EditorDataPath)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$scratch = Join-Path $repoRoot '.validation-temp/animation-lab'
New-Item -ItemType Directory -Path $scratch -Force | Out-Null
$sdk = (& dotnet --list-sdks | Select-Object -Last 1)
if ($LASTEXITCODE -ne 0 -or $sdk -notmatch '^([^ ]+) \[(.+)\]$') { throw 'A .NET SDK is required.' }
$compiler = Join-Path $Matches[2] ($Matches[1] + '/Roslyn/bincore/csc.dll')
$netstandard = Join-Path $EditorDataPath 'NetStandard/ref/2.1.0/netstandard.dll'
if (!(Test-Path -LiteralPath $netstandard)) { throw 'Expected Unity netstandard 2.1 reference assembly.' }
$managed = Join-Path $EditorDataPath 'Managed'
$runtimeRefs = @(Get-ChildItem -LiteralPath (Join-Path $managed 'UnityEngine') -Filter 'UnityEngine*.dll' -File)
$editorRefs = @(Get-ChildItem -LiteralPath (Join-Path $managed 'UnityEngine') -Filter 'UnityEditor*.dll' -File)
if ($runtimeRefs.Count -eq 0 -or $editorRefs.Count -eq 0) { throw 'Unity reference assemblies not found.' }
function Invoke-Compile([string]$Name, [array]$Sources, [array]$References, [string]$Defines) {
    $output = Join-Path $scratch ($Name + '.dll')
    $lines = @('-nologo', '-nostdlib+', '-target:library', '-langversion:9.0', ('-define:' + $Defines), ('-out:"' + $output + '"'))
    $lines += '-r:"' + $netstandard + '"'
    $lines += $References | ForEach-Object { '-r:"' + $_ + '"' }
    $lines += $Sources | ForEach-Object { '"' + $_ + '"' }
    $response = Join-Path $scratch ($Name + '.rsp')
    [IO.File]::WriteAllLines($response, $lines)
    & dotnet $compiler -noconfig ('@' + $response)
    if ($LASTEXITCODE -ne 0) { throw "$Name offline compilation failed." }
    Write-Output "${Name}: offline reference-assembly compile passed."
    return $output
}
$packageSources = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'packages/com.afauxzhub.character-locomotion/Runtime') -Filter '*.cs' -File | ForEach-Object FullName)
$runtimeSources = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'Client/Assets/Scripts') -Filter '*.cs' -Recurse -File | ForEach-Object FullName)
$packageOutput = @(Invoke-Compile 'Afauxzhub.CharacterLocomotion' $packageSources @($runtimeRefs.FullName) 'UNITY_2022_3_OR_NEWER') | Select-Object -Last 1
$runtimeOutput = @(Invoke-Compile 'AnimationLab.Runtime' $runtimeSources @($runtimeRefs.FullName + $packageOutput) 'UNITY_2022_3_OR_NEWER') | Select-Object -Last 1
$packageOutput
$runtimeOutput
$editorSources = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'Client/Assets/Editor/Animation') -Filter '*.cs' -File | ForEach-Object FullName)
Invoke-Compile 'AnimationLab.Editor' $editorSources @($runtimeRefs.FullName + $editorRefs.FullName + $runtimeOutput + $packageOutput) 'UNITY_EDITOR,UNITY_2022_3_OR_NEWER' | Write-Output
# Compile pure tests directly against the installed .NET reference pack: no NuGet restore or Unity process.
$dotnetRoot = Split-Path (Get-Command dotnet).Source -Parent
$framework = (& dotnet --list-runtimes | Where-Object { $_ -match '^Microsoft.NETCore.App ' } | Select-Object -Last 1)
if ($framework -notmatch '^Microsoft.NETCore.App ([0-9]+)\.([^ ]+) ') { throw 'Installed .NET runtime not found.' }
$major = $Matches[1]
$frameworkVersion = $Matches[1] + '.' + $Matches[2]
$pack = Get-ChildItem -LiteralPath (Join-Path $dotnetRoot 'packs/Microsoft.NETCore.App.Ref') -Directory | Where-Object { $_.Name.StartsWith($major + '.') } | Sort-Object { [version]$_.Name } | Select-Object -Last 1
$testRefs = Get-ChildItem -LiteralPath (Join-Path $pack.FullName "ref/net$major.0") -Filter '*.dll' -File
$testOutput = Join-Path $scratch 'AnimationLogicTests.dll'
$testLines = @('-nologo', '-nostdlib+', '-target:exe', '-langversion:9.0', ('-out:"' + $testOutput + '"'))
$testLines += $testRefs | ForEach-Object { '-r:"' + $_.FullName + '"' }
$testLines += @('tools/validation/AnimationLogicTests.cs', 'Client/Assets/Scripts/Animation/ActionTypes.cs', 'Client/Assets/Scripts/Animation/ActionClock.cs', 'packages/com.afauxzhub.character-locomotion/Runtime/LocomotionDynamics.cs') | ForEach-Object { '"' + (Join-Path $repoRoot $_) + '"' }
$testResponse = Join-Path $scratch 'AnimationLogicTests.rsp'
[IO.File]::WriteAllLines($testResponse, $testLines)
& dotnet $compiler -noconfig ('@' + $testResponse)
if ($LASTEXITCODE -ne 0) { throw 'Logic test compilation failed.' }
$runtimeConfig = @{ runtimeOptions = @{ tfm = "net$major.0"; framework = @{ name = 'Microsoft.NETCore.App'; version = $frameworkVersion } } } | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $scratch 'AnimationLogicTests.runtimeconfig.json'), $runtimeConfig)
& dotnet $testOutput
if ($LASTEXITCODE -ne 0) { throw 'Logic tests failed.' }
Write-Output 'No Unity Editor process was started or controlled. This is NOT a Unity 6000.3 import, Play Mode, IK or visual acceptance pass.'
