param(
    [string]$Message = "Update CCounter"
)

Write-Host "=== CCounter Git Save Script ===" -ForegroundColor Cyan

# Kontrollera att vi är i ett Git-repo
git rev-parse --is-inside-work-tree *> $null

if ($LASTEXITCODE -ne 0) {
    Write-Host "Fel: Du verkar inte stå i ett Git-repo." -ForegroundColor Red
    Write-Host "Gå till projektmappen först, t.ex.: cd C:\dev\CCounter"
    exit 1
}

# Kontrollera om .env råkat bli trackad
$trackedEnv = git ls-files .env

if ($trackedEnv -eq ".env") {
    Write-Host "VARNING: .env är redan trackad av Git!" -ForegroundColor Red
    Write-Host "Stoppar för säkerhets skull."
    Write-Host "Kör detta om du vill ta bort .env från Git men behålla filen lokalt:"
    Write-Host "git rm --cached .env" -ForegroundColor Yellow
    exit 1
}

# Kontrollera att .env finns i .gitignore
$gitignoreContent = ""
if (Test-Path ".gitignore") {
    $gitignoreContent = Get-Content ".gitignore" -Raw
}

if ($gitignoreContent -notmatch "(?m)^\.env$") {
    Write-Host "VARNING: .env verkar inte finnas i .gitignore." -ForegroundColor Yellow
    Write-Host "Lägger till .env i .gitignore..."
    Add-Content ".gitignore" "`n.env"
}

Write-Host ""
Write-Host "Git status före add:" -ForegroundColor Cyan
git status --short

Write-Host ""
Write-Host "Lägger till ändringar..." -ForegroundColor Cyan
git add .

# Extra säkerhet: ta bort .env från staging om den ändå skulle hamna där
git restore --staged .env 2>$null

Write-Host ""
Write-Host "Git status efter add:" -ForegroundColor Cyan
git status --short

# Kontrollera om det finns något att committa
git diff --cached --quiet

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Inget nytt att committa." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Skapar commit: $Message" -ForegroundColor Cyan
git commit -m "$Message"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Commit misslyckades." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Pushar till GitHub..." -ForegroundColor Cyan
git push

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Vanlig orsak: branchen saknar upstream." -ForegroundColor Yellow
    Write-Host "Testa manuellt:"
    Write-Host "git push -u origin main" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Om din branch heter master:"
    Write-Host "git push -u origin master" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Klart! Ändringarna är pushade till GitHub." -ForegroundColor Green
