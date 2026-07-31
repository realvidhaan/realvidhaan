#!/usr/bin/env python3
"""Regenerate every SVG in assets/. Pure stdlib, no deps.

    python3 assets/build.py            # rebuild, fetching live LeetCode stats
    python3 assets/build.py --offline  # rebuild from assets/leetcode.json

Output is deterministic (fixed RNG seeds), so re-running with unchanged data
produces byte-identical files and the daily workflow makes no noise commits.
"""
import json
import os
import random
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- palette ---
VOID = "#05070A"   # deepest background
PANEL = "#080D12"  # terminal body
LINE = "#0B3B24"   # hairline structure
DIM = "#00B368"    # rain trail, secondary
MINT = "#39FF88"   # accent, prompt
BRIGHT = "#F2FFF8" # primary text
MUTED = "#5B6B63"  # captions, labels

# Difficulty colours double as the terminal traffic-light trio, so they read as
# part of this world rather than as three arbitrary new hues.
EASY, MEDIUM, HARD = "#39FF88", "#FFC53D", "#FF5F56"

FONT = "ui-monospace,'SF Mono','JetBrains Mono',Menlo,Consolas,monospace"

# --------------------------------------------------------------- the rain ---
GLYPH_H = 16    # vertical distance between glyphs in a column
COL_W = 20      # horizontal distance between columns
TRAIL = 16      # glyphs per column before the pattern repeats
STRIP = TRAIL * GLYPH_H


def trail_opacity(i):
    """Bright head, then a long gentle decay.

    A steep falloff makes only the first few glyphs visible, so the field reads
    as scattered dashes; a shallow one keeps the whole column legible and it
    reads as a continuous falling stream.
    """
    if i == 0:
        return 1.0
    if i == 1:
        return 0.92
    if i == 2:
        return 0.82
    return max(0.12, 0.72 * (0.90 ** (i - 3)))


def trail_color(i):
    return (BRIGHT, "#9BFFC8", MINT, MINT)[i] if i < 4 else DIM


N_TEMPLATES = 10  # distinct digit sequences, reused across columns


def rain(width, height, seed, density=0.62, opacity=0.55, fade_edges=True):
    """A field of 0/1 columns on a strict grid — evenly spaced, never random x.

    Each column holds two stacked copies of its glyph strip and translates by
    exactly one strip height, so the loop is seamless with no visible reset.

    Columns reference one of a few <defs> templates rather than each carrying
    its own ~32 <text> nodes; at different speeds and phases the repetition is
    imperceptible, and it keeps these files at kilobytes instead of hundreds.
    """
    rng = random.Random(seed)

    defs = []
    for t in range(N_TEMPLATES):
        glyphs = []
        for copy in range(2):
            for i in range(TRAIL):
                y = copy * STRIP + i * GLYPH_H
                glyphs.append('<text y="%d" class="r%d">%d</text>'
                              % (y, i, rng.randint(0, 1)))
        # font set on the group, not per glyph: inherited by every child, and
        # kept off a global `text` rule that would outrank the presentation
        # attributes the hero and card type rely on.
        defs.append('<g id="k%d_%d" font-family="%s" font-size="13">%s</g>'
                    % (seed, t, FONT, "".join(glyphs)))

    cols = []
    for c in range(int(width // COL_W) + 1):
        if rng.random() > density:
            continue  # gaps keep it breathing instead of wall-to-wall
        cols.append(
            '<use href="#k%d_%d" class="c" x="%.0f" y="%d" '
            'style="animation-duration:%ss;animation-delay:%ss"/>'
            % (seed, rng.randrange(N_TEMPLATES), c * COL_W + COL_W / 2, -STRIP,
               round(rng.uniform(3.4, 8.2), 2), -round(rng.uniform(0, 8.2), 2))
        )

    mask = ' mask="url(#fade)"' if fade_edges else ""
    return ('<defs>%s</defs><g%s opacity="%s">%s</g>'
            % ("".join(defs), mask, opacity, "".join(cols)))


def rain_css():
    """Trail colour/opacity live in classes so they are not repeated per glyph."""
    rows = "".join(".r%d{fill:%s;fill-opacity:%.3f}" % (i, trail_color(i), trail_opacity(i))
                   for i in range(TRAIL))
    return ("@keyframes f{from{transform:translateY(0)}to{transform:translateY(%dpx)}}"
            ".c{animation-name:f;animation-timing-function:linear;"
            "animation-iteration-count:infinite}%s" % (STRIP, rows))


def vertical_fade(height, soft=0.18):
    """Rain dissolves into the page instead of ending on a hard edge."""
    return (
        '<linearGradient id="fg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%%" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="%d%%" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset="%d%%" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset="100%%" stop-color="#fff" stop-opacity="0"/>'
        '</linearGradient>'
        '<mask id="fade"><rect width="100%%" height="100%%" fill="url(#fg)"/></mask>'
        % (int(soft * 100), int((1 - soft) * 100))
    )


def svg_open(w, h, label):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d" role="img" aria-label="%s">' % (w, h, w, h, label))


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------- hero ---
HERO_W, HERO_H = 1200, 330
PROMPT = "$ "
TYPED = "Hello, I'm Vidhaan"
CAPTION = "high-school developer — I build things people actually use"


def typed_line(x, y, size, text, dur):
    """Char-by-char reveal via a stepped clip, with the cursor stepping in sync.

    textLength pins the run to an exact width so the cursor lands correctly no
    matter which monospace face the viewer's machine resolves.
    """
    cell = size * 0.6
    w = len(text) * cell
    steps = len(text)
    widths = ";".join("%.2f" % (w * i / steps) for i in range(steps + 1))
    xs = ";".join("%.2f" % (x + w * i / steps) for i in range(steps + 1))
    return (
        '<clipPath id="tc"><rect x="%.2f" y="%.2f" width="0" height="%.2f">'
        '<animate attributeName="width" values="%s" dur="%ss" '
        'calcMode="discrete" fill="freeze"/></rect></clipPath>'
        '<text clip-path="url(#tc)" x="%.2f" y="%.2f" fill="%s" font-family="%s" '
        'font-size="%d" font-weight="700" textLength="%.2f" lengthAdjust="spacing">%s</text>'
        '<rect y="%.2f" width="%.2f" height="%.2f" fill="%s" x="%.2f">'
        '<animate attributeName="x" values="%s" dur="%ss" calcMode="discrete" fill="freeze"/>'
        '<animate attributeName="opacity" values="1;0" dur="1s" begin="%ss" '
        'repeatCount="indefinite"/></rect>'
        % (x, y - size, size * 1.3, widths, dur,
           x, y, BRIGHT, FONT, size, w, esc(text),
           y - size * 0.76, size * 0.5, size * 0.9, BRIGHT, x,
           xs, dur, dur)
    )


def build_hero():
    pw, ph = 1080, 210          # terminal window
    px, py = (HERO_W - pw) / 2, 62
    size = 34
    cell = size * 0.6
    total = (len(PROMPT) + len(TYPED)) * cell
    tx = px + (pw - total) / 2
    ty = py + 118

    return (
        svg_open(HERO_W, HERO_H, "Hello, I'm Vidhaan — high-school developer")
        + "<style>%s</style>" % rain_css()
        + "<defs>%s</defs>" % vertical_fade(HERO_H, 0.14)
        + '<rect width="%d" height="%d" fill="%s"/>' % (HERO_W, HERO_H, VOID)
        + rain(HERO_W, HERO_H, seed=11, density=0.85, opacity=0.55)
        # terminal floats on the field; near-opaque so the rain never fights text
        + '<rect x="%.1f" y="%.1f" width="%d" height="%d" rx="10" fill="%s" '
          'fill-opacity="0.96" stroke="%s"/>' % (px, py, pw, ph, PANEL, LINE)
        + '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>'
          % (px, py + 34, px + pw, py + 34, LINE)
        + "".join('<circle cx="%.1f" cy="%.1f" r="4.5" fill="none" stroke="%s"/>'
                  % (px + 22 + i * 19, py + 17, MUTED) for i in range(3))
        + '<text x="%.1f" y="%.1f" text-anchor="middle" fill="%s" font-family="%s" '
          'font-size="12" letter-spacing="1">guest@vidhaan:~</text>'
          % (px + pw / 2, py + 21, MUTED, FONT)
        + '<text x="%.1f" y="%.1f" fill="%s" font-family="%s" font-size="%d" '
          'font-weight="700">%s</text>' % (tx, ty, DIM, FONT, size, PROMPT.strip())
        + typed_line(tx + len(PROMPT) * cell, ty, size, TYPED, 1.8)
        + '<text x="%.1f" y="%.1f" text-anchor="middle" fill="%s" font-family="%s" '
          'font-size="15" opacity="0"><animate attributeName="opacity" values="0;1" '
          'dur="0.6s" begin="2.0s" fill="freeze"/>%s</text>'
          % (px + pw / 2, py + 168, MUTED, FONT, esc(CAPTION))
        + "</svg>"
    )


# ------------------------------------------------------------------ about ---
# Commands type out; their output prints at once. That is how a real terminal
# behaves, and it keeps one authored moment instead of eight scattered ones.
# Labels sit in their own column rather than being padded with spaces: SVG
# collapses runs of whitespace, so padded text would not stay aligned.
SESSION = [
    ("cmd", "whoami", None),
    ("out", "", "vidhaan — 16, building software that solves problems I actually have"),
    ("gap", None, None),
    ("cmd", "cat now.txt", None),
    ("out", "building", "Velo — push-to-talk voice dictation for macOS, open source"),
    ("out", "shipping", "BasisRide — carpool matching for families at my school"),
    ("out", "learning", "how models work underneath, and how to put them in apps"),
    ("out", "competing", "ACSL — 39/40 at Nationals, 3/3 this Summer League"),
    ("out", "offline", "PADI scuba certified since I was 10"),
]
LABEL_W = 108  # x-offset of the value column, from the panel's text gutter

ABOUT_W = 1200
ROW_H = 30


def build_about():
    rows = [r for r in SESSION]
    ph = 78 + len(rows) * ROW_H + 34
    px, pw = 60, ABOUT_W - 120
    py = 26
    h = ph + 52

    body, t, y = [], 0.0, py + 74
    for row in rows:
        if row[0] == "gap":
            y += ROW_H
            continue
        if row[0] == "cmd":
            text = row[1]
            dur = max(0.45, len(text) * 0.045)
            body.append(
                '<text x="%d" y="%.1f" fill="%s" font-family="%s" font-size="15" '
                'font-weight="700" opacity="0"><animate attributeName="opacity" '
                'values="0;1" dur="0.01s" begin="%.2fs" fill="freeze"/>$</text>'
                % (px + 28, y, DIM, FONT, t)
            )
            body.append(_type_run(px + 28 + 16, y, 15, text, dur, t))
            t += dur + 0.28
        else:
            _, label, text = row
            reveal = ('<animate attributeName="opacity" values="0;1" dur="0.18s" '
                      'begin="%.2fs" fill="freeze"/>' % t)
            if label:
                body.append(
                    '<text x="%d" y="%.1f" fill="%s" font-family="%s" font-size="15" '
                    'opacity="0">%s%s</text>'
                    % (px + 28, y, MINT, FONT, reveal, esc(label))
                )
            body.append(
                '<text x="%d" y="%.1f" fill="%s" font-family="%s" font-size="15" '
                'opacity="0">%s%s</text>'
                % (px + 28 + (LABEL_W if label else 0), y,
                   BRIGHT if label else MUTED, FONT, reveal, esc(text))
            )
            t += 0.13
        y += ROW_H

    # resting prompt, blinking once the session finishes
    body.append(
        '<text x="%d" y="%.1f" fill="%s" font-family="%s" font-size="15" '
        'font-weight="700" opacity="0"><animate attributeName="opacity" values="0;1" '
        'dur="0.01s" begin="%.2fs" fill="freeze"/>$</text>' % (px + 28, y + 6, DIM, FONT, t)
    )
    body.append(
        '<rect x="%d" y="%.1f" width="8" height="15" fill="%s" opacity="0">'
        '<animate attributeName="opacity" values="1;0" dur="1s" begin="%.2fs" '
        'repeatCount="indefinite"/></rect>' % (px + 46, y - 6, BRIGHT, t + 0.1)
    )

    label = "Terminal session: whoami and cat now.txt — " + "; ".join(
        ("%s: %s" % (r[1], r[2])) if r[1] else r[2]
        for r in rows if r[0] == "out")
    return (
        svg_open(ABOUT_W, h, esc(label))
        + "<style>%s</style>" % rain_css()
        + "<defs>%s</defs>" % vertical_fade(h, 0.12)
        + '<rect width="%d" height="%d" fill="%s"/>' % (ABOUT_W, h, VOID)
        + rain(ABOUT_W, h, seed=29, density=0.8, opacity=0.42)
        + '<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="%s" '
          'fill-opacity="0.96" stroke="%s"/>' % (px, py, pw, ph, PANEL, LINE)
        + '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s"/>'
          % (px, py + 34, px + pw, py + 34, LINE)
        + "".join('<circle cx="%d" cy="%d" r="4.5" fill="none" stroke="%s"/>'
                  % (px + 22 + i * 19, py + 17, MUTED) for i in range(3))
        + '<text x="%d" y="%d" text-anchor="middle" fill="%s" font-family="%s" '
          'font-size="12" letter-spacing="1">guest@vidhaan:~</text>'
          % (px + pw / 2, py + 21, MUTED, FONT)
        + "".join(body)
        + "</svg>"
    )


_uid = [0]


def _type_run(x, y, size, text, dur, begin):
    """Stepped char reveal for the about panel (no cursor; the prompt owns it)."""
    cell = size * 0.6
    w = len(text) * cell
    steps = max(1, len(text))
    widths = ";".join("%.2f" % (w * i / steps) for i in range(steps + 1))
    # a counter, not hash(): PYTHONHASHSEED randomisation would change these ids
    # every run and make the daily workflow commit churn
    _uid[0] += 1
    cid = "t%d" % _uid[0]
    return (
        '<clipPath id="%s"><rect x="%.2f" y="%.2f" width="0" height="%.2f">'
        '<animate attributeName="width" values="%s" dur="%.2fs" begin="%.2fs" '
        'calcMode="discrete" fill="freeze"/></rect></clipPath>'
        '<text clip-path="url(#%s)" x="%.2f" y="%.2f" fill="%s" font-family="%s" '
        'font-size="%d" font-weight="700" textLength="%.2f" lengthAdjust="spacing">%s</text>'
        % (cid, x, y - size, size * 1.35, widths, dur, begin,
           cid, x, y, BRIGHT, FONT, size, w, esc(text))
    )


# ---------------------------------------------------------------- divider ---
def build_divider(seed):
    w, h = 1200, 72
    return (
        svg_open(w, h, "")
        + "<style>%s</style>" % rain_css()
        + "<defs>%s</defs>" % vertical_fade(h, 0.22)
        + '<rect width="%d" height="%d" fill="%s"/>' % (w, h, VOID)
        + rain(w, h, seed=seed, density=0.8, opacity=0.7)
        + "</svg>"
    )


# --------------------------------------------------------------- leetcode ---
LC_W, LC_H = 500, 200


QUERY = ("query u($u:String!){allQuestionsCount{difficulty count}"
         "matchedUser(username:$u){submitStatsGlobal{acSubmissionNum"
         "{difficulty count}}}}")


def fetch_leetcode(user="vidhaan_j"):
    payload = json.dumps({"query": QUERY, "variables": {"u": user}})
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(
            "https://leetcode.com/graphql", data=payload.encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = json.load(r)
    except Exception:
        # Python builds without a CA bundle (common on macOS python.org installs)
        # can't do TLS; curl carries the system trust store.
        out = subprocess.run(
            ["curl", "-sS", "-X", "POST", "https://leetcode.com/graphql",
             "-H", "Content-Type: application/json",
             "-H", "User-Agent: Mozilla/5.0", "-d", payload],
            capture_output=True, text=True, timeout=30, check=True)
        raw = json.loads(out.stdout)

    d = raw["data"]
    total = {x["difficulty"]: x["count"] for x in d["allQuestionsCount"]}
    soln = {x["difficulty"]: x["count"]
            for x in d["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"]}
    if not soln.get("All"):
        raise ValueError("no solved counts returned for %s" % user)
    return {"user": user, "solved": soln, "total": total}


def build_leetcode(data):
    s, t = data["solved"], data["total"]
    px, py, pw, ph = 1, 1, LC_W - 2, LC_H - 2
    rows = [("easy", EASY, s.get("Easy", 0), t.get("Easy", 1)),
            ("medium", MEDIUM, s.get("Medium", 0), t.get("Medium", 1)),
            ("hard", HARD, s.get("Hard", 0), t.get("Hard", 1))]

    body = [
        '<text x="24" y="34" fill="%s" font-family="%s" font-size="13" '
        'font-weight="700">$ leetcode --stats</text>' % (DIM, FONT),
        '<text x="%d" y="34" text-anchor="end" fill="%s" font-family="%s" '
        'font-size="12">%s</text>' % (LC_W - 24, MUTED, FONT, data["user"]),
        '<text x="24" y="76" fill="%s" font-family="%s" font-size="34" '
        'font-weight="700">%d</text>' % (BRIGHT, FONT, s.get("All", 0)),
        '<text x="%d" y="76" fill="%s" font-family="%s" font-size="13">solved</text>'
        % (34 + len(str(s.get("All", 0))) * 21, MUTED, FONT),
    ]

    # Bars fill left-to-right on load — the one moment of motion on this card.
    bx, bw = 150, LC_W - 150 - 24
    for i, (name, colour, got, tot) in enumerate(rows):
        y = 116 + i * 30
        pct = got / tot if tot else 0
        body.append('<text x="24" y="%d" fill="%s" font-family="%s" font-size="13">%s</text>'
                    % (y + 10, colour, FONT, name))
        body.append('<text x="140" y="%d" text-anchor="end" fill="%s" font-family="%s" '
                    'font-size="13">%d</text>' % (y + 10, BRIGHT, FONT, got))
        body.append('<rect x="%d" y="%d" width="%d" height="6" rx="3" fill="%s" '
                    'fill-opacity="0.25"/>' % (bx, y + 2, bw, colour))
        body.append(
            '<rect x="%d" y="%d" width="0" height="6" rx="3" fill="%s">'
            '<animate attributeName="width" values="0;%.1f" dur="0.9s" begin="%.2fs" '
            'fill="freeze" calcMode="spline" keySplines="0.16 1 0.3 1" keyTimes="0;1"/>'
            '</rect>' % (bx, y + 2, colour, bw * pct, 0.25 + i * 0.12)
        )
        body.append('<text x="%d" y="%d" text-anchor="end" fill="%s" font-family="%s" '
                    'font-size="11">%d%%</text>' % (LC_W - 24, y + 26, MUTED, FONT,
                                                    round(pct * 100)))

    label = "LeetCode: %d solved — %s" % (
        s.get("All", 0),
        ", ".join("%d %s" % (r[2], r[0]) for r in rows))
    return (
        svg_open(LC_W, LC_H, label)
        + '<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="%s" stroke="%s"/>'
          % (px, py, pw, ph, VOID, LINE)
        + "".join(body)
        + "</svg>"
    )


# ------------------------------------------------------------------- main ---
def write(name, content):
    path = os.path.join(HERE, name)
    with open(path, "w") as f:
        f.write(content + "\n")
    print("%-18s %6d bytes" % (name, len(content)))


def main():
    cache = os.path.join(HERE, "leetcode.json")
    if "--offline" in sys.argv:
        data = json.load(open(cache))
    else:
        try:
            data = fetch_leetcode()
            json.dump(data, open(cache, "w"), indent=2, sort_keys=True)
        except Exception as e:                      # network down / API changed
            print("leetcode fetch failed (%s); using cache" % e, file=sys.stderr)
            data = json.load(open(cache))

    write("hero.svg", build_hero())
    write("about.svg", build_about())
    write("rain-a.svg", build_divider(seed=3))
    write("rain-b.svg", build_divider(seed=17))
    write("leetcode.svg", build_leetcode(data))


if __name__ == "__main__":
    main()
