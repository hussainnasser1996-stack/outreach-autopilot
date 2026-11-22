#!/usr/bin/env python3
"""Outreach autopilot: send approved advisory emails, follow up once, watch for bounces and replies.

Commands:
  outreach.py send      [--dry-run] [--limit N]   send next queued rows (approved batches only)
  outreach.py followup  [--dry-run]               one follow-up, in-thread, after FOLLOWUP_DAYS with no reply
  outreach.py inbox                               scan Gmail (IMAP) for bounces and replies, update the queue
  outreach.py status                              counts by status
  outreach.py daily     [--dry-run]               inbox -> followup -> send -> phone summary

Credentials: env GMAIL_APP_PASSWORD, or macOS Keychain service "gmail-app-password-bahrain".
Never printed or logged.
"""
import csv, datetime as dt, email.utils, imaplib, json, os, random, re, smtplib, ssl, subprocess, sys, time
import urllib.request
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
QUEUE = ROOT / "queue" / "queue.csv"
LOG = ROOT / "log" / "sent.md"
FIELDS = ["id", "batch", "firm", "to", "greeting_name", "hook", "variant", "status",
          "sent_at", "message_id", "followup_at", "note", "country"]
LINKEDIN = "https://www.linkedin.com/in/hussain-nasser-8b3a4917b"
WEBSITE = "https://hussain-nasser.vercel.app"

MIDDLE = {
    "fund": "I support funds and advisers with financial models, valuations and investor materials when the team is busy.",
    "valuation": "I support valuation and transaction teams with models and valuation packs when the team is busy.",
    "gaming": "My investment work covers AI and interactive media, including gaming, and I can help with deal analysis, valuations, financial models and investor materials, plus a Saudi and GCC view when it is useful.",
}


# ---------- control ----------
def control():
    c = {}
    for line in (ROOT / "CONTROL.md").read_text().splitlines():
        m = re.match(r"^\s*([a-z_]+):\s*(.*?)\s*$", line)
        if m:
            c[m.group(1)] = m.group(2)
    c["approved_batches"] = [b.strip() for b in c.get("approved_batches", "").strip("[]").split(",") if b.strip()]
    c["daily_cap"] = int(c.get("daily_cap", "30"))
    c["followup_days"] = int(c.get("followup_days", "7"))
    c["send_days"] = [d.strip() for d in c.get("send_days", "Sun,Mon,Tue,Wed,Thu").split(",")]
    c["uae_send_days"] = [d.strip() for d in c.get("uae_send_days", "Mon,Tue,Wed,Thu,Fri").split(",")]
    return c


def ksa_day():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%a")


def workday(r, c):
    """True if today (KSA time) is a working day in the row's country. UAE and INTL rows Mon-Fri, rest of GCC Sun-Thu."""
    ctry = (r.get("country") or "").upper()
    days = c["uae_send_days"] if (ctry == "UAE" or ctry.startswith("INTL")) else c["send_days"]
    return ksa_day() in days


# ---------- queue ----------
def load():
    if not QUEUE.exists():
        return []
    with QUEUE.open(newline="") as f:
        return list(csv.DictReader(f))


def save(rows):
    tmp = QUEUE.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(QUEUE)


# ---------- credentials / transport ----------
def password():
    p = os.environ.get("GMAIL_APP_PASSWORD")
    if p:
        return p.replace(" ", "")
    try:
        return subprocess.check_output(
            ["security", "find-generic-password", "-s", "gmail-app-password-bahrain", "-w"],
            stderr=subprocess.DEVNULL).decode().strip().replace(" ", "")
    except Exception:
        sys.exit("No Gmail app password: set GMAIL_APP_PASSWORD or Keychain 'gmail-app-password-bahrain'.")


def smtp():
    s = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60)
    s.login(CFG["from_email"], password())
    return s


def ntfy(title, body, priority="default"):
    topic = CFG.get("ntfy_topic")
    if not topic:
        return
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), method="POST",
                                     headers={"Title": title.encode("ascii", "ignore").decode(),
                                              "Priority": priority, "Tags": "envelope"})
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:
        print("ntfy failed:", e)


# ---------- message building ----------
def bodies(r):
    mid = MIDDLE.get(r.get("variant") or "fund", MIDDLE["fund"])
    name = r["greeting_name"] or "team"
    hook = r["hook"].rstrip(".")
    firm = r["firm"]
    poss = firm + ("'" if firm.endswith("s") else "'s")
    ctry = r.get("country") or ""
    if ctry.upper().startswith("INTL:"):
        region = ctry.split(":", 1)[1].strip()
    else:
        region = {"UAE": "the UAE"}.get(ctry.upper(), "Saudi Arabia" if r["batch"] == "G3" else "the Gulf")
    what = "gaming companies and investors" if r.get("variant") == "gaming" else "investment and advisory firms"
    opener = f"I came across {firm} while looking at {what} in {region}."
    text = (f"Dear {name},\n\n{opener}\n\n"
            f"I'm an Investment Director working across Saudi Arabia and global markets. {mid}\n\n"
            f"I've attached a short sample case. You can see my background and recent work on my "
            f"LinkedIn profile ({LINKEDIN}) and my personal website ({WEBSITE}).\n\n"
            f"I'd be glad to help whenever it's useful.\n\n"
            f"Kind regards,\nHussain Nasser\nInvestment Director\n+973 3874 2734\n")
    html = (f"<div>Dear {name},</div><div><br></div>"
            f"<div>{opener}</div><div><br></div>"
            f"<div>I'm an Investment Director working across Saudi Arabia and global markets. {mid}</div><div><br></div>"
            f"<div>I've attached a short sample case. You can see my background and recent work on my "
            f"<a href=\"{LINKEDIN}\">LinkedIn profile</a> and my <a href=\"{WEBSITE}\">personal website</a>.</div><div><br></div>"
            f"<div>I'd be glad to help whenever it's useful.</div><div><br></div>"
            f"<div>Kind regards,<br>Hussain Nasser<br>Investment Director<br>"
            f"<a href=\"tel:+97338742734\">+973 3874 2734</a><br>"
            f"<a href=\"{LINKEDIN}\">LinkedIn</a> &middot; <a href=\"{WEBSITE}\">Website</a></div>")
    return text, html


def build(r):
    m = EmailMessage()
    m["From"] = email.utils.formataddr(("Hussain Nasser", CFG["from_email"]))
    m["To"] = r["to"]
    m["Subject"] = "Gaming investment and Saudi market support" if r.get("variant") == "gaming" else CFG["subject"]
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = email.utils.make_msgid(domain="gmail.com")
    text, html = bodies(r)
    m.set_content(text)
    m.add_alternative(html, subtype="html")
    pdf = ROOT / CFG["attachment"]
    m.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)
    return m


def build_followup(r):
    m = EmailMessage()
    m["From"] = email.utils.formataddr(("Hussain Nasser", CFG["from_email"]))
    m["To"] = r["to"]
    m["Subject"] = "Re: " + ("Gaming investment and Saudi market support" if r.get("variant") == "gaming" else CFG["subject"])
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = email.utils.make_msgid(domain="gmail.com")
    if r.get("message_id"):
        m["In-Reply-To"] = r["message_id"]
        m["References"] = r["message_id"]
    first = (r["greeting_name"] or "team").split()[0] if r["greeting_name"] and "team" not in r["greeting_name"].lower() else "team"
    text = (f"Hi {first},\n\nJust following up on my note from last week in case it's useful. "
            f"Happy to help whenever your team has a live deal or a model that needs extra hands.\n\n"
            f"Best regards,\nHussain")
    m.set_content(text)
    return m


def log(line):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def valid_email(a):
    return bool(re.fullmatch(r"[^@\s,;]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", a or ""))


# ---------- commands ----------
def cmd_send(dry=False, limit=None):
    c = control()
    if c.get("mode") == "paused":
        print("paused"); return []
    rows = load()
    sent_today = sum(1 for r in rows if r["sent_at"].startswith(dt.date.today().isoformat()))
    cap = min(c["daily_cap"] - sent_today, limit or 10**6)
    todo = [r for r in rows if r["status"] == "queued" and r["batch"] in c["approved_batches"] and workday(r, c)]
    done = []
    if cap <= 0 or not todo:
        print(f"nothing to send (cap left {cap}, approved queued {len(todo)})"); return []
    conn = None if dry else smtp()
    for r in todo[:cap]:
        if not valid_email(r["to"]):
            r["status"] = "skipped"; r["note"] = "invalid address"; continue
        m = build(r)
        if dry:
            out = ROOT / "log" / "dry-run"; out.mkdir(parents=True, exist_ok=True)
            (out / f"{r['id']}.eml").write_bytes(bytes(m))
            print("DRY", r["id"]); done.append(r); continue
        try:
            conn.send_message(m)
        except smtplib.SMTPServerDisconnected:
            conn = smtp(); conn.send_message(m)
        except Exception as e:
            r["note"] = f"send error: {type(e).__name__}"; print("ERR", r["id"], type(e).__name__); continue
        r["status"], r["sent_at"], r["message_id"] = "sent", now(), m["Message-ID"]
        log(f"| {r['sent_at']} | {r['id']} | {r['firm']} | {r['to']} | initial |")
        save(rows); done.append(r); print("SENT", r["id"])
        time.sleep(random.uniform(CFG.get("gap_min_s", 45), CFG.get("gap_max_s", 120)))
    if conn:
        conn.quit()
    save(rows)
    return done


def cmd_followup(dry=False):
    c = control()
    if c.get("mode") == "paused" or c.get("followups", "on") != "on":
        return []
    rows = load()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=c["followup_days"])
    due = [r for r in rows if r["status"] == "sent" and not r["followup_at"] and r["sent_at"] and workday(r, c)
           and dt.datetime.strptime(r["sent_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc) < cutoff]
    done = []
    conn = None if (dry or not due) else smtp()
    for r in due:
        m = build_followup(r)
        if dry:
            print("DRY followup", r["id"]); done.append(r); continue
        conn.send_message(m)
        r["followup_at"] = now(); r["status"] = "followed_up"
        log(f"| {r['followup_at']} | {r['id']} | {r['firm']} | {r['to']} | follow-up |")
        save(rows); done.append(r)
        time.sleep(random.uniform(30, 90))
    if conn:
        conn.quit()
    return done


def _dec(v):
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


def cmd_inbox():
    rows = load()
    by_addr = {r["to"].lower(): r for r in rows if r["status"] in ("sent", "followed_up")}
    by_domain = {}
    for r in by_addr.values():
        by_domain.setdefault(r["to"].split("@")[-1].lower(), []).append(r)
    by_mid = {r["message_id"]: r for r in rows if r["message_id"]}
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(CFG["from_email"], password())
    M.select("INBOX", readonly=True)
    since = (dt.date.today() - dt.timedelta(days=14)).strftime("%d-%b-%Y")
    _, data = M.search(None, f'(SINCE "{since}")')
    events = []
    for num in data[0].split()[-400:]:
        # Fetch headers and body separately: Gmail may return the two parts in either order.
        _, hm = M.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT IN-REPLY-TO REFERENCES)])")
        _, bm = M.fetch(num, "(BODY.PEEK[TEXT]<0.4000>)")
        hdr = b"".join(p[1] for p in hm if isinstance(p, tuple))
        raw = hdr + b"\r\n" + b"".join(p[1] for p in bm if isinstance(p, tuple))
        e = message_from_bytes(hdr)
        frm = email.utils.parseaddr(_dec(e.get("From")))[1].lower()
        refs = (e.get("In-Reply-To", "") + " " + e.get("References", "")).split()
        text = raw.decode("utf-8", "ignore")
        if "mailer-daemon" in frm or "postmaster" in frm:
            # Bounce bodies are often base64 / quoted-printable: fetch the whole notice and decode every part.
            _, full = M.fetch(num, "(BODY.PEEK[])")
            fm = message_from_bytes(b"".join(p[1] for p in full if isinstance(p, tuple)))
            parts = [fm.get("X-Failed-Recipients", "")]
            for part in fm.walk():
                pl = part.get_payload(decode=True)
                if pl:
                    parts.append(pl.decode("utf-8", "ignore"))
                elif part.get_content_type() in ("message/delivery-status", "message/rfc822"):
                    parts.append(str(part))
            text = (text + " " + " ".join(parts)).lower()
            for addr, r in by_addr.items():
                if addr in text and r["status"] != "bounced":
                    r["status"], r["note"] = "bounced", "bounce " + now()[:10]; events.append(("bounce", r))
            continue
        r = next((by_mid[x] for x in refs if x in by_mid), None) or by_addr.get(frm)
        if not r and frm.split("@")[-1] in by_domain:
            r = by_domain[frm.split("@")[-1]][0]
        if r and r["status"] not in ("replied", "bounced"):
            probe = (_dec(e.get("Subject")) + " " + text[:1500]).lower()
            auto = (re.search(r"no-?reply|do-?not-?reply|notifications?@", frm) or re.search(
                r"auto(matic)?[- ]?(reply|response|confirmation)|out of (the )?office|\booo\b|away from the office|on leave"
                r"|ticket (id|no|number|#)|has been (created|received|logged)|we (have )?received your (message|email|enquiry|inquiry|request)"
                r"|thank you for (contacting|writing|reaching out to|your (message|email|enquiry|inquiry))"
                r"|تذكرة|تم استلام|رد آلي", probe))
            if auto:
                r["note"] = "auto-reply " + now()[:10]
            else:
                r["status"], r["note"] = "replied", f"reply from {frm} {now()[:10]}"; events.append(("reply", r))
    M.logout()
    save(rows)
    for kind, r in events:
        print(kind.upper(), r["id"])
        if kind == "reply":
            ntfy(f"Reply: {r['firm']}", f"{r['firm']} replied to your advisory email. Check Gmail (.bahrain).", "high")
    return events


def cmd_status():
    rows = load(); out = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    print(json.dumps(out, indent=1)); return out


def cmd_daily(dry=False):
    c = control()
    stamp = ROOT / "state" / "last_daily.txt"
    ksa = dt.datetime.now(dt.timezone(dt.timedelta(hours=3)))
    if not dry and "--force" not in sys.argv:
        if ksa.hour < 8:
            print(ksa.isoformat(), "before 08:00 KSA, skip"); return
        if stamp.exists() and stamp.read_text().strip() == ksa.date().isoformat():
            print(ksa.isoformat(), "already ran today, skip"); return
    print("=== daily run", ksa.isoformat())
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%a")
    ev = [] if dry else cmd_inbox()
    fu = cmd_followup(dry)
    sent = cmd_send(dry)
    st = cmd_status()
    queued_unapproved = sum(1 for r in load() if r["status"] == "queued" and r["batch"] not in c["approved_batches"])
    msg = (f"Sent {len(sent)} new, {len(fu)} follow-ups. Replies {sum(1 for k,_ in ev if k=='reply')}, "
           f"bounces {sum(1 for k,_ in ev if k=='bounce')}. Totals: {json.dumps(st)}."
           + (f" {queued_unapproved} rows wait for your OK." if queued_unapproved else ""))
    print(msg)
    if not dry:
        ntfy("Outreach autopilot", msg)
        stamp.parent.mkdir(exist_ok=True); stamp.write_text(ksa.date().isoformat() + "\n")


def cmd_selftest():
    """Prove the full path works: SMTP login + real send to self, IMAP login + find it, ntfy push."""
    m = EmailMessage()
    m["From"] = email.utils.formataddr(("Hussain Nasser", CFG["from_email"]))
    m["To"] = CFG["from_email"]
    tag = "autopilot-selftest-" + now()
    m["Subject"] = tag
    m["Message-ID"] = email.utils.make_msgid(domain="gmail.com")
    m.set_content("Outreach autopilot self-test. Safe to delete.")
    s = smtp(); s.send_message(m); s.quit(); print("SMTP send OK")
    for _ in range(12):
        time.sleep(10)
        M = imaplib.IMAP4_SSL("imap.gmail.com"); M.login(CFG["from_email"], password())
        M.select("INBOX", readonly=True)
        _, d = M.search(None, f'(SUBJECT "{tag}")'); M.logout()
        if d[0].split():
            print("IMAP find OK"); ntfy("Outreach autopilot", "Self-test passed (cloud send + inbox read)."); return
    sys.exit("IMAP: self-test mail not found after 2 min")


if __name__ == "__main__":
    a = sys.argv[1:] or ["status"]
    dry = "--dry-run" in a
    lim = int(a[a.index("--limit") + 1]) if "--limit" in a else None
    {"send": lambda: cmd_send(dry, lim), "followup": lambda: cmd_followup(dry), "inbox": cmd_inbox,
     "status": cmd_status, "daily": lambda: cmd_daily(dry), "selftest": cmd_selftest}[a[0]]()
