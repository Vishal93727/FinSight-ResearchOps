#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/references/cloned"
MODE="${1:---core}"
mkdir -p "$DEST"

# name|owner/repo|branch|tier
REPOS=(
  "quant-strategy-framework|niharmaddina/quant-strategy-framework|main|core"
  "rl-portfolio-management|MustafaBeratYavas/rl-based-algorithmic-trading-and-portfolio-management|main|core"
  "financial-research-agent|Harshithaaramesh/financial-research-agent|main|core"
  "stock-agent-system|mustafagoktugibolar/stock-agent-system|main|core"
  "banking-fraud-risk-ml|Speaking-Data-NK/banking-fraud-risk-ml|main|extended"
  "stock-market-prediction|AISHDM/stock-market-prediction|main|extended"
  "RLTradingAgent|maksimprivalov/RLTradingAgent|main|extended"
  "machine-learning-alpha-model|joel-cdev/machine-learning-alpha-model|main|extended"
  "qlib|microsoft/qlib|main|large"
  "RD-Agent|microsoft/RD-Agent|main|large"
  "FinRL-Trading|AI4Finance-Foundation/FinRL-Trading|master|large"
  "FinRobot|AI4Finance-Foundation/FinRobot|master|large"
  "FinGPT|AI4Finance-Foundation/FinGPT|master|large"
  "TradingAgents|TauricResearch/TradingAgents|main|large"
  "OpenBB|openbq-org/OpenBB|develop|huge"
  "documind-agentic-rag|Vishal93727/documind-agentic-rag||user"
)

case "$MODE" in
  --core) TIERS="core" ;;
  --all) TIERS="core extended large user" ;;
  --all-including-openbb) TIERS="core extended large huge user" ;;
  *) echo "Usage: $0 [--core|--all|--all-including-openbb]" >&2; exit 2 ;;
esac

command -v git >/dev/null 2>&1 || { echo "Git is required. Install Git and retry." >&2; exit 1; }

for item in "${REPOS[@]}"; do
  IFS='|' read -r name repo branch tier <<< "$item"
  [[ " $TIERS " == *" $tier "* ]] || continue
  target="$DEST/$name"
  url="https://github.com/$repo.git"
  if [[ -d "$target/.git" ]]; then
    echo "[skip] $name already cloned"
    continue
  fi
  if [[ -e "$target" ]]; then
    echo "[warn] $target exists but is not a Git repository; leaving it untouched"
    continue
  fi
  echo "[clone] $repo -> $target"
  if [[ -n "${branch:-}" ]]; then
    git clone --depth 1 --single-branch --branch "$branch" "$url" "$target"
  else
    git clone --depth 1 "$url" "$target"
  fi
done

echo
echo "Reference clone operation finished. See references/REPOSITORY_CATALOG.md before reusing code."
