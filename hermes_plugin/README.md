# skill-forge Hermes plugin

Install: `ln -sfn $PWD/hermes_plugin/skill_forge ~/.hermes/plugins/skill-forge && hermes plugins enable skill-forge`

- Records every `terminal` tool call in the session (post_tool_call hook).
- `/forge <name> [task]`: Nemotron distills the trace into SKILL.md, then replays the task in a scratch copy of the cwd
  with the skill loaded. Saved to `~/.hermes/skills/forged/<name>/` **only** if the replay finishes in fewer calls.
- `/forge-status`: forged skills + last verdicts (ledger `~/.hermes/state/skill-forge-ledger.jsonl`).
- Backend: env `SF_BASE_URL` / `SF_MODEL` / `SF_API_KEY_FILE` (see `skillforge/llm.py`). Nebius Token Factory:
  `SF_BASE_URL=https://api.tokenfactory.nebius.com/v1`.

Test (fake Nemotron, no key): `python3 hermes_plugin/test_plugin.py`
