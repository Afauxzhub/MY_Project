param(
    [Parameter(Mandatory=$true)][string]$SourceAssets,
    [Parameter(Mandatory=$true)][string]$ModelPrefab,
    [Parameter(Mandatory=$true)][string]$SheathedClips,
    [Parameter(Mandatory=$true)][string]$DrawnClips,
    [string]$OutputName = 'animation-reference'
)
# Filesystem-only preparation. Does not launch Unity, import into Assets, or modify source files.
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$sourceRoot = (Resolve-Path -LiteralPath $SourceAssets).Path.TrimEnd('\', '/')
$scratchRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot '.validation-temp'))
if ($OutputName -notmatch '^[A-Za-z0-9_-]+$') { throw 'OutputName must be a simple directory name.' }
$output = [IO.Path]::GetFullPath((Join-Path $scratchRoot $OutputName))
if (!$output.StartsWith($scratchRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must remain under .validation-temp.' }
if (Test-Path -LiteralPath $output) { throw 'Output already exists. Choose a new name; this tool never overwrites a reference pack.' }
function Resolve-Source([string]$Path) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (!$resolved.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Source is outside the selected Assets root: $Path" }
    return $resolved
}
$prefabPath = Resolve-Source $ModelPrefab
$sheathedPath = Resolve-Source $SheathedClips
$drawnPath = Resolve-Source $DrawnClips
if ([IO.Path]::GetExtension($prefabPath) -ne '.prefab') { throw 'This preparer accepts an unpacked text prefab, not a model importer or prefab variant.' }
$prefabText = [IO.File]::ReadAllText($prefabPath)
if (!$prefabText.StartsWith('%YAML')) { throw 'Model prefab must be Unity YAML.' }
$blocks = [regex]::Split($prefabText, '(?m)(?=^--- !u!)')
$allowed = @(1, 4, 23, 33, 95, 137)
$keptIds = [Collections.Generic.HashSet[string]]::new()
$selected = [Collections.Generic.List[string]]::new()
foreach ($block in $blocks) {
    if ($block -match '^--- !u!([0-9]+) &(-?[0-9]+)') {
        if ([int]$Matches[1] -eq 1001) { throw 'Nested prefab instance found. Unpack a local copy manually after approval; do not guess dependency overrides.' }
        if ($allowed -contains [int]$Matches[1]) { $null = $keptIds.Add($Matches[2]); $selected.Add($block) }
    } else { $selected.Add($block) }
}
$sanitized = ($selected -join '')
$sanitized = [regex]::Replace($sanitized, '(?m)^  - component: \{fileID: (-?[0-9]+)\}\r?\n', {
    param($match)
    if ($keptIds.Contains($match.Groups[1].Value)) { return $match.Value }
    return ''
})
# Strip source materials/shaders and Animator controller. Runtime scripts and colliders were excluded by class ID.
$sanitized = [regex]::Replace($sanitized, '(?m)^  m_Materials:\r?\n(?:  - .*(?:\r?\n|$))+', "  m_Materials: []`n")
$sanitized = [regex]::Replace($sanitized, '(?m)^  m_Controller: .*$', '  m_Controller: {fileID: 0}')
$dependencies = @([regex]::Matches($sanitized, 'm_(?:Mesh|Avatar): \{fileID: -?[0-9]+, guid: ([a-f0-9]{32}), type: [0-9]+\}') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
$allGuids = @([regex]::Matches($sanitized, 'guid: ([a-f0-9]{32})') | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -ne ('0' * 32) } | Sort-Object -Unique)
foreach ($guid in $allGuids) { if ($dependencies -notcontains $guid) { throw "Unsupported external prefab dependency: $guid. No unsafe dependency copying performed." } }
$guidFiles = @{}
if ($dependencies.Count -gt 0) {
    $rgArgs = @('-l', '--glob', '*.meta', '-F')
    foreach ($guid in $dependencies) { $rgArgs += @('-e', ('guid: ' + $guid)) }
    $rgArgs += @('--', $sourceRoot)
    $metas = @(& rg @rgArgs)
    if ($LASTEXITCODE -gt 1) { throw 'Dependency metadata search failed.' }
    foreach ($meta in $metas) {
        $content = [IO.File]::ReadAllText($meta)
        if ($content -match '(?m)^guid: ([a-f0-9]{32})') {
            $guid = $Matches[1]
            if ($guidFiles.ContainsKey($guid)) { throw "Duplicate source GUID: $guid" }
            $guidFiles[$guid] = $meta.Substring(0, $meta.Length - 5)
        }
    }
    foreach ($guid in $dependencies) { if (!$guidFiles.ContainsKey($guid)) { throw "Missing source mesh/avatar dependency: $guid" } }
}
New-Item -ItemType Directory -Path $output | Out-Null
$manifest = [Collections.Generic.List[object]]::new()
function Write-GeneratedAsset([string]$Relative, [string]$Text, [string]$MainFileId) {
    $target = Join-Path $output $Relative
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    [IO.File]::WriteAllText($target, $Text, [Text.UTF8Encoding]::new($false))
    $guid = [guid]::NewGuid().ToString('N')
    $meta = "fileFormatVersion: 2`nguid: $guid`nNativeFormatImporter:`n  externalObjects: {}`n  mainObjectFileID: $MainFileId`n  userData: `n  assetBundleName: `n  assetBundleVariant: `n"
    if ([IO.Path]::GetExtension($Relative) -eq '.prefab') { $meta = "fileFormatVersion: 2`nguid: $guid`nPrefabImporter:`n  externalObjects: {}`n  userData: `n  assetBundleName: `n  assetBundleVariant: `n" }
    [IO.File]::WriteAllText($target + '.meta', $meta, [Text.UTF8Encoding]::new($false))
}
foreach ($guid in $dependencies) {
    $source = Resolve-Source $guidFiles[$guid]
    if ([IO.Path]::GetExtension($source) -ne '.asset') { throw 'Mesh/avatar dependencies must be standalone .asset files.' }
    $newGuid = [guid]::NewGuid().ToString('N')
    $relative = 'Dependencies/' + $newGuid + '.asset'
    $target = Join-Path $output $relative
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    [IO.File]::Copy($source, $target, $false)
    $meta = [IO.File]::ReadAllText($source + '.meta') -replace ('guid: ' + $guid), ('guid: ' + $newGuid)
    [IO.File]::WriteAllText($target + '.meta', $meta, [Text.UTF8Encoding]::new($false))
    $sanitized = $sanitized.Replace('guid: ' + $guid, 'guid: ' + $newGuid)
    $manifest.Add(@{ source = $source; sourceSHA256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash; destination = $relative; kind = 'mesh-or-avatar' })
}
Write-GeneratedAsset 'Model.prefab' $sanitized '100100000'
$manifest.Add(@{ source = $prefabPath; sourceSHA256 = (Get-FileHash -LiteralPath $prefabPath -Algorithm SHA256).Hash; destination = 'Model.prefab'; kind = 'render-only-prefab' })
foreach ($set in @(@{ Name = 'Sheathed'; Path = $sheathedPath }, @{ Name = 'Drawn'; Path = $drawnPath })) {
    foreach ($clip in Get-ChildItem -LiteralPath $set.Path -Filter '*.anim' -File) {
        $text = [IO.File]::ReadAllText($clip.FullName)
        if (!$text.StartsWith('%YAML')) { throw "Clip is not Unity YAML: $($clip.Name)" }
        # m_Events is the final field in standalone serialized AnimationClips. Reject unexpected following object blocks.
        if ($text -notmatch '(?m)^  m_Events:' -or [regex]::Matches($text, '(?m)^--- !u!').Count -ne 1) { throw 'Unexpected clip structure; no guessed rewrite performed.' }
        $text = [regex]::Replace($text, '(?ms)^  m_Events:.*\z', "  m_Events: []`n")
        $relative = $set.Name + '/' + $clip.Name
        Write-GeneratedAsset $relative $text '7400000'
        $manifest.Add(@{ source = $clip.FullName; sourceSHA256 = (Get-FileHash -LiteralPath $clip.FullName -Algorithm SHA256).Hash; destination = $relative; kind = 'event-free-clip-copy' })
    }
}
$result = @{ schemaVersion = 1; localOnly = $true; sourceUnmodified = $true; notes = @('No Unity import or runtime validation performed.', 'Materials removed; importer supplies a neutral preview material.', 'Animation paths are NOT retargeted. Use explicit prefix remapping and binding audit.', 'This manifest contains local source paths and must never be committed.'); files = $manifest }
[IO.File]::WriteAllText((Join-Path $output 'local-manifest.json'), ($result | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Write-Output "Prepared $($manifest.Count) local reference files under $output. Nothing copied into Client/Assets; Unity and Max were not used."
