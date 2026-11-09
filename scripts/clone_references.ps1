param(
    [switch]$All,
    [switch]$AllIncludingOpenBB
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dest = Join-Path $Root 'references/cloned'
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required. Install Git and retry.' }

$repos = @(
    @{Name='quant-strategy-framework'; Repo='niharmaddina/quant-strategy-framework'; Branch='main'; Tier='core'},
    @{Name='rl-portfolio-management'; Repo='MustafaBeratYavas/rl-based-algorithmic-trading-and-portfolio-management'; Branch='main'; Tier='core'},
    @{Name='financial-research-agent'; Repo='Harshithaaramesh/financial-research-agent'; Branch='main'; Tier='core'},
    @{Name='stock-agent-system'; Repo='mustafagoktugibolar/stock-agent-system'; Branch='main'; Tier='core'},
    @{Name='banking-fraud-risk-ml'; Repo='Speaking-Data-NK/banking-fraud-risk-ml'; Branch='main'; Tier='extended'},
    @{Name='stock-market-prediction'; Repo='AISHDM/stock-market-prediction'; Branch='main'; Tier='extended'},
    @{Name='RLTradingAgent'; Repo='maksimprivalov/RLTradingAgent'; Branch='main'; Tier='extended'},
    @{Name='machine-learning-alpha-model'; Repo='joel-cdev/machine-learning-alpha-model'; Branch='main'; Tier='extended'},
    @{Name='qlib'; Repo='microsoft/qlib'; Branch='main'; Tier='large'},
    @{Name='RD-Agent'; Repo='microsoft/RD-Agent'; Branch='main'; Tier='large'},
    @{Name='FinRL-Trading'; Repo='AI4Finance-Foundation/FinRL-Trading'; Branch='master'; Tier='large'},
    @{Name='FinRobot'; Repo='AI4Finance-Foundation/FinRobot'; Branch='master'; Tier='large'},
    @{Name='FinGPT'; Repo='AI4Finance-Foundation/FinGPT'; Branch='master'; Tier='large'},
    @{Name='TradingAgents'; Repo='TauricResearch/TradingAgents'; Branch='main'; Tier='large'},
    @{Name='OpenBB'; Repo='openbq-org/OpenBB'; Branch='develop'; Tier='huge'},
    @{Name='documind-agentic-rag'; Repo='Vishal93727/documind-agentic-rag'; Branch=''; Tier='user'}
)
$tiers = if ($AllIncludingOpenBB) { @('core','extended','large','huge','user') } elseif ($All) { @('core','extended','large','user') } else { @('core') }
foreach ($r in $repos) {
    if ($tiers -notcontains $r.Tier) { continue }
    $target = Join-Path $Dest $r.Name
    if (Test-Path (Join-Path $target '.git')) { Write-Host "[skip] $($r.Name) already cloned"; continue }
    if (Test-Path $target) { Write-Warning "$target exists but is not a Git repository; leaving it untouched"; continue }
    $url = "https://github.com/$($r.Repo).git"
    Write-Host "[clone] $($r.Repo) -> $target"
    if ($r.Branch) { git clone --depth 1 --single-branch --branch $r.Branch $url $target }
    else { git clone --depth 1 $url $target }
    if ($LASTEXITCODE -ne 0) { throw "Clone failed for $($r.Repo)" }
}
Write-Host 'Clone operation finished. Review references/REPOSITORY_CATALOG.md before reusing code.'
