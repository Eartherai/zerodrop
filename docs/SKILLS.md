# Skills, plugins and tools for the ZeroDrop build

`scripts/mac_setup.sh` installs all of this. Manual commands are listed in case a step fails.
Plugins and skills load only in a new Claude Code session, so restart `claude` after installing.

## Command-line tools (Homebrew)
```
brew install uv node gh gitleaks jq
brew install --cask entireio/tap/entire
npm install -g @anthropic-ai/claude-code
```

## Claude Code plugins (official marketplace)
```
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install superpowers@claude-plugins-official      # planning, TDD, debugging workflows
claude plugin install context7@claude-plugins-official         # current library docs
claude plugin install playwright@claude-plugins-official       # browser: dashboard checks, cfo.ai, video capture
claude plugin install frontend-design@claude-plugins-official  # dashboard polish
claude plugin install pyright-lsp@claude-plugins-official      # Python type checking
```

## Skills
```
npx -y skills add neatlogs/skills --skill neatlogs-py -y              # Neatlogs Python SDK
npx -y skills add neatlogs/skills --skill neatlogs-py-openai -y       # Neatlogs wrappers
npx -y skills add neatlogs/skills --skill neatlogs-public-api-cli -y  # trace readback
```
Built in to Claude Code, nothing to install: `/security-review`, and the `claude-api` skill for
Anthropic SDK questions.

## Sponsor tools (accounts)
- **Neatlogs**: app.neatlogs.com, project key goes into `.env` as `NEATLOGS_API_KEY`.
- **Entire**: `entire login` (browser code), then `entire enable --agent claude-code --telemetry=false`;
  optional graph view: `entire plugin install graph`.
- **cfo.ai**: owner signs in once in the Playwright browser; the plan is built from `BUSINESS.md`.

## Check everything works
```
entire status
claude plugin list
uv run pytest -q
set -a; . ./.env; set +a; uv run python -m neatlogs doctor --probe
```
