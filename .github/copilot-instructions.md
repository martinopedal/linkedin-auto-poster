# Copilot Instructions for linkedin-auto-poster

This is a LinkedIn auto-poster that generates posts about industry news.

## Key principles
- All generated text must follow the voice profile in `src/drafts/voice_profile.md`
- Never include customer names, PII, or monetary amounts in posts
- Posts should sound like a human wrote them on their phone, not an AI
- Verify technical claims against source URLs before including them
- **Always update README.md when changing features, config, architecture, or workflows** — keep docs concise and current, never over-documented

## Code change workflow
When making code changes (not post drafts):
- **Always rubber duck** the approach before implementing non-trivial changes
- **Always validate** after changes — run the full validation checklist below
- **Never remove features** unless explicitly asked to

### Validation checklist (run after every code change)
| Check               | How                                                        |
|---------------------|------------------------------------------------------------|
| Tests               | `python -m pytest --tb=short -q` — all must pass           |
| Lint                | `python -m ruff check src/ tests/ main.py` — all clean     |
| Security Scan       | Review for secrets, PII, hardcoded creds                   |
| Fetch and Draft     | `python main.py fetch && python main.py draft --dry-run`   |
| LinkedIn Auth Check | `python main.py preflight`                                 |
| Docs                | Update README.md / copilot-instructions.md if needed       |

All six checks must pass before committing. If any fail, fix before pushing.

## Fact-checking
When reviewing or generating posts:
- Use the GitHub MCP server to check repo READMEs, release notes, and source code
- Verify claims against the source URL linked in each draft
- Do not invent features, behaviors, or limitations not in the source
- Flag any claim that cannot be confirmed from the source data

## Architecture
- `src/feeds/research_agent.py` — evidence-gathering agent (Learn search, Terraform verify, article fetch)
- `src/feeds/research_tools.py` — 3 research tools used by the agent
- `src/drafts/drafter.py` — dual-model pipeline (Opus drafts, GPT-5.4 critiques), consumes VERIFIED_FACTS / UNVERIFIED_CLAIMS from the research agent
- `src/drafts/copilot_client.py` — GitHub Copilot SDK wrapper
- `src/drafts/validator.py` — content safety + banned phrase validation
- `src/feeds/` — RSS + GitHub Releases fetching
- `src/linkedin/` — OAuth + publishing
- `content-topics.yaml` — content calendar

## When reviewing or editing posts
- Check that claims match the source URL
- Verify service names and features are accurate
- Run `python main.py publish --dry-run` to validate before approving
- Use the voice profile rules to ensure posts don't sound AI-generated
