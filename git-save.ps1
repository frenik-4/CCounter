param(
    [string]$Message = "Update CCounter"
)

Write-Host "=== CCounter Git Save Script ===" -ForegroundColor Cyan

git rev-parse --is-inside-work-tree *> $null

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: You are not inside a Git repository." -ForegroundColor Red
    Write-Host "Go to the project folder first:"
    Write-Host "cd C:\dev\CCounter"
    exit 1
}

$trackedEnv = git ls-files .env

if ($trackedEnv -eq ".env") {
    Write-Host "ERROR: .env is already tracked by Git." -ForegroundColor Red
    Write-Host "Run this to remove it from Git but keep it locally:"
    Write-Host "git rm --cached .env" -ForegroundColor Yellow
    exit 1
}

$gitignoreContent = ""

if (Test-Path ".gitignore") {
    $gitignoreContent = Get-Content ".gitignore" -Raw
}

if ($gitignoreContent -notmatch "(?m)^\.env$") {
    Write-Host "WARNING: .env is not in .gitignore. Adding it now." -ForegroundColor Yellow
    Add-Content ".gitignore" "`n.env"
}

Write-Host ""
Write-Host "Git status before add:" -ForegroundColor Cyan
git status --short

Write-Host ""
Write-Host "Adding changes..." -ForegroundColor Cyan
git add .

git restore --staged .env 2>$null

Write-Host ""
Write-Host "Git status after add:" -ForegroundColor Cyan
git status --short

git diff --cached --quiet

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Nothing new to commit." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Creating commit: $Message" -ForegroundColor Cyan
git commit -m "$Message"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Commit failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
git push

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Push failed." -ForegroundColor Yellow
    Write-Host "Try one of these manually:"
    Write-Host "git push -u origin main" -ForegroundColor Yellow
    Write-Host "git push -u origin master" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Done. Changes pushed to GitHub." -ForegroundColor Green