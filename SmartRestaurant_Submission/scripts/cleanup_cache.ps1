param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$manifestPath = Join-Path $projectRoot 'cleanup_manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Run submission_audit.py before cleanup.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([IO.Path]::GetFullPath($manifest.root) -ne $projectRoot) { throw 'Manifest root mismatch.' }
$records = @()
foreach ($item in $manifest.items) {
    if ($item.action -ne 'DELETE_CACHE' -or $item.category -ne 'CACHE') { continue }
    $relative = $item.path.Replace('/', [IO.Path]::DirectorySeparatorChar)
    if ($relative -match '(^|[\\/])\.venv([\\/]|$)') { continue }
    if ($relative -notmatch '(^|[\\/])(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|htmlcov|coverage)([\\/]|$)|\.pyc$|(^|[\\/])\.coverage$') { throw 'Invalid cache candidate.' }
    $target = [IO.Path]::GetFullPath((Join-Path $projectRoot $relative))
    if (-not $target.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Target outside project.' }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { continue }
    $entry = Get-Item -LiteralPath $target
    $ancestor = $entry
    while ($ancestor -and $ancestor.FullName -ne $projectRoot) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing cache through a reparse point.' }
        $ancestor = if ($ancestor.PSIsContainer) { $ancestor.Parent } else { $ancestor.Directory }
    }
    $records += [pscustomobject]@{path=$item.path;bytes=$entry.Length;action=$(if ($Apply) {'DELETED_CACHE'} else {'DRY_RUN'})}
    if ($Apply) { Remove-Item -LiteralPath $target -Force }
}
$report = [pscustomobject]@{apply=[bool]$Apply;root=$projectRoot;files=$records.Count;bytes=($records | Measure-Object bytes -Sum).Sum;items=$records}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $projectRoot 'submission_audit/cache_cleanup.json') -Encoding UTF8
Write-Output "Cache candidates: $($report.files); bytes: $($report.bytes); apply: $Apply"
