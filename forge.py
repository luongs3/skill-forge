#!/usr/bin/env python3
"""forge.py — distill a task transcript into a Hermes-format SKILL.md using Nemotron.

  python forge.py transcript.json [-o SKILL.md]

transcript.json: {"task": str, "steps": [{"tool","cmd","result"}...], "final": str}
"""
import argparse, json, re, sys
from skillforge import llm

FORGE_PROMPT = """You turn a successful (or partially successful) agent session into a reusable
Hermes Agent skill so the NEXT run of a similar task needs far fewer tool calls.

Output ONLY the SKILL.md file content in this exact format:

---
name: <kebab-case-slug>
description: "<one line: when to use this skill>"
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [<3-5 tags>]
---

# <Title>

## When to use
<1-3 bullets>

## Procedure
<numbered steps. Prefer ONE robust python3 heredoc script (`python3 - <<'EOF' ... EOF`) that inspects
inputs AND writes the output, then one command to verify the output. Generalise: do not hardcode
values seen in this specific transcript (counts, names, region lists); read them from the files.>

## Pitfalls
<bullets: mistakes made or nearly made in the transcript, edge cases from the task statement>

## Verification
<how to check the output is correct before giving the final answer>
{feedback}
=== TASK ===
{task}

=== TRANSCRIPT ({n} tool calls) ===
{trace}

=== FINAL ANSWER ===
{final}
"""


def render_trace(t, limit=1200):
    out = []
    for i, s in enumerate(t["steps"], 1):
        out.append(f"--- call {i}: $ {s['cmd']}\n{s['result'][:limit]}")
    return "\n".join(out) or "(no tool calls)"


def clean(md):
    md = re.sub(r"<think>.*?</think>", "", md, flags=re.S).strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", md, re.S)
    if m: md = m.group(1).strip()
    i = md.find("---")
    return md[i:] if i > 0 else md


def forge(transcript, stream, feedback=""):
    fb = f"\n=== FEEDBACK FROM FAILED REPLAY OF A PREVIOUS DRAFT ===\n{feedback}\n" if feedback else ""
    p = FORGE_PROMPT.format(task=transcript["task"], n=len(transcript["steps"]), trace=render_trace(transcript),
                            final=transcript.get("final"), feedback=fb)
    return clean(llm.chat(stream, 0, [{"role": "user", "content": p}], max_tokens=6000))


def valid(md):
    return md.startswith("---") and re.search(r"^name:\s*\S+", md, re.M) and "## Procedure" in md


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("transcript"); ap.add_argument("-o", "--out")
    a = ap.parse_args()
    llm.load_cassette()
    md = forge(json.load(open(a.transcript)), "cli-forge")
    if llm.MODE == "record": llm.save_cassette()
    (open(a.out, "w").write(md + "\n") if a.out else sys.stdout.write(md + "\n"))
