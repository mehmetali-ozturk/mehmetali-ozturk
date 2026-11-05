"""Draw the GitHub contribution calendar and a few stats as ASCII, saved as light + dark SVGs.

Runs daily from .github/workflows/ascii-stats.yml. Locally:
    GITHUB_TOKEN=$(gh auth token) python scripts/ascii_stats.py
"""
import datetime as dt
import json
import os
import pathlib
import urllib.request
from collections import Counter
from xml.sax.saxutils import escape

LOGIN = os.environ.get("GH_LOGIN", "mehmetali-ozturk")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = pathlib.Path(__file__).resolve().parent.parent / "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: [OWNER], privacy: PUBLIC, isFork: false, first: 100) {
      totalCount
      nodes { stargazerCount primaryLanguage { name } }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}
"""

LEVELS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]
GLYPHS = [".", "+", "*", "#", "@"]
THEMES = {
    # deep water -> sky -> sunlight, same palette as the header
    "dark": {"fg": "#c9d1d9", "dim": "#6e7681", "accent": "#ffd27a",
             "lv": ["#30363d", "#2f6fd6", "#5e9ff0", "#b7dcff", "#ffd27a"]},
    "light": {"fg": "#1f2328", "dim": "#8c959f", "accent": "#c46a00",
              "lv": ["#d0d7de", "#8bb8f0", "#3f82e0", "#1b4fa6", "#e08a1e"]},
}
FONT = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'


def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(body["errors"])
    return body["data"]["user"]


def streaks(days):
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    i = len(counts) - 1
    if counts and counts[i] == 0:  # today may simply not have started yet
        i -= 1
    while i >= 0 and counts[i]:
        current += 1
        i -= 1
    return current, longest


def svg(user, theme):
    T = THEMES[theme]
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    current, longest = streaks(days)
    repos = user["repositories"]
    stars = sum(n["stargazerCount"] for n in repos["nodes"])
    langs = Counter(n["primaryLanguage"]["name"].lower() for n in repos["nodes"] if n["primaryLanguage"])

    px, py, left, top = 13, 15, 52, 64  # cell pitch, label gutter, grid top
    width = 820
    out = []
    t = lambda x, y, s, fill, extra="": out.append(
        f'<text x="{x}" y="{y}" fill="{fill}"{extra}>{s}</text>')

    t(16, 26, f'<tspan font-weight="700">~/mehmet-ali $</tspan> git log --since="1 year ago" | ascii', T["fg"])

    # month labels at the first week that starts in a new month
    last = None
    for wi, w in enumerate(weeks):
        m = dt.date.fromisoformat(w["contributionDays"][0]["date"]).strftime("%b").lower()
        if m != last and wi < len(weeks) - 2:
            t(left + wi * px, top - 10, m, T["dim"])
        last = m
    for row, name in ((1, "mon"), (3, "wed"), (5, "fri")):
        t(16, top + row * py + 10, name, T["dim"])

    # the grid: one glyph per day
    k = 0
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            row = dt.date.fromisoformat(d["date"]).isoweekday() % 7  # sunday = 0, like github
            lv = LEVELS.index(d["contributionLevel"])
            extra = f' class="hot" style="animation-delay:{(k * 0.37) % 4:.2f}s"' if lv == 4 else ""
            t(left + wi * px, top + row * py + 10, GLYPHS[lv], T["lv"][lv], extra)
            k += 1

    y = top + 7 * py + 22
    legend = "".join(f'<tspan fill="{T["lv"][i]}">{g}</tspan> ' for i, g in enumerate(GLYPHS))
    t(left, y, f'less {legend}more', T["dim"], ' xml:space="preserve"')

    y += 34
    rows = [
        ("contributions", f'{cal["totalContributions"]:,} in the last year'),
        ("current streak", f"{current} day{'s' if current != 1 else ''}"),
        ("longest streak", f"{longest} day{'s' if longest != 1 else ''}"),
        ("public repos", f'{repos["totalCount"]}   stars {stars}   followers {user["followers"]["totalCount"]}'),
    ]
    for label, value in rows:
        t(16, y, f'<tspan fill="{T["dim"]}">{label:<16}</tspan>{escape(value)}', T["fg"], ' xml:space="preserve"')
        y += 19

    if langs:
        y += 14
        t(16, y, "languages, by public repo", T["dim"])
        y += 21
        total = sum(langs.values())
        for name, n in langs.most_common(5):
            share = n / total
            filled = round(share * 30)
            bar = f'<tspan fill="{T["accent"]}">{"#" * filled}</tspan><tspan fill="{T["dim"]}">{"." * (30 - filled)}</tspan>'
            t(16, y, f'{escape(name):<16}[{bar}] {share * 100:>3.0f}%', T["fg"], ' xml:space="preserve"')
            y += 19

    height = y + 8
    style = (
        f"text{{font-family:{FONT};font-size:12.5px}}"
        ".hot{animation:twinkle 4s ease-in-out infinite}"
        "@keyframes twinkle{0%,100%{opacity:1}50%{opacity:.45}}"
        "@media (prefers-reduced-motion:reduce){.hot{animation:none}}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="ASCII contribution graph and GitHub stats for {escape(LOGIN)}">'
        f"<style>{style}</style>" + "".join(out) + "</svg>\n"
    )


def main():
    user = fetch()
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"stats-{theme}.svg").write_text(svg(user, theme), encoding="utf-8")
    print("wrote", ", ".join(f"stats-{t}.svg" for t in THEMES))


if __name__ == "__main__":
    main()
