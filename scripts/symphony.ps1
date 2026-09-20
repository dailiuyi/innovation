param(
    [ValidateSet('Build', 'BuildBase', 'Doctor', 'Start', 'StartOffline', 'Stop', 'Status', 'Logs', 'Models', 'ValidateModel', 'PrepareTask', 'TaskStatus', 'ResumeTask')]
    [string]$Action = 'Status',
    [switch]$UseHostCredentials,
    [string]$Model = 'gpt-6-astra',
    [string]$Effort = 'low',
    [string]$DeepSeekKeyFile,
    [int]$Issue,
    [string]$PlanFile,
    [string]$Reason,
    [string]$WorkspaceVolume = 'innovation-symphony-workspaces',
    [ValidateSet('quick', 'frontend')][string]$Profile = 'quick',
    [switch]$Java,
    [ValidateRange(1, 4)][int]$BuildConcurrency = 1
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$runtimeRoot = Join-Path $repoRoot '.local\symphony'
$containerName = 'innovation-symphony'
$imageName = 'innovation-symphony:0.0.3-java-v2'
$seccompPath = Join-Path $repoRoot 'deploy\symphony-seccomp.json'

function Invoke-Docker {
    param([string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker failed with exit code $LASTEXITCODE" }
}

switch ($Action) {
    'Doctor' {
        & python (Join-Path $PSScriptRoot 'symphony_environment.py') verify
        if ($LASTEXITCODE -ne 0) { throw 'Environment version check failed; inspect drift before updating its baseline.' }
        $baseline = Get-Content -LiteralPath (Join-Path $repoRoot 'deploy/symphony-environment.lock.json') -Raw | ConvertFrom-Json
        $actualImage = & docker inspect --format '{{.Image}}' $containerName
        if ($LASTEXITCODE -ne 0 -or $actualImage -ne $baseline.imageId) { throw 'Running container uses another image.' }
        $probeArgs = @('exec', $containerName, 'python3', '/opt/symphony-execution/symphony_environment.py',
            'probe', '--lock', '/opt/symphony-execution/environment.lock.json', '--profile', $Profile)
        if ($Java) { $probeArgs += '--java' }
        if ($Issue -gt 0) { $probeArgs += @('--workspace', "/data/workspaces/GH-$Issue", '--plan', "/data/task-control/GH-$Issue/plan.json") }
        Invoke-Docker -Arguments $probeArgs
        return
    }
    'BuildBase' {
        $asset = Join-Path $runtimeRoot 'downloads/symphony-v0.0.3-linux_x86_64'
        $expected = 'ea35a04a54a6d37c0cafe3f195da871e47614a8c05765b90dbb4cac32e1435ee'
        if (-not (Test-Path -LiteralPath $asset) -or (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
            throw 'Provide the checksum-verified official Symphony v0.0.3 Linux x86_64 release under .local/symphony/downloads first.'
        }
        $buildRoot = Join-Path $runtimeRoot 'build-base'
        New-Item -ItemType Directory -Force -Path (Join-Path $buildRoot 'downloads') | Out-Null
        @('*', '!Dockerfile', '!downloads/', '!downloads/symphony-v0.0.3-linux_x86_64') |
            Set-Content -LiteralPath (Join-Path $buildRoot '.dockerignore') -Encoding utf8
        Copy-Item -LiteralPath (Join-Path $repoRoot 'deploy/symphony-base.Dockerfile') -Destination (Join-Path $buildRoot 'Dockerfile')
        Copy-Item -LiteralPath $asset -Destination (Join-Path $buildRoot 'downloads/symphony-v0.0.3-linux_x86_64')
        Invoke-Docker -Arguments @('build', '--tag', 'innovation-symphony:0.0.3', $buildRoot)
        return
    }
    { $_ -in 'PrepareTask', 'TaskStatus', 'ResumeTask' } {
        if ($Issue -lt 1) { throw 'Positive -Issue required' }
        $taskArgs = @((Join-Path $PSScriptRoot 'symphony_task.py'),
            @{PrepareTask='prepare'; TaskStatus='status'; ResumeTask='resume'}[$Action],
            '--state-root', (Join-Path $runtimeRoot 'data/task-control'), '--issue', "GH-$Issue")
        if ($Action -eq 'PrepareTask') { $taskArgs += @('--plan', $PlanFile) }
        if ($Action -eq 'ResumeTask') {
            $taskArgs += @('--reason', $Reason)
            if ($PlanFile) { $taskArgs += @('--plan', $PlanFile) }
        }
        & python @taskArgs
        if ($LASTEXITCODE -ne 0) { throw 'Task control command failed' }
        return
    }
    'Build' {
        # An explicit minimal context avoids sending source, auth or logs to Docker.
        $buildRoot = Join-Path $runtimeRoot 'build-validation'
        New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
        @('*', '!Dockerfile', '!requirements-review.txt', '!prepare_symphony_workspace.py') |
            Set-Content -LiteralPath (Join-Path $buildRoot '.dockerignore') -Encoding utf8
        Copy-Item -LiteralPath (Join-Path $repoRoot 'deploy/symphony.Dockerfile') -Destination (Join-Path $buildRoot 'Dockerfile')
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'requirements-review.txt') -Destination $buildRoot
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'prepare_symphony_workspace.py') -Destination $buildRoot
        Invoke-Docker -Arguments @('build', '--tag', $imageName, $buildRoot)
        return
    }
    'Status' {
        Invoke-Docker -Arguments @('ps', '-a', '--filter', "name=^/$containerName$", '--format', '{{.Names}}: {{.Status}} | {{.Ports}}')
        try {
            Invoke-RestMethod 'http://127.0.0.1:43190/api/v1/state' | ConvertTo-Json -Depth 6
        } catch { Write-Output 'Dashboard is not reachable.' }
        return
    }
    'Logs' { Invoke-Docker -Arguments @('logs', '--tail', '80', $containerName); return }
    'Stop' { Invoke-Docker -Arguments @('stop', $containerName); return }
    'Models' {
        Invoke-Docker -Arguments @('exec', $containerName, 'python3', '/opt/symphony-routing/symphony_model_probe.py',
            'catalog', '--output', '/data/logs/model-catalog.json')
        return
    }
    'ValidateModel' {
        Invoke-Docker -Arguments @('exec', $containerName, 'python3', '/opt/symphony-routing/symphony_model_probe.py',
            'validate', '--model', $Model, '--effort', $Effort, '--output', '/data/logs/model-validation.json')
        return
    }
}

if ($Action -eq 'Start' -and -not $UseHostCredentials) {
    throw 'Authenticated startup requires explicit -UseHostCredentials: shares the GitHub CLI token with Symphony and mounts Codex auth.json read-only. StartOffline needs neither.'
}
& python (Join-Path $PSScriptRoot 'symphony_environment.py') verify
if ($LASTEXITCODE -ne 0) { throw 'Unverified environment version; inspect drift and run explicit validation before refreshing the lock.' }
$existing = & docker ps -a --filter "name=^/$containerName$" --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker is not available.' }
if ($existing) {
    throw 'Container already exists. Stop it and remove only the innovation-symphony container before changing mode; .local/symphony/data is retained.'
}

$dataRoot = Join-Path $runtimeRoot 'data'
$cacheRoot = Join-Path $dataRoot 'cache'
New-Item -ItemType Directory -Force -Path $dataRoot, (Join-Path $dataRoot 'codex'), (Join-Path $cacheRoot 'pip'), (Join-Path $cacheRoot 'npm') | Out-Null
$workflowPath = Join-Path $repoRoot 'WORKFLOW.md'
if ($Action -eq 'StartOffline') { $workflowPath = Join-Path $runtimeRoot 'smoke.md' }
if (-not (Test-Path -LiteralPath $workflowPath -PathType Leaf)) { throw "Missing workflow: $workflowPath" }
if (-not (Test-Path -LiteralPath $seccompPath -PathType Leaf)) { throw "Missing sandbox profile: $seccompPath" }
$adapterPath = Join-Path $PSScriptRoot 'symphony_codex_adapter.py'
$probePath = Join-Path $PSScriptRoot 'symphony_model_probe.py'
$publishPath = Join-Path $PSScriptRoot 'symphony_publish.py'
$taskPath = Join-Path $PSScriptRoot 'symphony_task.py'
$executionFiles = @('agent_check.py', 'frontend_control.py', 'harness.py', 'check_java.py', 'test_frontend_control.py', 'test_symphony_task.py', 'test_symphony_publish.py', 'symphony_task.py', 'symphony_publish.py', 'symphony_entrypoint.py', 'migrate_symphony_workspaces.py', 'test_migrate_symphony_workspaces.py', 'symphony_environment.py', 'test_symphony_environment_lock.py', 'verify_symphony_concurrency.py')
foreach ($executionFile in $executionFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $executionFile) -PathType Leaf)) {
        throw "Missing execution script: $executionFile"
    }
}
foreach ($routingPath in @($adapterPath, $probePath, $publishPath, $taskPath)) {
    if (-not (Test-Path -LiteralPath $routingPath -PathType Leaf)) { throw "Missing routing script: $routingPath" }
}

# Keep task working trees and task-local dependencies on Linux-native storage.
# Existing Windows working trees must be copied and verified explicitly before hiding them.
if ($WorkspaceVolume -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]+$') { throw 'Invalid workspace volume name' }
Invoke-Docker -Arguments @('volume', 'create', '--label', 'app=innovation-symphony', $WorkspaceVolume)
$legacyWorkspaces = Join-Path $dataRoot 'workspaces'
$legacyNonEmpty = (Test-Path -LiteralPath $legacyWorkspaces) -and
    @(Get-ChildItem -LiteralPath $legacyWorkspaces -Directory).Count -gt 0
if ($legacyNonEmpty) {
    Invoke-Docker -Arguments @('run', '--rm', '--network', 'none', '--user', '1000:1000',
        '--mount', "type=volume,source=$WorkspaceVolume,target=/workspaces", '--entrypoint', 'python3',
        $imageName, '-c', 'import json; p=json.load(open("/workspaces/.migration-verified.json")); assert p["verified"] is True, "Migrate and verify legacy workspaces first"')
}
Invoke-Docker -Arguments @('run', '--rm', '--network', 'none', '--user', '0:0',
    '--cap-drop', 'ALL', '--cap-add', 'CHOWN', '--security-opt', 'no-new-privileges',
    '--mount', "type=volume,source=$WorkspaceVolume,target=/workspaces", '--entrypoint', 'python3',
    $imageName, '-c', 'import os
from pathlib import Path
os.chown("/workspaces",0,0)
try:
    Path("/workspaces/.volume-initialized").touch()
finally:
    os.chown("/workspaces",1000,1000)')

$dockerArguments = @(
    'run', '-d', '--name', $containerName,
    '--label', 'app=innovation-symphony', '--restart', 'unless-stopped',
    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
    '--security-opt', "seccomp=$seccompPath",
    '--pids-limit', '512', '--memory', '4g', '--cpus', '2',
    '--env', 'SYMPHONY_CONTROL_ROOT=/data/task-control',
    '--env', "SYMPHONY_BUILD_CONCURRENCY=$BuildConcurrency",
    '--env', 'SYMPHONY_ENVIRONMENT_LOCK=/opt/symphony-execution/environment.lock.json',
    '--mount', "type=bind,source=$repoRoot/deploy/symphony-environment.lock.json,target=/opt/symphony-execution/environment.lock.json,readonly",
    '-p', '127.0.0.1:43190:43190',
    '--mount', "type=bind,source=$workflowPath,target=/config/WORKFLOW.md,readonly",
    '--mount', "type=bind,source=$adapterPath,target=/opt/symphony-routing/symphony_codex_adapter.py,readonly",
    '--mount', "type=bind,source=$probePath,target=/opt/symphony-routing/symphony_model_probe.py,readonly",
    '--mount', "type=bind,source=$publishPath,target=/opt/symphony-routing/symphony_publish.py,readonly",
    '--mount', "type=bind,source=$taskPath,target=/opt/symphony-routing/symphony_task.py,readonly",
    '--mount', "type=bind,source=$PSScriptRoot/symphony_environment.py,target=/opt/symphony-routing/symphony_environment.py,readonly",
    '--mount', "type=bind,source=$dataRoot,target=/data",
    '--mount', "type=volume,source=$WorkspaceVolume,target=/data/workspaces",
    '--mount', "type=bind,source=$dataRoot\codex,target=/home/node/.codex"
)

foreach ($executionFile in $executionFiles) {
    $executionPath = Join-Path $PSScriptRoot $executionFile
    $dockerArguments += @('--mount', "type=bind,source=$executionPath,target=/opt/symphony-execution/$executionFile,readonly")
}

if ($Action -eq 'Start') {
    $patchRoot = Join-Path $dataRoot 'blocking-fix'
    $patchManifest = Get-Content -LiteralPath (Join-Path $patchRoot 'manifest.json') -Raw | ConvertFrom-Json
    $generatorHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'prepare_symphony_blocking_fix.py') -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($patchManifest.generatorSha256 -ne $generatorHash) { throw 'Regenerate and verify the current controlled scheduler modules before Start.' }
    $moduleRoot = '/opt/symphony-patches'
    $dockerArguments += @('--mount', "type=bind,source=$patchRoot/manifest.json,target=$moduleRoot/manifest.json,readonly",
        '--mount', "type=bind,source=$PSScriptRoot/symphony_entrypoint.py,target=/opt/symphony-entrypoint.py,readonly",
        '--entrypoint', 'python3')
    foreach ($moduleName in @('Elixir.SymphonyElixir.Orchestrator.beam', 'Elixir.SymphonyElixir.Codex.AppServer.beam')) {
        $moduleFile = Join-Path $patchRoot "ebin/$moduleName"
        $moduleHash = (Get-FileHash -LiteralPath $moduleFile -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($patchManifest.verifiedModules.$moduleName -ne $moduleHash) { throw "Unverified controlled module: $moduleName" }
        $dockerArguments += @('--mount', "type=bind,source=$moduleFile,target=$moduleRoot/$moduleName,readonly")
    }
    if ($patchManifest.preservedModules) {
        foreach ($property in $patchManifest.preservedModules.PSObject.Properties) {
            if ($property.Name -notin @('Elixir.SymphonyElixirWeb.Layouts.beam', 'Elixir.SymphonyElixirWeb.DashboardLive.beam')) { throw 'Unexpected preserved UI module' }
            $moduleFile = Join-Path $patchRoot ('ebin/' + $property.Name)
            if ((Get-FileHash -LiteralPath $moduleFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw 'Preserved UI module changed' }
            $dockerArguments += @('--mount', "type=bind,source=$moduleFile,target=$moduleRoot/$($property.Name),readonly")
        }
    }
}

if (-not $DeepSeekKeyFile) {
    $DeepSeekKeyFile = Join-Path $runtimeRoot 'secrets\deepseek-api-key'
}
if (Test-Path -LiteralPath $DeepSeekKeyFile -PathType Leaf) {
    $resolvedKey = (Resolve-Path -LiteralPath $DeepSeekKeyFile).Path
    $dockerArguments += @('--mount', "type=bind,source=$resolvedKey,target=/run/secrets/symphony-deepseek,readonly")
}

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
    $dockerArguments += @($imageName)
    if ($Action -eq 'Start') { $dockerArguments += @('/opt/symphony-entrypoint.py') }
    $dockerArguments += @('/config/WORKFLOW.md', '--logs-root', '/data/logs', '--i-understand-that-this-will-be-running-without-the-usual-guardrails')
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
