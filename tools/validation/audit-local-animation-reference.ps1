param([Parameter(Mandatory=$true)][string]$PackDirectory, [string]$FromPrefix = '', [string]$ToPrefix = '')
$ErrorActionPreference = 'Stop'
$pack = (Resolve-Path -LiteralPath $PackDirectory).Path
$manifest = Get-Content -LiteralPath (Join-Path $pack 'local-manifest.json') -Raw | ConvertFrom-Json
$names = @{}; $parents = @{}; $objects = @{}
$text = [IO.File]::ReadAllText((Join-Path $pack 'Model.prefab'))
foreach ($block in [regex]::Split($text, '(?m)(?=^--- !u!)')) {
    if ($block -notmatch '^--- !u!([0-9]+) &(-?[0-9]+)') { continue }
    $type = [int]$Matches[1]; $id = $Matches[2]
    if ($type -eq 1 -and $block -match '(?m)^  m_Name: (.*)\r?$') {
        $value = $Matches[1].TrimEnd("`r")
        if ($value.StartsWith('"')) { $value = $value | ConvertFrom-Json }
        $names[$id] = $value
    }
    if ($type -eq 4) {
        if ($block -notmatch 'm_GameObject: \{fileID: (-?[0-9]+)\}') { throw 'Transform missing GameObject.' }
        $objects[$id] = $Matches[1]
        if ($block -notmatch 'm_Father: \{fileID: (-?[0-9]+)\}') { throw 'Transform missing parent.' }
        $parents[$id] = $Matches[1]
    }
}
$paths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$null = $paths.Add('')
foreach ($id in $parents.Keys) {
    if ($parents[$id] -eq '0') { continue }
    $parts = [Collections.Generic.List[string]]::new(); $cursor = $id; $seen = [Collections.Generic.HashSet[string]]::new()
    while ($parents[$cursor] -ne '0') {
        if (!$seen.Add($cursor) -or !$parents.ContainsKey($cursor)) { throw 'Invalid transform hierarchy.' }
        $parts.Insert(0, $names[$objects[$cursor]]); $cursor = $parents[$cursor]
    }
    if (!$paths.Add(($parts -join '/'))) { throw 'Ambiguous duplicate bone path.' }
}
$results = @()
foreach ($set in @('Sheathed', 'Drawn')) {
    foreach ($clip in Get-ChildItem -LiteralPath (Join-Path $pack $set) -Filter '*.anim' -File) {
        $clipText = [IO.File]::ReadAllText($clip.FullName)
        $bindings = @([regex]::Matches($clipText, '(?m)^    path: ([^\r\n]*(?:\r?\n      [^\r\n]+)*)') | ForEach-Object { ($_.Groups[1].Value -replace '\r?\n      ', ' ').TrimEnd("`r") } | Sort-Object -Unique)
        $missing = @(); $mappedMissing = @()
        foreach ($path in $bindings) {
            if (!$paths.Contains($path)) { $missing += $path }
            $mapped = $path
            if ($FromPrefix -and ($path -eq $FromPrefix -or $path.StartsWith($FromPrefix + '/', [StringComparison]::Ordinal))) { $mapped = ($ToPrefix + $path.Substring($FromPrefix.Length)).TrimStart('/') }
            if (!$paths.Contains($mapped)) { $mappedMissing += $mapped }
        }
        $results += @{ clip = $clip.Name; set = $set; paths = $bindings.Count; missing = $missing; mappedMissing = $mappedMissing; hasGenericRoot = ($clipText -match 'm_HasGenericRootTransform: 1') }
    }
}
$changed = @()
foreach ($file in $manifest.files) { if ((Get-FileHash -LiteralPath $file.source -Algorithm SHA256).Hash -ne $file.sourceSHA256) { $changed += $file.source } }
$report = @{ schemaVersion = 1; bonePathCount = $paths.Count; sourceHashMismatches = $changed; candidatePrefix = @{ from = $FromPrefix; to = $ToPrefix }; clips = $results; limitation = 'Path-name coverage only. Does not prove component/property compatibility, bindpose, scale, retargeting, root-motion extraction or visual quality.' }
[IO.File]::WriteAllText((Join-Path $pack 'local-binding-audit.json'), ($report | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
$results | Group-Object set | ForEach-Object {
    [pscustomobject]@{ Set = $_.Name; Clips = $_.Count; FullyBound = @($_.Group | Where-Object { $_.missing.Count -eq 0 }).Count; AfterCandidateMap = @($_.Group | Where-Object { $_.mappedMissing.Count -eq 0 }).Count; HasGenericRoot = @($_.Group | Where-Object { $_.hasGenericRoot }).Count }
} | Format-Table -AutoSize
Write-Output "Source hashes unchanged: $($changed.Count -eq 0); model paths: $($paths.Count). No Unity runtime checks performed."
if ($changed.Count -ne 0) { throw 'Source assets changed since pack preparation.' }
