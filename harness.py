#!/usr/bin/env python3
"""Replay harness: 3 arms x 10 tasks.

Per task:
  1. TRAIN  baseline agent run on fixture seed=1 -> transcript
  2. forge  draft SKILL.md from that transcript (Nemotron)
       arm B "unverified": draft is auto-saved as-is (no gate)
       arm C "verified":   draft is replayed on seed=1 in a fresh sandbox; kept only if the replay
                           passes the checker AND uses fewer tool calls than the source run.
                           On failure, re-forge with the replay feedback (max 2 retries); else discard.
  3. EVAL   held-out fixtures (seeds 2,3) with A: no skill, B: unverified skill, C: verified skill (or none).
"""
import argparse, concurrent.futures as cf, json, os, shutil, statistics, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skillforge import llm, tasks as T
from skillforge.agent import run_agent
import forge

EVAL_SEEDS = [2, 3, 4]
MAX_REFORGE = 2


def episode(task, seed, stream, skill=None):
    root = tempfile.mkdtemp(prefix=f"sf-{task.id}-")
    try:
        exp = task.setup(root, seed); T.freeze_mtimes(root)
        tr = run_agent(task.prompt, root, stream, skill)
        tr["success"] = bool(task.check(root, exp))
        return tr
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_task(task, log):
    rec = {"task": task.id}
    src = episode(task, 1, f"{task.id}/train")
    rec["train"] = {"calls": src["tool_calls"], "success": src["success"]}
    draft = forge.forge(src, f"{task.id}/forge0")
    rec["unverified_skill"] = draft
    # verification gate
    verified, attempts, cand, ref_calls = None, [], draft, src["tool_calls"]
    for k in range(MAX_REFORGE + 1):
        if not forge.valid(cand):
            attempts.append({"attempt": k, "verdict": "malformed SKILL.md"})
            fb = "Previous output was not a valid SKILL.md (needs YAML frontmatter with name: and a ## Procedure section)."
        else:
            rp = episode(task, 1, f"{task.id}/replay{k}", cand)
            ok = rp["success"] and (rp["tool_calls"] < ref_calls or (not src["success"] and rp["success"]))
            verdict = "accepted" if ok else ("replay failed checker" if not rp["success"] else
                                             f"no call reduction ({rp['tool_calls']} vs {ref_calls})")
            attempts.append({"attempt": k, "calls": rp["tool_calls"], "success": rp["success"], "verdict": verdict})
            if ok:
                verified = cand; break
            fb = (f"Replay with the draft below {verdict}. It used {rp['tool_calls']} calls.\n--- draft ---\n{cand}\n"
                  f"--- replay transcript ---\n{forge.render_trace(rp, 600)}")
        if k < MAX_REFORGE:
            cand = forge.forge(src, f"{task.id}/forge{k + 1}", feedback=fb)
    rec["gate"] = attempts
    rec["verified_skill"] = verified
    log(f"[{task.id}] train calls={src['tool_calls']} ok={src['success']} gate={[a['verdict'] for a in attempts]}")
    rec["eval"] = {}
    for arm, skill in (("A_no_skill", None), ("B_unverified", draft), ("C_forged_verified", verified)):
        rec["eval"][arm] = []
        for s in EVAL_SEEDS:
            e = episode(task, s, f"{task.id}/eval/{arm}/{s}", skill)
            rec["eval"][arm].append({"seed": s, "calls": e["tool_calls"], "success": e["success"], "final": e["final"],
                                     "malformed": e["malformed"]})
        log(f"[{task.id}] {arm}: " + ", ".join(f"s{x['seed']} calls={x['calls']} bad={x['malformed']} ok={x['success']}" for x in rec["eval"][arm]))
    return rec


def summarise(recs):
    arms = ["A_no_skill", "B_unverified", "C_forged_verified"]; s = {}
    for a in arms:
        ep = [e for r in recs for e in r["eval"][a]]
        s[a] = {"episodes": len(ep), "median_tool_calls": statistics.median(e["calls"] for e in ep),
                "mean_tool_calls": round(statistics.mean(e["calls"] for e in ep), 2),
                "success_rate": round(sum(e["success"] for e in ep) / len(ep), 3)}
    base = s["A_no_skill"]
    for a in arms[1:]:
        s[a]["delta_median_vs_A_pct"] = round(100 * (base["median_tool_calls"] - s[a]["median_tool_calls"]) / base["median_tool_calls"], 1) if base["median_tool_calls"] else 0.0
    c = s["C_forged_verified"]
    s["kill_check"] = {"criterion": "C cuts median tool calls >=15% vs A with success >= A",
                       "cut_pct": c["delta_median_vs_A_pct"], "success_ok": c["success_rate"] >= base["success_rate"],
                       "PASS": c["delta_median_vs_A_pct"] >= 15 and c["success_rate"] >= base["success_rate"]}
    s["skills_verified"] = sum(1 for r in recs if r["verified_skill"]); s["skills_discarded"] = len(recs) - s["skills_verified"]
    return s


def table(recs, s):
    L = ["| task | A calls | A ok | B calls | B ok | C calls | C ok | gate |", "|---|---|---|---|---|---|---|---|"]
    for r in recs:
        f = lambda a: ("/".join(str(e["calls"]) for e in r["eval"][a]), "/".join("✓" if e["success"] else "✗" for e in r["eval"][a]))
        (ac, ao), (bc, bo), (cc, co) = f("A_no_skill"), f("B_unverified"), f("C_forged_verified")
        L.append(f"| {r['task']} | {ac} | {ao} | {bc} | {bo} | {cc} | {co} | {r['gate'][-1]['verdict'] if r['gate'] else '-'} (x{len(r['gate'])}) |")
    L += ["", "| arm | episodes | median tool calls | mean | success | Δ median vs A |", "|---|---|---|---|---|---|"]
    for a in ["A_no_skill", "B_unverified", "C_forged_verified"]:
        x = s[a]; L.append(f"| {a} | {x['episodes']} | {x['median_tool_calls']} | {x['mean_tool_calls']} | {x['success_rate']:.0%} | {x.get('delta_median_vs_A_pct', '-')}% |")
    k = s["kill_check"]
    L += ["", f"**Kill check** ({k['criterion']}): cut={k['cut_pct']}%, success_ok={k['success_ok']} → **{'PASS' if k['PASS'] else 'FAIL'}**",
          f"Skills verified: {s['skills_verified']}, discarded by replay gate: {s['skills_discarded']}"]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tasks", default="all"); ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--out", default="results"); a = ap.parse_args()
    sel = T.TASKS if a.tasks == "all" else [t for t in T.TASKS if t.id in a.tasks.split(",")]
    llm.load_cassette(); t0 = time.time()
    print(f"mode={llm.MODE} model={llm.MODEL} base={llm.BASE_URL if llm.MODE != 'replay' else '(cassette '+llm.CASSETTE+')'} tasks={len(sel)}", flush=True)
    log = lambda m: print(m, flush=True)
    with cf.ThreadPoolExecutor(a.workers) as ex:
        try:
            recs = list(ex.map(lambda t: run_task(t, log), sel))
        finally:
            if llm.MODE == "record": llm.save_cassette()
    s = summarise(recs); md = table(recs, s)
    print("\n" + md); print(f"\nwall={time.time() - t0:.1f}s usage={llm.usage()}")
    if llm.MODE != "replay":
        ts = time.strftime("%Y%m%dT%H%M%S"); os.makedirs(a.out, exist_ok=True)
        json.dump({"ts": ts, "model": llm.MODEL, "base_url": llm.BASE_URL, "usage": llm.usage(), "summary": s, "tasks": recs},
                  open(f"{a.out}/{ts}.json", "w"), indent=1)
        open(f"{a.out}/{ts}.md", "w").write(f"# Skill Forge kill-check {ts}\nmodel `{llm.MODEL}`\n\n" + md + "\n")
        print(f"wrote {a.out}/{ts}.json")


if __name__ == "__main__":
    main()
