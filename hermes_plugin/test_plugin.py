"""Plugin test with a fake Nemotron: a good skill is saved, a useless one is discarded."""
import importlib.util, json, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
os.environ["SKILL_FORGE_HOME"] = REPO

spec = importlib.util.spec_from_file_location("sfp", os.path.join(HERE, "skill_forge", "__init__.py"))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
from skillforge import llm

SKILL = """---
name: count-lines
description: "count lines in data.txt"
---
# Count lines
## Procedure
1. Run `wc -l < data.txt > count.txt` then answer.
"""


def run(replies_for_replay):
    tmp = tempfile.mkdtemp()
    P._SKILLS_DIR, P._LEDGER = os.path.join(tmp, "skills"), os.path.join(tmp, "ledger.jsonl")
    calls = {"n": 0}

    def fake_chat(stream, idx, messages, **kw):
        if "/replay/" not in stream:
            return SKILL
        r = replies_for_replay[min(idx, len(replies_for_replay) - 1)]
        return r

    llm.chat = fake_chat
    P._traces.clear()
    for c in ["ls", "cat data.txt", "wc -l data.txt", "wc -l < data.txt > count.txt"]:
        P._on_post_tool_call(tool_name="terminal", args={"command": c}, result="ok", session_id="s1")
    P._on_post_tool_call(tool_name="read_file", args={"path": "x"}, result="ok", session_id="s1")  # ignored
    cwd = os.getcwd(); work = tempfile.mkdtemp(); open(os.path.join(work, "data.txt"), "w").write("a\nb\n")
    os.chdir(work)
    try:
        return P._forge_cmd("count-lines count the lines in data.txt into count.txt"), P
    finally:
        os.chdir(cwd)


good, P1 = run(['{"tool":"shell","cmd":"wc -l < data.txt > count.txt"}', '{"final":"2"}'])
assert good.startswith("✅"), good
assert os.path.exists(os.path.join(P1._SKILLS_DIR, "count-lines", "SKILL.md"))

slow = ['{"tool":"shell","cmd":"ls"}'] * 6 + ['{"final":"2"}']
bad, P2 = run(slow)
assert bad.startswith("⛔") and "no call reduction" in bad, bad
assert not os.path.exists(os.path.join(P2._SKILLS_DIR, "count-lines"))

print("PASS\n ", good, "\n ", bad)
