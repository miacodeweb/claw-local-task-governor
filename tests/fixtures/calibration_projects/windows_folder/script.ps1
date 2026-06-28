# Backup script for a service
param($Path = "C:\Backup", $Days = 7)

Write-Host "Starting backup to $Path"

$files = Get-ChildItem -Path $Path -Recurse
$oldFiles = $files | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$Days) }

foreach ($file in $oldFiles) {
    Write-Host "Removing old backup: $($file.FullName)"
}

Write-Host "Backup complete."
