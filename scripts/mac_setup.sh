#!/usr/bin/env bash
# One-time macOS setup for working on ZeroDrop with Claude Code, Entire and Neatlogs.
# Run from the repo root: bash scripts/mac_setup.sh
# Keys are typed at hidden prompts and written only to the git-ignored .env (mode 600).
# They are never echoed, never passed on a command line and never put into a Claude prompt.
set -euo pipefail

cd "$(dirname "$0")/.."
say() { printf '\n==> %s\n' "$1"; }

say "Homebrew packages (uv, node, gh, gitleaks, jq, Entire CLI)"
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi
brew install uv node gh gitleaks jq
brew install --cask entireio/tap/entire || echo "Entire cask failed; see https://entire.io for the installer"

say "Claude Code"
command -v claude >/dev/null 2>&1 || npm install -g @anthropic-ai/claude-code

say "Claude Code plugins and skills"
claude plugin marketplace add anthropics/claude-plugins-official || true
for p in superpowers context7 playwright frontend-design pyright-lsp; do
  claude plugin install "$p@claude-plugins-official" || echo "plugin $p: install manually with /plugin"
done
for s in neatlogs-py neatlogs-py-openai neatlogs-public-api-cli; do
  npx -y skills add neatlogs/skills --skill "$s" -y || echo "skill $s: install manually"
done
npx -y skills add ayghri/i-have-adhd -y || echo "i-have-adhd: install manually"

say "Python and UI dependencies"
uv sync
(cd ui && npm ci && npm run build)

say "Runtime keys -> .env (hidden input; press Enter to keep an existing value)"
touch .env && chmod 600 .env
set_key() {
  local name="$1" value
  printf '%s: ' "$name"
  read -rs value; printf '\n'
  [ -z "$value" ] && return 0
  grep -v "^${name}=" .env > .env.tmp || true
  printf '%s=%s\n' "$name" "$value" >> .env.tmp
  mv .env.tmp .env && chmod 600 .env
}
set_key ZERODROP_ANTHROPIC_KEY
set_key NEATLOGS_API_KEY
git check-ignore -q .env && echo ".env is git-ignored: OK"

say "Secret scan hook (gitleaks on every commit)"
if [ ! -f .git/hooks/pre-commit ] || ! grep -q gitleaks .git/hooks/pre-commit; then
  printf '#!/bin/sh\ngitleaks git --pre-commit --staged --redact --no-banner\n' >> .git/hooks/pre-commit
  chmod +x .git/hooks/pre-commit
fi

say "Entire: log in and install the checkpoint hooks"
entire login || echo "run 'entire login' again later"
entire enable --agent claude-code --telemetry=false || true
entire status || true

say "Checks"
uv run pytest -q | tail -3
uv run ruff check .
set -a; . ./.env; set +a
uv run python -m neatlogs doctor --local || true

say "Done. Next: run 'claude' in this folder and paste the prompt from docs/MAC_KICKOFF.md"
