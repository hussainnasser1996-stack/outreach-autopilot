#!/usr/bin/env python3
"""Import an INTL-R2 target file as batch <id> and tag each row country=INTL:<country> (sends Mon-Fri).
Usage: import_intl.py <file.md> <batch_id>"""
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import outreach as o

src, batch = Path(sys.argv[1]), sys.argv[2]
subprocess.run([sys.executable, str(Path(__file__).parent / "import_batch.py"), str(src), batch], check=True)
NICE = {"usa": "the US", "us": "the US", "united states": "the US", "uk": "the UK", "united kingdom": "the UK",
        "netherlands": "the Netherlands", "uae": "the UAE"}
lines = [l for l in src.read_text().splitlines() if l.startswith("|")]
hdr = [h.strip().lower() for h in lines[0].strip("|").split("|")]
fi, ci = hdr.index("firm"), hdr.index("city")
where = {}
for l in lines[2:]:
    c = [x.strip() for x in l.strip("|").split("|")]
    if len(c) > ci:
        ctry = c[ci].split(",")[-1].strip()
        where[c[fi].lower()] = NICE.get(ctry.lower(), ctry)
rows = o.load(); n = 0
for r in rows:
    if r["batch"] == batch and r["status"] == "queued":
        r["country"] = "INTL:" + where.get(r["firm"].lower(), "global markets"); n += 1
o.save(rows)
print(f"tagged {n} {batch} rows")
