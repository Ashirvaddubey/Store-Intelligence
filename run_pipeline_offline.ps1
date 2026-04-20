$ErrorActionPreference = "Stop"
$baseDir = "c:\Users\GANES\OneDrive\Desktop\Purplle Tech\store-intelligence"
Set-Location $baseDir

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  STORE INTELLIGENCE - OFFLINE PIPELINE (NO DB/REDIS)" -ForegroundColor Cyan
Write-Host "  Events written directly to JSONL files"              -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

# ── Step 1: Create folders ───────────────────────────────────────────────────
Write-Host "`n[1/7] Creating output folders..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "data\clips\STORE_BLR_002" | Out-Null
New-Item -ItemType Directory -Force -Path "data\clips\STORE_BLR_003" | Out-Null
New-Item -ItemType Directory -Force -Path "data\events"              | Out-Null
Write-Host "  => Folders ready." -ForegroundColor Green

# ── Step 2: Move videos ───────────────────────────────────────────────────────
Write-Host "`n[2/7] Moving videos from Downloads..." -ForegroundColor Yellow

function Move-Video($src, $dst) {
    if (Test-Path $src) {
        Move-Item -Path $src -Destination $dst -Force
        Write-Host "  => Moved: $(Split-Path $src -Leaf) -> $dst" -ForegroundColor Green
    } elseif (Test-Path $dst) {
        Write-Host "  => Already in place: $dst" -ForegroundColor DarkGray
    } else {
        Write-Host "  !! NOT FOUND: $src" -ForegroundColor Red
    }
}

Move-Video "c:\Users\GANES\Downloads\CAM 1.mp4" "data\clips\STORE_BLR_002\CAM_ENTRY_01.mp4"
Move-Video "c:\Users\GANES\Downloads\CAM 2.mp4" "data\clips\STORE_BLR_002\CAM_FLOOR_01.mp4"
Move-Video "c:\Users\GANES\Downloads\CAM 3.mp4" "data\clips\STORE_BLR_002\CAM_BILLING_01.mp4"
Move-Video "c:\Users\GANES\Downloads\CAM 4.mp4" "data\clips\STORE_BLR_003\CAM_ENTRY_01.mp4"
Move-Video "c:\Users\GANES\Downloads\CAM 5.mp4" "data\clips\STORE_BLR_003\CAM_FLOOR_01.mp4"

# ── Step 3-7: Run YOLO detection (no --api-url) ───────────────────────────────
function Run-Detection($step, $label, $video, $store, $cam, $out) {
    Write-Host "`n[$step/7] $label..." -ForegroundColor Yellow
    if (-not (Test-Path $video)) {
        Write-Host "  !! Skipping - video not found: $video" -ForegroundColor Red
        return
    }
    python -m pipeline.detect `
        --video       $video  `
        --store-id    $store  `
        --camera-id   $cam    `
        --layout      "data\store_layout.json" `
        --output      $out    `
        --skip-frames 3       `
        --conf-thresh 0.35    `
        --device      cpu

    if ($LASTEXITCODE -eq 0) {
        $lines = (Get-Content $out -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
        Write-Host "  => Done! $lines events -> $out" -ForegroundColor Green
    } else {
        Write-Host "  !! Pipeline failed (exit code $LASTEXITCODE)" -ForegroundColor Red
    }
}

Run-Detection 3 "STORE_BLR_002 ENTRY"   "data\clips\STORE_BLR_002\CAM_ENTRY_01.mp4"   "STORE_BLR_002" "CAM_ENTRY_01"   "data\events\STORE_BLR_002_CAM_ENTRY.jsonl"
Run-Detection 4 "STORE_BLR_002 FLOOR"   "data\clips\STORE_BLR_002\CAM_FLOOR_01.mp4"   "STORE_BLR_002" "CAM_FLOOR_01"   "data\events\STORE_BLR_002_CAM_FLOOR.jsonl"
Run-Detection 5 "STORE_BLR_002 BILLING" "data\clips\STORE_BLR_002\CAM_BILLING_01.mp4" "STORE_BLR_002" "CAM_BILLING_01" "data\events\STORE_BLR_002_CAM_BILLING.jsonl"
Run-Detection 6 "STORE_BLR_003 ENTRY"   "data\clips\STORE_BLR_003\CAM_ENTRY_01.mp4"   "STORE_BLR_003" "CAM_ENTRY_01"   "data\events\STORE_BLR_003_CAM_ENTRY.jsonl"
Run-Detection 7 "STORE_BLR_003 FLOOR"   "data\clips\STORE_BLR_003\CAM_FLOOR_01.mp4"   "STORE_BLR_003" "CAM_FLOOR_01"   "data\events\STORE_BLR_003_CAM_FLOOR.jsonl"

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host "`n=======================================================" -ForegroundColor Cyan
Write-Host "  ALL DONE! Event file summary:" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Cyan

Get-ChildItem "data\events\*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
    $lines = (Get-Content $_.FullName | Measure-Object -Line).Lines
    Write-Host "  $($_.Name): $lines events" -ForegroundColor White
}
