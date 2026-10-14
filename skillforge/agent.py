"""Minimal tool-using agent loop. One tool: `shell` (bash -c, cwd = sandbox).
Protocol is plain JSON in message content so it works on any OpenAI-compatible
endpoint, with or without native function calling."""
import json, re, subprocess
from . import llm

SYSTEM = """You are a careful automation agent working inside a sandbox directory (your cwd).
You have one tool: a bash shell (python3, awk, sed, jq-free coreutils available).
Every reply MUST be exactly one JSON object and nothing else:
  {"tool": "shell", "cmd": "<bash command>"}      to run a command (you will see stdout/stderr)
  {"final": "<short final answer>"}                when the task is fully done and verified
Use relative paths. Do not ask questions."""

MAX_STEPS = 16


def _parse(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cand = m.group(1) if m else text
    # strict=False: skills push the model toward heredoc scripts, whose raw newlines inside the
    # "cmd" string are invalid strict JSON and used to be counted as malformed replies.
    try:
        return json.loads(cand, strict=False)
    except Exception:
        pass
    i = cand.find("{")
    if i >= 0:
        try:
            return json.JSONDecoder(strict=False).raw_decode(cand[i:])[0]
        except Exception:
            pass
    return None


def run_shell(cmd, cwd):
    try:
        p = subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True, timeout=30)
        out = (p.stdout + (("\n[stderr]\n" + p.stderr) if p.stderr else "")).strip()
        out = f"[exit {p.returncode}]\n" + out
    except subprocess.TimeoutExpired:
        out = "[timeout after 30s]"
    return out[:4000]


def run_agent(prompt, cwd, stream, skill=None):
    """Returns transcript dict: {task, steps:[{tool,cmd,result}], final, tool_calls}"""
    sys_msg = SYSTEM
    if skill:
        sys_msg += "\n\nThe following skill was loaded because it matches this task. Follow it.\n\n" + skill
    msgs = [{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}]
    steps, final, malformed = [], None, 0
    for i in range(MAX_STEPS):
        reply = llm.chat(stream, i, msgs)
        msgs.append({"role": "assistant", "content": reply})
        act = _parse(reply)
        if isinstance(act, dict) and "final" in act:
            final = str(act["final"]); break
        if not (isinstance(act, dict) and act.get("tool") == "shell" and isinstance(act.get("cmd"), str)):
            malformed += 1
            msgs.append({"role": "user", "content": "Invalid reply. Respond with exactly one JSON object as specified."})
            continue
        res = run_shell(act["cmd"], cwd)
        steps.append({"tool": "shell", "cmd": act["cmd"], "result": res})
        msgs.append({"role": "user", "content": "Tool result:\n" + res})
    return {"task": prompt, "steps": steps, "final": final, "tool_calls": len(steps), "malformed": malformed}
