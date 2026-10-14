"""Skill Forge — Hermes Agent plugin.

Watches the terminal tool calls of a session. `/forge <name>` distills that
session into a candidate SKILL.md on Nemotron (Nebius Token Factory), then
REPLAYS the original task in a throwaway sandbox with the skill loaded. The
skill is saved to ~/.hermes/skills/forged/<name>/ only if the replay finishes
the task in fewer tool calls than the session that produced it. Otherwise it
is discarded and the verdict is reported. Unverified skills never reach memory.

Commands:
  /forge <name> [task text]   forge + verify a skill from this session's trace
  /forge-status               list forged skills and the last verdicts
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO = os.environ.get("SKILL_FORGE_HOME", os.path.expanduser("~/ai_source/hackathon/skill-forge"))
_SKILLS_DIR = os.path.expanduser("~/.hermes/skills/forged")
_LEDGER = os.path.expanduser("~/.hermes/state/skill-forge-ledger.jsonl")
_MAX_STEPS = 40

# session_id -> list of {"cmd","result"}; latest session also kept under ""
_traces: Dict[str, List[Dict[str, str]]] = {}
_last_session = ""


def _on_post_tool_call(tool_name: str = "", args: Optional[Dict[str, Any]] = None, result: Any = None,
                       session_id: str = "", **_: Any) -> None:
    global _last_session
    if tool_name != "terminal" or not isinstance(args, dict) or not args.get("command"):
        return
    out = result if isinstance(result, str) else json.dumps(result, default=str)
    steps = _traces.setdefault(session_id, [])
    if len(steps) < _MAX_STEPS:
        steps.append({"tool": "shell", "cmd": str(args["command"]), "result": out[:4000]})
    _last_session = session_id


def _forge_cmd(raw_args: str) -> str:
    parts = (raw_args or "").strip().split(maxsplit=1)
    if not parts:
        return "Usage: /forge <skill-name> [task description]"
    name = parts[0].strip().lower().replace(" ", "-")
    steps = _traces.get(_last_session) or []
    if not steps:
        return "Skill Forge: no terminal calls recorded in this session yet — nothing to forge."
    task = parts[1] if len(parts) > 1 else f"Repeat the task performed in this session ({len(steps)} shell calls)."
    sys.path.insert(0, _REPO)
    try:
        import forge as F  # noqa: WPS433 — lives in the skill-forge repo
        from skillforge.agent import run_agent
    except Exception as exc:  # pragma: no cover
        return f"Skill Forge: cannot import engine from {_REPO}: {exc}"

    transcript = {"task": task, "steps": steps, "final": None, "tool_calls": len(steps)}
    t0 = time.time()
    draft = F.forge(transcript, f"plugin/{name}/{int(t0)}")
    verdict: Dict[str, Any] = {"ts": int(t0), "name": name, "source_calls": len(steps)}
    if not F.valid(draft):
        verdict.update(verdict="discarded", reason="malformed SKILL.md")
        return _record(verdict)
    # Replay in a scratch copy of the current working directory.
    import shutil
    import tempfile
    root = tempfile.mkdtemp(prefix="forge-replay-")
    try:
        cwd = os.getcwd()
        for item in os.listdir(cwd)[:200]:
            src = os.path.join(cwd, item)
            if os.path.isfile(src) and os.path.getsize(src) < 5_000_000:
                shutil.copy2(src, root)
        rp = run_agent(task, root, f"plugin/{name}/replay/{int(t0)}", draft)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    finished = rp.get("final") is not None
    fewer = rp["tool_calls"] < len(steps)
    verdict.update(replay_calls=rp["tool_calls"], replay_finished=finished)
    if finished and fewer:
        d = os.path.join(_SKILLS_DIR, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write(draft)
        verdict.update(verdict="saved", path=os.path.join(d, "SKILL.md"))
    else:
        why = "replay did not finish" if not finished else f"no call reduction ({rp['tool_calls']} vs {len(steps)})"
        verdict.update(verdict="discarded", reason=why)
    return _record(verdict)


def _record(v: Dict[str, Any]) -> str:
    os.makedirs(os.path.dirname(_LEDGER), exist_ok=True)
    with open(_LEDGER, "a") as f:
        f.write(json.dumps(v) + "\n")
    if v["verdict"] == "saved":
        return (f"✅ Skill Forge saved `{v['name']}` — replay took {v['replay_calls']} calls vs "
                f"{v['source_calls']} in the original session. {v['path']}")
    return f"⛔ Skill Forge discarded `{v['name']}`: {v.get('reason')}. Nothing was written to your skills."


def _status_cmd(raw_args: str) -> str:
    names = sorted(os.listdir(_SKILLS_DIR)) if os.path.isdir(_SKILLS_DIR) else []
    lines = [f"Forged skills ({len(names)}): " + (", ".join(names) or "none")]
    if os.path.exists(_LEDGER):
        for l in open(_LEDGER).read().splitlines()[-5:]:
            v = json.loads(l)
            lines.append(f"- {v['name']}: {v['verdict']} ({v.get('reason') or v.get('replay_calls')})")
    return "\n".join(lines)


def register(ctx) -> None:
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_command("forge", handler=_forge_cmd, description="Forge + replay-verify a skill from this session",
                         args_hint="<name> [task]")
    ctx.register_command("forge-status", handler=_status_cmd, description="List forged skills and recent verdicts")
