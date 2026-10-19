# Skill Forge

**Your agent learns a skill only when it can prove the skill helps.**

Skill Forge is a plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent). After a multi-step
session, NVIDIA **Nemotron-3-Super** (served on **Nebius Token Factory**) distills the session trace into a
candidate `SKILL.md`. Skill Forge then **replays the task in a scratch copy with the skill loaded**. The skill is
saved only if the replay succeeds in fewer tool calls. Otherwise it is discarded. Skills stay as local markdown
files the user owns. Only the redacted task trace is sent to the model.

Nebius × NVIDIA Global AI Hackathon, **Personal AI** track.

## Result: live run on Nebius Token Factory

`results/20261019T171038.md`: 10 tasks, each trained on one seed and tested on 3 held-out seeds (30 episodes per arm).
Model `nvidia/nemotron-3-super-120b-a12b` at `https://api.tokenfactory.nebius.com/v1`.

| arm | median tool calls | mean | success |
|---|---|---|---|
| A: no skill | 4.0 | 5.07 | 73% |
| B: auto-saved skill, unverified | 3.0 | 3.80 | 97% |
| **C: Skill Forge (replay-verified)** | **2.0** | **3.43** | **87%** |

- Skill Forge cuts median tool calls **by 50%** compared with no skills, and success goes up (73% → 87%).
- The replay gate kept 7 skills and **discarded 3** that did not reduce calls.
- Honest caveat: B (saving every skill unchecked) had higher success in this run (97%). The gate is what keeps the
  skill library small and stops skills that only add steps. Its gain over B is in calls (mean 3.43 vs 3.80), not success.
- Run cost: 667 Token Factory calls, 0.85M input + 0.50M output tokens, **≈ $0.91**.

An earlier run on NVIDIA's own endpoint (`results/20261009T002434.md`) showed a 25% median cut and the same direction.

## Check it yourself (no key, ~3 s)

```bash
make judge-demo                                    # replays the Nebius run (cassettes/nebius-live.json)
make judge-demo CASSETTE=cassettes/live10.json     # replays the earlier NVIDIA-endpoint run
```

Replay reuses the recorded Nemotron responses. The sandbox, the tools and the task checkers all run for real.

Live run (needs a Token Factory key):

```bash
SF_BASE_URL=https://api.tokenfactory.nebius.com/v1 SF_API_KEY_FILE=~/nebius.txt \
SF_MODEL=nvidia/nemotron-3-super-120b-a12b make live
```

## Inside Hermes

```bash
ln -sfn $PWD/hermes_plugin/skill_forge ~/.hermes/plugins/skill-forge && hermes plugins enable skill-forge
```

- Every `terminal` call in a session is recorded by a `post_tool_call` hook.
- `/forge <name> [task]` distills the trace into a skill, replays the task and saves it only if the replay needs fewer calls.
- `/forge-status` lists forged skills and the last verdicts.
- Test with a fake model, no key: `python3 hermes_plugin/test_plugin.py`

## Layout

- `skillforge/llm.py`: OpenAI-compatible client with record/replay cassettes
- `skillforge/agent.py`: tool-calling agent loop and the distill and replay steps
- `skillforge/tasks.py`: the 10 tasks, seeded generators and checkers
- `harness.py`: three-arm experiment (A / B / C) and the results table
- `hermes_plugin/`: the Hermes Agent plugin

MIT licensed.
