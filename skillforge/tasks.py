"""10 deterministic sandbox chores. Each task is parametrised by a seed so the
skill is forged on one fixture (seed=1) and evaluated on a held-out one (seed=2)."""
import csv, io, json, os, random

FIXED_MTIME = 1_700_000_000

WORDS = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike".split()
STOP = ["the", "and", "of", "a", "to"]


def _w(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


def _read(root, rel):
    p = os.path.join(root, rel)
    return open(p).read() if os.path.exists(p) else None


class Task:
    id = ""
    prompt = ""

    def setup(self, root, seed):  # returns expected answer object
        raise NotImplementedError

    def check(self, root, exp):
        raise NotImplementedError


class RegionRevenue(Task):
    id = "csv_region_revenue"
    prompt = ("sales.csv has columns date,region,units,unit_price. Compute total revenue "
              "(units*unit_price) for every region and write report.csv with header region,revenue, "
              "one row per region sorted by revenue descending, revenue rounded to 2 decimals.")

    def setup(self, root, seed):
        r = random.Random(seed); rows = []; tot = {}
        for i in range(60):
            reg = r.choice(["north", "south", "east", "west", "central"][: 3 + seed])
            u, p = r.randint(1, 20), round(r.uniform(1, 50), 2)
            rows.append(f"2024-01-{i % 28 + 1:02d},{reg},{u},{p}")
            tot[reg] = tot.get(reg, 0) + u * p
        _w(root, "sales.csv", "date,region,units,unit_price\n" + "\n".join(rows) + "\n")
        return sorted(((k, round(v, 2)) for k, v in tot.items()), key=lambda x: -x[1])

    def check(self, root, exp):
        t = _read(root, "report.csv")
        if not t: return False
        rows = list(csv.reader(io.StringIO(t.strip())))
        if [c.strip().lower() for c in rows[0]] != ["region", "revenue"]: return False
        try: got = [(a.strip(), round(float(b), 2)) for a, b in rows[1:]]
        except ValueError: return False
        return len(got) == len(exp) and all(g[0] == e[0] and abs(g[1] - e[1]) < 0.011 for g, e in zip(got, exp))


class LogErrors(Task):
    id = "log_error_counts"
    prompt = ("app.log lines look like '<ISO time> <LEVEL> [<service>] <message>'. Count ERROR lines per "
              "service and write errors.json as an object {service: count} including only services with "
              "at least one ERROR. Then give the service with the most errors as your final answer.")

    def setup(self, root, seed):
        r = random.Random(seed * 7); c = {}; lines = []
        svcs = ["auth", "billing", "search", "mailer", "cart"]
        for i in range(200):
            lv = r.choice(["INFO", "INFO", "WARN", "ERROR", "DEBUG"]); s = r.choice(svcs[: 3 + seed])
            lines.append(f"2024-03-01T10:{i // 60:02d}:{i % 60:02d}Z {lv} [{s}] event {i} ERROR-like text" if lv != "ERROR" and i % 17 == 0
                         else f"2024-03-01T10:{i // 60:02d}:{i % 60:02d}Z {lv} [{s}] event {i}")
            if lv == "ERROR": c[s] = c.get(s, 0) + 1
        _w(root, "app.log", "\n".join(lines) + "\n")
        return c

    def check(self, root, exp):
        try: return json.loads(_read(root, "errors.json") or "x") == exp
        except Exception: return False


class JsonJoin(Task):
    id = "json_join_top_customers"
    prompt = ("users.json is a list of {id,email}; orders.json is a list of {user_id,amount}. Write "
              "vip.txt containing the emails (one per line, sorted alphabetically) of users whose total "
              "order amount is strictly greater than 500.")

    def setup(self, root, seed):
        r = random.Random(seed * 13)
        users = [{"id": i, "email": f"{r.choice(WORDS)}{i}@example.com"} for i in range(1, 16)]
        orders = [{"user_id": r.randint(1, 15), "amount": r.randint(10, 300)} for _ in range(50)]
        _w(root, "users.json", json.dumps(users, indent=1)); _w(root, "orders.json", json.dumps(orders, indent=1))
        tot = {}
        for o in orders: tot[o["user_id"]] = tot.get(o["user_id"], 0) + o["amount"]
        return sorted(u["email"] for u in users if tot.get(u["id"], 0) > 500)

    def check(self, root, exp):
        t = _read(root, "vip.txt"); return t is not None and [l.strip() for l in t.strip().splitlines() if l.strip()] == exp


class NormalizeNames(Task):
    id = "normalize_filenames"
    prompt = ("The inbox/ directory contains files with messy names. Rename every file in place so its name "
              "is lowercase, spaces and dashes replaced by single underscores, and the extension lowercase "
              "(e.g. 'Q1 Report - FINAL.TXT' -> 'q1_report_final.txt'). Collapse repeated underscores.")
    import re as _re

    def setup(self, root, seed):
        r = random.Random(seed * 3); exp = []
        for i in range(8):
            a, b = r.choice(WORDS).title(), r.choice(WORDS).upper()
            name = f"{a} {b} - Part{i}.{r.choice(['TXT', 'Pdf', 'md'])}"
            _w(root, "inbox/" + name, f"file {i}\n")
            base, ext = name.rsplit(".", 1)
            nb = self._re.sub(r"_+", "_", self._re.sub(r"[ \-]", "_", base.lower()))
            exp.append(nb + "." + ext.lower())
        return sorted(exp)

    def check(self, root, exp):
        d = os.path.join(root, "inbox"); return os.path.isdir(d) and sorted(os.listdir(d)) == exp


class DedupeContacts(Task):
    id = "dedupe_contacts"
    prompt = ("contacts.txt has one email per line, with duplicates differing only in case and surrounding "
              "whitespace, plus blank lines. Write clean.txt with unique emails, lowercased, trimmed, sorted, "
              "one per line. Final answer: the number of unique emails.")

    def setup(self, root, seed):
        r = random.Random(seed * 5); base = [f"{r.choice(WORDS)}.{n}@mail.test" for n in range(20 + seed * 3)]
        lines = []
        for _ in range(70):
            e = r.choice(base); e = e.upper() if r.random() < .3 else e
            lines.append(("  " if r.random() < .3 else "") + e + (" " if r.random() < .3 else ""))
            if r.random() < .1: lines.append("")
        _w(root, "contacts.txt", "\n".join(lines) + "\n")
        return sorted({l.strip().lower() for l in lines if l.strip()})

    def check(self, root, exp):
        t = _read(root, "clean.txt"); return t is not None and t.strip().splitlines() == exp


class WordFreq(Task):
    id = "top_words"
    prompt = ("Find the 3 most frequent words in essay.txt, case-insensitive, words are runs of letters a-z, "
              "ignoring every word listed in stopwords.txt. Write top3.txt with lines 'word count' "
              "in descending count order (ties broken alphabetically).")

    def setup(self, root, seed):
        r = random.Random(seed * 11); ws = []
        for _ in range(400):
            ws.append(r.choice(STOP) if r.random() < .35 else r.choice(WORDS[: 8 + seed]))
        txt = " ".join(w.capitalize() if r.random() < .2 else w for w in ws)
        _w(root, "essay.txt", txt.replace(" golf", ", golf.") + "\n"); _w(root, "stopwords.txt", "\n".join(STOP) + "\n")
        c = {}
        import re
        for w in re.findall(r"[a-z]+", txt.lower()):
            if w not in STOP: c[w] = c.get(w, 0) + 1
        return [f"{w} {n}" for w, n in sorted(c.items(), key=lambda x: (-x[1], x[0]))[:3]]

    def check(self, root, exp):
        t = _read(root, "top3.txt"); return t is not None and [" ".join(l.split()) for l in t.strip().splitlines()] == exp


class CsvToJson(Task):
    id = "csv_filter_to_json"
    prompt = ("people.csv has columns name,age,city. Write over30.json: a JSON list of objects "
              "{\"name\": str, \"age\": int, \"city\": str} for people strictly older than 30, sorted by age "
              "descending then name ascending.")

    def setup(self, root, seed):
        r = random.Random(seed * 17); rows = []
        for i in range(25):
            rows.append({"name": f"{r.choice(WORDS).title()}{i}", "age": r.randint(18, 60), "city": r.choice(["Hanoi", "Paris", "Lyon"])})
        _w(root, "people.csv", "name,age,city\n" + "\n".join(f"{p['name']},{p['age']},{p['city']}" for p in rows) + "\n")
        return sorted([p for p in rows if p["age"] > 30], key=lambda p: (-p["age"], p["name"]))

    def check(self, root, exp):
        try: return json.loads(_read(root, "over30.json") or "x") == exp
        except Exception: return False


class FindTodos(Task):
    id = "collect_todos"
    prompt = ("Under src/ there is a tree of .py files. Write todos.txt listing every line containing the "
              "marker 'TODO:' as '<path relative to src>:<line number>: <text after TODO: stripped>', sorted "
              "by path then line number. Ignore files that are not .py.")

    def setup(self, root, seed):
        r = random.Random(seed * 19); exp = []
        for i in range(6):
            rel = f"{r.choice(['core', 'api', 'util'])}/{r.choice(WORDS)}_{i}.py"; lines = []
            for n in range(1, 15):
                if r.random() < .2:
                    t = f"fix {r.choice(WORDS)} handling"; lines.append(f"    x = {n}  # TODO: {t}"); exp.append((rel, n, t))
                else: lines.append(f"    y = {n}")
            _w(root, "src/" + rel, "\n".join(lines) + "\n")
        _w(root, "src/notes.md", "TODO: not code\n")
        return [f"{p}:{n}: {t}" for p, n, t in sorted(exp)]

    def check(self, root, exp):
        t = _read(root, "todos.txt"); return t is not None and [l.rstrip() for l in t.strip().splitlines()] == exp


class IniPatch(Task):
    id = "ini_patch"
    prompt = ("config.ini has several sections. In section [database] set port to 6543 and add "
              "pool_size = 20 if missing; in every section whose name starts with 'cache' set ttl to 900. "
              "Leave everything else unchanged. Final answer: the list of sections you modified.")

    def setup(self, root, seed):
        r = random.Random(seed * 23); secs = ["server", "database"] + [f"cache_{w}" for w in r.sample(WORDS, 2 + seed)] + ["logging"]
        out = []
        for s in secs:
            out.append(f"[{s}]")
            if s == "database": out += ["host = db.local", "port = 5432", "user = app"]
            elif s.startswith("cache"): out += [f"ttl = {r.randint(10, 99)}", "size = 128"]
            else: out += [f"level = {r.choice(['info', 'debug'])}", "ttl = 5"]
            out.append("")
        _w(root, "config.ini", "\n".join(out)); return secs

    def check(self, root, exp):
        import configparser
        c = configparser.ConfigParser()
        try: c.read_string(_read(root, "config.ini") or "")
        except Exception: return False
        if c.sections() != exp: return False
        if c["database"].get("port") != "6543" or c["database"].get("pool_size") != "20" or c["database"].get("host") != "db.local": return False
        for s in exp:
            if s.startswith("cache") and (c[s].get("ttl") != "900" or c[s].get("size") != "128"): return False
            if not s.startswith("cache") and s != "database" and c[s].get("ttl") != "5": return False
        return True


class ExtSizes(Task):
    id = "bytes_by_extension"
    prompt = ("Walk the data/ tree recursively. Sum file sizes in bytes grouped by lowercase file extension "
              "(files without an extension use 'none'). Write sizes.csv with header ext,bytes sorted by bytes "
              "descending then ext ascending.")

    def setup(self, root, seed):
        r = random.Random(seed * 29); tot = {}
        for i in range(20):
            ext = r.choice(["log", "LOG", "csv", "json", "", "bin"][: 4 + seed])
            rel = f"data/{r.choice(['a', 'b', 'a/c'])}/f{i}" + (f".{ext}" if ext else "")
            n = r.randint(10, 3000); _w(root, rel, "x" * n)
            k = ext.lower() or "none"; tot[k] = tot.get(k, 0) + n
        return [f"{k},{v}" for k, v in sorted(tot.items(), key=lambda x: (-x[1], x[0]))]

    def check(self, root, exp):
        t = _read(root, "sizes.csv")
        if not t: return False
        l = [x.strip().replace(" ", "") for x in t.strip().splitlines()]
        return l[0] == "ext,bytes" and l[1:] == exp


TASKS = [RegionRevenue(), LogErrors(), JsonJoin(), NormalizeNames(), DedupeContacts(), WordFreq(),
         CsvToJson(), FindTodos(), IniPatch(), ExtSizes()]


def freeze_mtimes(root):
    for d, _, fs in os.walk(root):
        for f in fs: os.utime(os.path.join(d, f), (FIXED_MTIME, FIXED_MTIME))
        os.utime(d, (FIXED_MTIME, FIXED_MTIME))
