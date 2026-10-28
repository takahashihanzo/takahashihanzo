#!/usr/bin/env python3
"""Regenerates stats.svg, langs.svg, trophies.svg and the projects table in README.md
from real GitHub data. Runs daily in .github/workflows/update-profile.yml.

  python scripts/update_profile.py            # live (needs GH_TOKEN / GITHUB_TOKEN)
  python scripts/update_profile.py --empty    # blank cards (no network)
  python scripts/update_profile.py --demo     # fake sample data, for previewing the design
"""
import hashlib, json, os, re, sys, urllib.request

USER = os.environ.get("PROFILE_USER", "takahashihanzo")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONO = "text{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace}"
FALLBACK = ["#00ff41", "#7dd3fc", "#00c853", "#fde047", "#4ade80", "#fb923c"]

QUERY = """
query($login:String!){
  user(login:$login){
    createdAt
    followers{totalCount}
    pullRequests{totalCount}
    contributionsCollection{totalCommitContributions restrictedContributionsCount}
    repositories(ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC,first:100,orderBy:{field:PUSHED_AT,direction:DESC}){
      totalCount
      nodes{
        name description url stargazerCount isArchived
        primaryLanguage{name color}
        languages(first:8,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}
      }
    }
  }
}"""


def fetch():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GH_TOKEN / GITHUB_TOKEN not set")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if data.get("errors") or not data.get("data", {}).get("user"):
        sys.exit(f"GraphQL error: {data}")
    u = data["data"]["user"]
    repos = [r for r in u["repositories"]["nodes"] if r["name"].lower() != USER.lower()]
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]
            langs.setdefault(n["name"], [0, n["color"]])
            langs[n["name"]][0] += e["size"]
    cc = u["contributionsCollection"]
    return {
        "created": u["createdAt"],
        "events": fetch_events(token),
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "repos": len(repos),
        "followers": u["followers"]["totalCount"],
        "prs": u["pullRequests"]["totalCount"],
        "langs": sorted(([n, v[0], v[1]] for n, v in langs.items()), key=lambda x: -x[1]),
        "top": sorted((r for r in repos if not r["isArchived"]), key=lambda r: -r["stargazerCount"])[:6],
    }


def fetch_events(token):
    try:
        req = urllib.request.Request(
            f"https://api.github.com/users/{USER}/events/public?per_page=30",
            headers={"Authorization": f"bearer {token}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:  # activity log is a bonus; never fail the run for it
        print("events unavailable:", e)
        return []


def demo():
    return {
        "created": "2026-07-15T00:00:00Z",
        "events": [
            {"type": "PushEvent", "created_at": "2026-10-28T18:02:00Z", "repo": {"name": "takahashihanzo/demo-repo"}, "payload": {"size": 3}},
            {"type": "PullRequestEvent", "created_at": "2026-10-27T11:20:00Z", "repo": {"name": "takahashihanzo/demo-repo"}, "payload": {"action": "opened", "number": 4}},
            {"type": "WatchEvent", "created_at": "2026-10-25T09:41:00Z", "repo": {"name": "someone/cool-tool"}, "payload": {}},
            {"type": "CreateEvent", "created_at": "2026-10-24T21:05:00Z", "repo": {"name": "takahashihanzo/new-idea"}, "payload": {"ref_type": "repository"}},
        ],
        "stars": 42, "commits": 380, "repos": 9, "followers": 17, "prs": 12,
        "langs": [["JavaScript", 520, "#f1e05a"], ["HTML", 300, "#e34c26"], ["CSS", 150, "#563d7c"], ["TypeScript", 90, "#3178c6"]],
        "top": [
            {"name": "demo-repo", "url": "#", "description": "Sample project", "stargazerCount": 12, "primaryLanguage": {"name": "JavaScript"}},
        ],
    }


def empty():
    return {"created": None, "events": [], "stars": 0, "commits": 0, "repos": 0, "followers": 0, "prs": 0, "langs": [], "top": []}


# ---------------------------------------------------------------- ranks
SCALES = {  # thresholds for C, B, A, S, SSS
    "stars": [1, 10, 50, 200, 1000],
    "followers": [1, 10, 50, 200, 1000],
    "commits": [10, 100, 500, 2000, 8000],
    "repos": [1, 5, 15, 40, 100],
    "prs": [1, 10, 50, 200, 800],
    "langs": [1, 3, 5, 8, 12],
}
LETTERS = ["C", "B", "A", "S", "SSS"]


def rank(key, v):
    lvl = sum(1 for t in SCALES[key] if v >= t)
    return ("-" if lvl == 0 else LETTERS[lvl - 1]), lvl


def overall(d):
    pts = sum(rank(k, d[k] if k != "langs" else len(d["langs"]))[1] for k in SCALES)
    if not pts:
        return "-", 0
    idx = min(pts * 10 // 30, 9)
    return ["D", "C", "B", "B+", "A", "A", "A+", "S", "S", "S+"][idx], (idx + 1) / 10


# ---------------------------------------------------------------- svgs
def lift(c):
    """Brighten language colors that vanish on the dark card (e.g. CSS #563d7c)."""
    try:
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    except Exception:
        return c
    if 0.299 * r + 0.587 * g + 0.114 * b < 110:
        r, g, b = (int(v + (255 - v) * 0.45) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------- hacker theme
import colorsys


def _shift(r, g, b):
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    h *= 360
    if s < 0.18 or not (235 <= h <= 350):
        return r, g, b                      # greys / whites / blues / yellows stay
    if l > 0.3:                             # neon pinks & purples -> terminal green
        h2, s2, l2 = 128 + (h - 250) * 0.2, 1.0, 0.38 + (l - 0.3) * 0.3
    else:                                   # dark purple surfaces -> green-black
        h2, s2, l2 = 140, min(s, 0.6) * 0.8, l * 0.7
    r2, g2, b2 = colorsys.hls_to_rgb(h2 / 360, l2, s2)
    return round(r2 * 255), round(g2 * 255), round(b2 * 255)


def recolor(text):
    text = re.sub(r"#([0-9a-fA-F]{6})(?![0-9a-zA-Z])", lambda m: "#%02x%02x%02x" % _shift(*(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))), text)
    def rg(m):
        r, g, b = _shift(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return f"rgba({r},{g},{b},{m.group(4)})"
    return re.sub(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", rg, text)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stats_svg(d):
    rows = [
        ("⭐", "Total Stars Earned:", d["stars"], "#fde047"),
        ("💻", "Commits (this year):", d["commits"], "#7dd3fc"),
        ("📦", "Public Repos:", d["repos"], "#4ade80"),
        ("👥", "Followers:", d["followers"], "#00c853"),
        ("🔀", "Pull Requests:", d["prs"], "#00ff41"),
    ]
    out = []
    for i, (ic, label, val, col) in enumerate(rows):
        y = 74 + 31 * i
        out.append(
            f'  <g class="row" style="animation-delay:{0.5 + 0.22 * i:.2f}s">\n'
            f'    <text x="24" y="{y}" font-size="14">{ic}</text>\n'
            f'    <text x="52" y="{y}" font-size="13.5" fill="#c9d1d9">{label}</text>\n'
            f'    <text x="316" y="{y}" text-anchor="end" font-size="14" font-weight="bold" fill="{col}">{val:,}</text>\n'
            f"  </g>"
        )
    letter, frac = overall(d)
    circ = 326.7
    arc = round(circ * max(frac, 0.02), 1)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 232" width="500" height="232" role="img" aria-label="Takahashi Hanzo's GitHub stats">
<defs><style><![CDATA[
{MONO}
@keyframes fadeSlide{{from{{opacity:0;transform:translateX(-14px)}}to{{opacity:1;transform:translateX(0)}}}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes rankPulse{{0%,100%{{opacity:.85}}50%{{opacity:1}}}}
@keyframes shineX{{0%{{transform:translateX(-160px) skewX(-15deg)}}60%,100%{{transform:translateX(560px) skewX(-15deg)}}}}
.row{{opacity:0;animation:fadeSlide .5s ease forwards}}
.rk{{animation:rankPulse 2.4s ease-in-out infinite}}
.sh{{animation:shineX 4.5s ease-in-out 2.4s infinite}}
]]></style>
<linearGradient id="tg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0%"><animate attributeName="stop-color" values="#00ff41;#00c853;#00ff41" dur="6s" repeatCount="indefinite"/></stop>
  <stop offset="100%"><animate attributeName="stop-color" values="#00c853;#00ff41;#00c853" dur="6s" repeatCount="indefinite"/></stop>
</linearGradient>
<linearGradient id="ringg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#00ff41"/><stop offset="100%" stop-color="#00a843"/></linearGradient>
<linearGradient id="shg" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#fff" stop-opacity="0"/><stop offset="50%" stop-color="#fff" stop-opacity=".07"/><stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient>
<clipPath id="cc"><rect x="1" y="1" width="498" height="230" rx="14"/></clipPath>
<filter id="g"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<rect x="1" y="1" width="498" height="230" rx="14" fill="#050a05" stroke="url(#tg)" stroke-width="1.5"/>
<text x="24" y="38" font-size="16" font-weight="bold" fill="url(#tg)">💀 root@hanzo:~# stats</text>

{chr(10).join(out)}

<g transform="translate(418,138)">
  <circle r="52" fill="none" stroke="#0f2412" stroke-width="9"/>
  <circle r="52" fill="none" stroke="url(#ringg)" stroke-width="9" stroke-linecap="round" stroke-dasharray="{arc} {circ}" stroke-dashoffset="{arc}" transform="rotate(-90)">
    <animate attributeName="stroke-dashoffset" from="{arc}" to="0" dur="1.6s" begin=".6s" fill="freeze" calcMode="spline" keySplines=".2 .8 .3 1"/>
  </circle>
  <text class="rk" y="14" text-anchor="middle" font-size="38" font-weight="bold" fill="#00ff41" filter="url(#g)">{letter}</text>
  <text y="76" text-anchor="middle" font-size="10.5" fill="#8b949e" opacity="0" style="animation:fadeIn .5s ease 1.8s forwards">RANK</text>
</g>

<g clip-path="url(#cc)"><rect class="sh" x="0" y="0" width="120" height="232" fill="url(#shg)"/></g>
</svg>
'''


def langs_svg(d):
    langs = d["langs"][:4]
    total = sum(l[1] for l in langs) or 1
    head = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 282" width="420" height="282" role="img" aria-label="Top languages">
<defs><style><![CDATA[
{MONO}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes shineX{{0%{{transform:translateX(-140px)}}60%,100%{{transform:translateX(460px)}}}}
.row{{opacity:0;animation:fadeUp .5s ease forwards}}
.sh{{animation:shineX 4s ease-in-out 2.2s infinite}}
]]></style>
<linearGradient id="tg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0%"><animate attributeName="stop-color" values="#00ff41;#00c853;#00ff41" dur="6s" repeatCount="indefinite"/></stop>
  <stop offset="100%"><animate attributeName="stop-color" values="#00c853;#00ff41;#00c853" dur="6s" repeatCount="indefinite"/></stop>
</linearGradient>
<linearGradient id="shg" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#fff" stop-opacity="0"/><stop offset="50%" stop-color="#fff" stop-opacity=".08"/><stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient>
<clipPath id="cardc"><rect x="1" y="1" width="418" height="280" rx="14"/></clipPath>
<clipPath id="stackc"><rect x="20" y="58" width="0" height="11" rx="5.5"><animate attributeName="width" from="0" to="380" dur="1.4s" begin=".4s" fill="freeze" calcMode="spline" keySplines=".2 .8 .3 1"/></rect></clipPath>
</defs>
<rect x="1" y="1" width="418" height="280" rx="14" fill="#050a05" stroke="url(#tg)" stroke-width="1.5"/>
<text x="20" y="34" font-size="16" font-weight="bold" fill="url(#tg)">📊 root@hanzo:~# langs</text>
'''
    tail = '<g clip-path="url(#cardc)"><rect class="sh" x="0" y="0" width="100" height="282" fill="url(#shg)" transform="skewX(-15)"/></g>\n</svg>\n'
    if not langs:
        msg = (
            '<text x="210" y="140" text-anchor="middle" font-size="14" fill="#c9d1d9">No public code yet</text>\n'
            '<text x="210" y="166" text-anchor="middle" font-size="12" fill="#8b949e">Push your first repo — this card fills itself.</text>\n'
        )
        return head + msg + tail
    stack, rows, x = [], [], 20.0
    for i, (name, size, color) in enumerate(langs):
        col = lift(color) if color else FALLBACK[i % len(FALLBACK)]
        pct = size / total * 100
        w = 380 * size / total
        stack.append(f'<rect x="{x:.1f}" y="58" width="{w:.1f}" height="11" fill="{col}"/>')
        x += w
        y = 91 + 42 * i
        bw = 268 * pct / 100
        delay = 0.90 + 0.35 * i
        rows.append(
            f'  <g class="row" style="animation-delay:{delay:.2f}s">\n'
            f'    <circle cx="26" cy="{y}" r="5" fill="{col}"/>\n'
            f'    <text x="40" y="{y + 5}" font-size="13" fill="#e6edf3" font-weight="bold">{esc(name)}</text>\n'
            f'    <text x="396" y="{y + 5}" text-anchor="end" font-size="13" fill="{col}" font-weight="bold">{pct:.1f}%</text>\n'
            f'    <rect x="40" y="{y + 13}" width="268" height="9" rx="4.5" fill="#0f2412"/>\n'
            f'    <rect x="40" y="{y + 13}" width="{bw:.1f}" height="9" rx="4.5" fill="{col}">\n'
            f'      <animate attributeName="width" from="0" to="{bw:.1f}" dur="1.1s" begin="{delay + .15:.2f}s" fill="freeze" calcMode="spline" keySplines=".2 .8 .3 1"/>\n'
            f"    </rect>\n  </g>"
        )
    return head + f'<g clip-path="url(#stackc)">{"".join(stack)}</g>\n\n' + "\n".join(rows) + "\n" + tail


def trophies_svg(d):
    cells = [
        ("⭐", "Stargazer", "stars", f"Stars {d['stars']:,}", "#fde047", d["stars"]),
        ("👥", "Rising Star", "followers", f"Followers {d['followers']:,}", "#00c853", d["followers"]),
        ("💻", "Committer", "commits", f"Commits {d['commits']:,}", "#7dd3fc", d["commits"]),
        ("📦", "Creator", "repos", f"Repos {d['repos']:,}", "#4ade80", d["repos"]),
        ("🔀", "Collaborator", "prs", f"PRs {d['prs']:,}", "#00ff41", d["prs"]),
        ("🧠", "Polyglot", "langs", f"Languages {len(d['langs'])}", "#00e676", len(d["langs"])),
    ]
    out = []
    for i, (ic, title, key, sub, col, val) in enumerate(cells):
        letter, lvl = rank(key, val)
        x = 12 + 180 * i
        cx = x + 84
        bar = 132 * lvl / 5
        d0 = 0.30 + 0.18 * i
        out.append(
            f'  <g class="cell" style="animation-delay:{d0:.2f}s">\n'
            f'    <rect x="{x}" y="12" width="168" height="144" rx="14" fill="#050a05" stroke="{col}" stroke-opacity=".55" stroke-width="1.3"/>\n'
            f'    <text x="{cx}.0" y="52" text-anchor="middle" font-size="30">{ic}</text>\n'
            f'    <text class="rk" x="{x + 152}" y="40" text-anchor="end" font-size="{24 if len(letter) > 2 else 30}" font-weight="bold" fill="{col}" style="animation-delay:{d0 + .4:.2f}s">{letter}</text>\n'
            f'    <text x="{cx}.0" y="90" text-anchor="middle" font-size="14" font-weight="bold" fill="#e6edf3">{title}</text>\n'
            f'    <text x="{cx}.0" y="112" text-anchor="middle" font-size="11" fill="#9aa4b2">{sub}</text>\n'
            f'    <rect x="{x + 18}" y="124" width="132" height="5" rx="2.5" fill="#0f2412"/>\n'
            f'    <rect x="{x + 18}" y="124" width="0" height="5" rx="2.5" fill="{col}">\n'
            f'      <animate attributeName="width" from="0" to="{bar:.1f}" dur="1s" begin="{d0 + .3:.2f}s" fill="freeze" calcMode="spline" keySplines=".2 .8 .3 1"/>\n'
            f"    </rect>\n  </g>"
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1092 168" width="1092" height="168" role="img" aria-label="GitHub trophies">
<defs><style><![CDATA[
{MONO}
@keyframes popCell{{0%{{opacity:0;transform:translateY(16px) scale(.85)}}70%{{opacity:1;transform:translateY(-3px) scale(1.03)}}100%{{opacity:1;transform:translateY(0) scale(1)}}}}
@keyframes rankGlow{{0%,100%{{opacity:.75}}50%{{opacity:1}}}}
@keyframes shineX2{{0%{{transform:translateX(-200px) skewX(-15deg)}}60%,100%{{transform:translateX(1172px) skewX(-15deg)}}}}
.cell{{opacity:0;animation:popCell .55s cubic-bezier(.2,.8,.3,1.2) forwards;transform-box:fill-box;transform-origin:center}}
.rk{{animation:rankGlow 2.2s ease-in-out infinite}}
.sh2{{animation:shineX2 5s ease-in-out 2s infinite}}
]]></style>
<linearGradient id="shg2" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#fff" stop-opacity="0"/><stop offset="50%" stop-color="#fff" stop-opacity=".07"/><stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient>
<clipPath id="tc"><rect x="0" y="0" width="1092" height="168" rx="14"/></clipPath>
</defs>

{chr(10).join(out)}
<g clip-path="url(#tc)"><rect class="sh2" x="0" y="0" width="140" height="168" fill="url(#shg2)"/></g>
</svg>
'''



CHROME = """<rect x="1" y="1" width="{w1}" height="{h1}" rx="14" fill="#030603" stroke="url(#tg)" stroke-width="1.5"/>
<rect x="1" y="1" width="{w1}" height="30" rx="14" fill="#0d1f0f"/><rect x="1" y="16" width="{w1}" height="15" fill="#0d1f0f"/>
<circle cx="22" cy="16" r="5" fill="#ff5f57"/><circle cx="40" cy="16" r="5" fill="#febc2e"/><circle cx="58" cy="16" r="5" fill="#28c840"/>
<text x="{cx}" y="20" text-anchor="middle" font-size="12" fill="#8b949e">{title}</text>"""

BASE_CSS = """@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}
@keyframes scan{0%{transform:translateY(-40px)}100%{transform:translateY(__H__px)}}
.ln{opacity:0;animation:fadeIn .25s ease forwards}
.cur{animation:blink 1s step-end infinite}
.scan{animation:scan 5s linear infinite}"""

DEFS = """<linearGradient id="tg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0%"><animate attributeName="stop-color" values="#00ff41;#00c853;#00ff41" dur="6s" repeatCount="indefinite"/></stop>
  <stop offset="100%"><animate attributeName="stop-color" values="#00c853;#00ff41;#00c853" dur="6s" repeatCount="indefinite"/></stop>
</linearGradient>
<linearGradient id="sc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#00ff41" stop-opacity="0"/><stop offset="100%" stop-color="#00ff41" stop-opacity=".12"/></linearGradient>
<pattern id="crt" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#00ff41" opacity=".05"/></pattern>
<filter id="gl"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>"""

SKULL = [
    "     ______",
    '  .-"      "-.',
    " /            \\",
    "|              |",
    "|,  .-.  .-.  ,|",
    "| )(__/  \\__)( |",
    "|/     /\\     \\|",
    "(_     ^^     _)",
    " \\__|IIIIII|__/",
    "  | \\IIIIII/ |",
    "  \\          /",
    "   `--------`",
]


def uptime(created):
    if not created:
        return "just booted"
    import datetime as dt
    c = dt.datetime.strptime(created[:10], "%Y-%m-%d")
    days = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - c).days
    y, rem = divmod(days, 365)
    mo, dd = divmod(rem, 30)
    return ", ".join(x for x in (f"{y} yr" if y else "", f"{mo} mo" if mo else "", f"{dd} d") if x)


def neofetch_svg(d):
    W, H = 1092, 372
    top = ", ".join(l[0] for l in d["langs"][:3]) or "none yet"
    info = [
        ("", "takahashihanzo", "@", "github"),
        ("sep", "", "", ""),
        ("OS", "GitHub (stealth edition)", "", ""),
        ("Uptime", uptime(d.get("created")), "", ""),
        ("Repos", f"{d['repos']}", "", ""),
        ("Stars", f"{d['stars']}", "", ""),
        ("Followers", f"{d['followers']}", "", ""),
        ("Commits", f"{d['commits']} this year", "", ""),
        ("Languages", top, "", ""),
        ("Theme", "Matrix Green [dark]", "", ""),
        ("Status", "learning, building, lurking", "", ""),
    ]
    sk = "".join(
        f'<tspan x="60" dy="{0 if i == 0 else 19}" class="ln" style="animation-delay:{0.3 + i * 0.12:.2f}s">{esc(l)}</tspan>' for i, l in enumerate(SKULL)
    )
    rows = []
    for i, (k, v, a, b) in enumerate(info):
        y = 82 + i * 21
        dl = 0.4 + i * 0.22
        if k == "":
            rows.append(f'<text class="ln" x="360" y="{y}" font-size="15" font-weight="bold" style="animation-delay:{dl:.2f}s"><tspan fill="#00ff41">{v}</tspan><tspan fill="#8b949e">{a}</tspan><tspan fill="#00ff41">{b}</tspan></text>')
        elif k == "sep":
            rows.append(f'<text class="ln" x="360" y="{y}" font-size="15" fill="#14501f" style="animation-delay:{dl:.2f}s">----------------------</text>')
        else:
            rows.append(f'<text class="ln" x="360" y="{y}" font-size="15" style="animation-delay:{dl:.2f}s"><tspan fill="#00ff41" font-weight="bold">{k}</tspan><tspan fill="#8b949e">: </tspan><tspan fill="#e6edf3">{esc(v)}</tspan></text>')
    sw = ["#00ff41", "#00c853", "#00a843", "#fde047", "#22d3ee", "#ff2b2b", "#e6edf3", "#14501f"]
    swatch = "".join(f'<rect x="{360 + i * 30}" y="{82 + len(info) * 21 + 6}" width="26" height="14" fill="{c}"/>' for i, c in enumerate(sw))
    cmd_y = 56
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="neofetch for takahashihanzo">
<defs><style><![CDATA[
{MONO}
{BASE_CSS.replace('__H__', str(H))}
]]></style>
{DEFS}
<clipPath id="cp"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14"/></clipPath>
</defs>
{CHROME.format(w1=W-2, h1=H-2, cx=W/2, title="takahashihanzo@github: ~")}
<text x="22" y="{cmd_y}" font-size="14"><tspan fill="#00ff41" font-weight="bold">root@hanzo</tspan><tspan fill="#8b949e">:~# </tspan><tspan fill="#e6edf3">neofetch</tspan></text>
<text x="60" y="84" font-size="15" fill="#00ff41" filter="url(#gl)" xml:space="preserve">{sk}</text>
{chr(10).join(rows)}
<g class="ln" style="animation-delay:3.2s">{swatch}</g>
<text x="22" y="{H-16}" font-size="14"><tspan fill="#00ff41" font-weight="bold">root@hanzo</tspan><tspan fill="#8b949e">:~# </tspan></text>
<rect class="cur" x="150" y="{H-29}" width="9" height="16" fill="#00ff41"/>
<g clip-path="url(#cp)"><rect class="scan" x="0" y="0" width="{W}" height="40" fill="url(#sc)"/><rect width="{W}" height="{H}" fill="url(#crt)"/></g>
</svg>
"""


def event_line(e):
    t = e.get("type", "")
    repo = (e.get("repo") or {}).get("name", "?")
    p = e.get("payload") or {}
    when = (e.get("created_at") or "")[5:16].replace("T", " ")
    if t == "PushEvent":
        n = p.get("size") or len(p.get("commits", []) or []) or 1
        return when, "PUSH", "#00ff41", f"{n} commit{'s' if n != 1 else ''} → {repo}"
    if t == "PullRequestEvent":
        return when, "PR  ", "#22d3ee", f"{p.get('action', 'updated')} #{p.get('number', '?')} in {repo}"
    if t == "CreateEvent":
        return when, "NEW ", "#00ff41", f"created {p.get('ref_type', 'ref')} {repo}"
    if t == "WatchEvent":
        return when, "STAR", "#fde047", f"starred {repo}"
    if t == "ForkEvent":
        return when, "FORK", "#e879f9", f"forked {repo}"
    if t in ("IssuesEvent", "IssueCommentEvent"):
        return when, "ISSU", "#ff2b2b", f"activity in {repo}"
    return when, "EVNT", "#8b949e", f"{t.replace('Event', '').lower()} · {repo}"


def activity_svg(d):
    W = 1092
    evs = [event_line(e) for e in d.get("events", [])[:7]]
    if not evs:
        evs = [("--", "IDLE", "#8b949e", "no public activity yet — go commit something 💀")]
    H = 100 + 24 * len(evs)
    rows = []
    for i, (when, tag, col, msg) in enumerate(evs):
        y = 84 + i * 24
        rows.append(
            f'<text class="ln" x="22" y="{y}" font-size="14" style="animation-delay:{0.5 + i * 0.35:.2f}s">'
            f'<tspan fill="#8b949e">[{esc(when)}]</tspan><tspan fill="{col}" font-weight="bold"> {tag} </tspan><tspan fill="#cdd3dd">{esc(msg[:100])}</tspan></text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Recent GitHub activity log">
<defs><style><![CDATA[
{MONO}
{BASE_CSS.replace('__H__', str(H))}
]]></style>
{DEFS}
<clipPath id="cp"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14"/></clipPath>
</defs>
{CHROME.format(w1=W-2, h1=H-2, cx=W/2, title="activity.log")}
<text x="22" y="58" font-size="14"><tspan fill="#00ff41" font-weight="bold">root@hanzo</tspan><tspan fill="#8b949e">:~# </tspan><tspan fill="#e6edf3">tail -f /var/log/github/activity.log</tspan></text>
{chr(10).join(rows)}
<rect class="cur" x="22" y="{84 + len(evs) * 24 - 8}" width="9" height="15" fill="#00ff41"/>
<g clip-path="url(#cp)"><rect class="scan" x="0" y="0" width="{W}" height="40" fill="url(#sc)"/><rect width="{W}" height="{H}" fill="url(#crt)"/></g>
</svg>
"""


def projects_md(d):
    if not d["top"]:
        return "| 🚀 Project | 💻 Tech | ⭐ |\n|:---|:---:|:---:|\n| ✨ *Your repos show up here automatically after the daily update* | — | — |"
    rows = ["| 🚀 Project | 💻 Tech | ⭐ |", "|:---|:---:|:---:|"]
    for r in d["top"]:
        lang = (r.get("primaryLanguage") or {}).get("name")
        rows.append(f"| [{r['name']}]({r['url']}) | {'`' + lang + '`' if lang else '—'} | {r['stargazerCount']} |")
    return "\n".join(rows)


def write(path, text):
    full = os.path.join(ROOT, path)
    if path.endswith(".svg"):
        text = recolor(text)
    old = open(full, encoding="utf-8").read() if os.path.exists(full) else None
    if old != text:
        open(full, "w", encoding="utf-8").write(text)
    return old != text


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    d = demo() if mode == "--demo" else empty() if mode == "--empty" else fetch()
    changed = {
        "stats": write("stats.svg", stats_svg(d)),
        "langs": write("langs.svg", langs_svg(d)),
        "trophies": write("trophies.svg", trophies_svg(d)),
        "neofetch": write("neofetch.svg", neofetch_svg(d)),
        "activity": write("activity.svg", activity_svg(d)),
    }
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    new = re.sub(r"(<!--PROJECTS:START-->\n).*?(\n<!--PROJECTS:END-->)", lambda m: m.group(1) + projects_md(d) + m.group(2), readme, flags=re.S)
    for name, ch in changed.items():  # bump ?v= so GitHub's image cache refreshes
        if ch:
            h = hashlib.sha1(open(os.path.join(ROOT, f"{name}.svg"), "rb").read()).hexdigest()[:7]
            new = re.sub(rf"({name}\.svg\?v=)\w+", rf"\g<1>{h}", new)
    if new != readme:
        open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8").write(new)
    print("updated:", [k for k, v in changed.items() if v] or "nothing", "| readme changed:", new != readme)


if __name__ == "__main__":
    main()
