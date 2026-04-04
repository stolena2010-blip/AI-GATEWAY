# register_services.ps1 — Register Windows Services for DrawingAI Pro profiles
# Run as Administrator

param(
    [string]$PythonPath = "C:\DrawingAI\.venv\Scripts\python.exe",
    [string]$ProjectPath = "C:\DrawingAI",
    [string]$NssmPath = "C:\nssm\nssm.exe"
)

$profiles = @("quotes", "orders", "invoices", "delivery", "complaints")

foreach ($profile in $profiles) {
    $serviceName = "DrawingAI_$profile"
    $displayName = "DrawingAI Pro - $profile"

    Write-Host "Registering service: $serviceName" -ForegroundColor Green

    # Remove existing service if present
    $existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "  Removing existing service..."
        & $NssmPath remove $serviceName confirm
    }

    # Register with NSSM
    & $NssmPath install $serviceName $PythonPath
    & $NssmPath set $serviceName AppParameters "run_pipeline.py --profile $profile"
    & $NssmPath set $serviceName AppDirectory $ProjectPath
    & $NssmPath set $serviceName DisplayName $displayName
    & $NssmPath set $serviceName Description "DrawingAI Pro - $profile document processing pipeline"
    & $NssmPath set $serviceName Start SERVICE_AUTO_START
    & $NssmPath set $serviceName AppStdout "$ProjectPath\logs\${profile}_service.log"
    & $NssmPath set $serviceName AppStderr "$ProjectPath\logs\${profile}_service_err.log"
    & $NssmPath set $serviceName AppRotateFiles 1
    & $NssmPath set $serviceName AppRotateBytes 5242880

    Write-Host "  Service '$serviceName' registered successfully" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "All services registered. Start with:" -ForegroundColor Yellow
foreach ($profile in $profiles) {
    Write-Host "  Start-Service DrawingAI_$profile"
}
