#!/usr/bin/env python3
"""Import a GCC-SWEEP markdown table into queue/queue.csv as batch <id> (status queued, NOT approved).
Usage: import_batch.py <sweep.md> <batch_id> [--max N]
Email rows go to the queue; form rows go to pending/<batch>-forms.md for browser sending."""
import csv, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import outreach as o

src, batch = Path(sys.argv[1]), sys.argv[2]
mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 10**6
rows = o.load()
seen_to = {r["to"].lower() for r in rows}
seen_firm = {r["firm"].lower() for r in rows}
excl = (o.ROOT / "EXCLUDE.txt").read_text().lower() if (o.ROOT / "EXCLUDE.txt").exists() else ""
lines = [l for l in src.read_text().splitlines() if l.startswith("|")]
hdr = [h.strip().lower() for h in lines[0].strip("|").split("|")]
def col(cells, *names):
    for n in names:
        for i, h in enumerate(hdr):
            if h.startswith(n) and i < len(cells):
                return cells[i].strip()
    return ""
added, forms = 0, []
n = len([r for r in rows if r["batch"] == batch])
for l in lines[2:]:
    c = [x.strip() for x in l.strip("|").split("|")]
    firm = col(c, "firm"); route = col(c, "route (email"); person = col(c, "named person"); hook = col(c, "hook (one")
    typ = col(c, "type").lower()
    if not firm or firm.lower() in seen_firm or firm.lower() in excl:
        continue
    em = re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", route)
    if not em:
        if "http" in route: forms.append(l)
        continue
    to = em.group(0)
    if to.lower() in seen_to: continue
    name = re.split(r"[,(–-]", person)[0].strip() if person and person.lower() not in ("—", "-", "n/a", "", "none") else ""
    if not name or len(name.split()) > 5 or "team" in name.lower(): name = ""
    greeting = name
    hk = re.sub(r"^(hook=generic[:;]?\s*)", "", hook, flags=re.I).strip() or "your work in the region"
    variant = "valuation" if re.search(r"audit|account|advis|consult|big ?4|valuation|transaction", typ) else "fund"
    n += 1
    rows.append({"id": f"{batch}-{n}", "batch": batch, "firm": firm, "to": to, "greeting_name": greeting or "team",
                 "hook": hk, "variant": variant, "status": "queued"})
    seen_to.add(to.lower()); seen_firm.add(firm.lower()); added += 1
    if added >= mx: break
o.save(rows)
if forms:
    (o.ROOT / "pending" / f"{batch}-forms.md").write_text("\n".join(lines[:2] + forms) + "\n")
print(f"added {added} email rows to {batch}; {len(forms)} form rows -> pending/{batch}-forms.md")
