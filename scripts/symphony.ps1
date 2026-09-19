param(
    [ValidateSet('Start', 'StartOffline', 'Stop', 'Status', 'Logs')]
    [string]$Action = 'Status',
    [switch]$UseHostCredentials
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$runtimeRoot = Join-Path $repoRoot '.local\symphony'
$containerName = 'innovation-symphony'
$imageName = 'innovation-symphony:0.0.3'
$seccompPath = Join-Path $repoRoot 'deploy\symphony-seccomp.json'

function Invoke-Docker {
    param([string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker failed with exit code $LASTEXITCODE" }
}

switch ($Action) {
    'Status' {
        Invoke-Docker -Arguments @('ps', '-a', '--filter', "name=^/$containerName$", '--format', '{{.Names}}: {{.Status}} | {{.Ports}}')
        try {
            Invoke-RestMethod 'http://127.0.0.1:43190/api/v1/state' | ConvertTo-Json -Depth 6
        } catch { Write-Output 'Dashboard is not reachable.' }
        return
    }
    'Logs' { Invoke-Docker -Arguments @('logs', '--tail', '80', $containerName); return }
    'Stop' { Invoke-Docker -Arguments @('stop', $containerName); return }
}

if ($Action -eq 'Start' -and -not $UseHostCredentials) {
    throw 'Authenticated startup requires explicit -UseHostCredentials: shares the GitHub CLI token with Symphony and mounts Codex auth.json read-only. StartOffline needs neither.'
}
$existing = & docker ps -a --filter "name=^/$containerName$" --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker is not available.' }
if ($existing) {
    throw 'Container already exists. Stop it and remove only the innovation-symphony container before changing mode; .local/symphony/data is retained.'
}

$dataRoot = Join-Path $runtimeRoot 'data'
New-Item -ItemType Directory -Force -Path $dataRoot, (Join-Path $dataRoot 'codex') | Out-Null
$workflowPath = Join-Path $repoRoot 'WORKFLOW.md'
if ($Action -eq 'StartOffline') { $workflowPath = Join-Path $runtimeRoot 'smoke.md' }
if (-not (Test-Path -LiteralPath $workflowPath -PathType Leaf)) { throw "Missing workflow: $workflowPath" }
if (-not (Test-Path -LiteralPath $seccompPath -PathType Leaf)) { throw "Missing sandbox profile: $seccompPath" }

$dockerArguments = @(
    'run', '-d', '--name', $containerName,
    '--label', 'app=innovation-symphony', '--restart', 'unless-stopped',
    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
    '--security-opt', "seccomp=$seccompPath",
    '--pids-limit', '512', '--memory', '4g', '--cpus', '2',
    '-p', '127.0.0.1:43190:43190',
    '--mount', "type=bind,source=$workflowPath,target=/config/WORKFLOW.md,readonly",
    '--mount', "type=bind,source=$dataRoot,target=/data",
    '--mount', "type=bind,source=$dataRoot\codex,target=/home/node/.codex"
)

$oldGitHubToken = $env:GITHUB_TOKEN
try {
    if ($Action -eq 'Start') {
        $codexHomePath = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
        $authPath = Join-Path $codexHomePath 'auth.json'
        if (-not (Test-Path -LiteralPath $authPath -PathType Leaf)) { throw 'Codex auth.json not found. Log in to Codex first.' }
        $ghTokenOutput = & gh auth token --hostname github.com
        if ($LASTEXITCODE -ne 0 -or -not $ghTokenOutput) { throw 'GitHub CLI authentication is unavailable.' }
        $env:GITHUB_TOKEN = ($ghTokenOutput -join '').Trim()
        $ghTokenOutput = $null
        $dockerArguments += @('--env', 'GITHUB_TOKEN', '--mount', "type=bind,source=$authPath,target=/home/node/.codex/auth.json,readonly")
    }
    $dockerArguments += @($imageName, '/config/WORKFLOW.md', '--logs-root', '/data/logs', '--i-understand-that-this-will-be-running-without-the-usual-guardrails')
    Invoke-Docker -Arguments $dockerArguments
} finally {
    $env:GITHUB_TOKEN = $oldGitHubToken
}

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try {
        $state = Invoke-RestMethod 'http://127.0.0.1:43190/api/v1/state'
        Write-Output "Symphony is available at http://127.0.0.1:43190/ (mode: $Action)."
        $state.counts | ConvertTo-Json
        return
    } catch { Start-Sleep -Seconds 1 }
}
throw 'Container started but dashboard health check failed. Inspect logs; startup is not verified.'
