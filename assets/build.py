#!/usr/bin/env python3
"""Regenerate every SVG in assets/. Pure stdlib, no deps.

    python3 assets/build.py            # rebuild, fetching live stats
    python3 assets/build.py --offline  # rebuild from assets/*.json caches

Output is deterministic (fixed RNG seeds), so re-running with unchanged data
produces byte-identical files and the daily workflow makes no noise commits.
"""
import datetime
import json
import math
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
# the streak card this sits beside declares exactly this stack
SANS = "'Segoe UI',Ubuntu,sans-serif"

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


# Every reveal animates *from* a hidden state into the element's own natural
# one, with fill-mode backwards. The resting state is therefore fully legible,
# so a renderer that ignores the animation — reduced motion, GitHub's mobile
# app, any static rasteriser — still shows all of the content. Starting at
# opacity 0 and animating up would make the motion load-bearing for legibility.
REVEAL_CSS = (
    # Per-character reveal rides on fill-opacity, not on a clip: CSS cannot
    # animate the geometry of a rect inside <clipPath>, which silently left the
    # text unclipped while the caret marched correctly across it.
    "@keyframes rvf{from{fill-opacity:0}}"
    "@keyframes caret{from{transform:translateX(var(--w))}}"
    "@keyframes rv{from{opacity:0}}"
    "@keyframes blink{50%{opacity:0}}"
    "@keyframes gone{to{opacity:0}}"
    ".ch{animation:rvf .01s step-end backwards}"
    ".caret{animation-name:caret;animation-fill-mode:backwards}"
    ".rv{animation:rv .18s backwards}"
    ".blink{animation:blink 1s step-end infinite backwards}"
    # a finished command hands its caret to the next line, the way a real
    # terminal keeps exactly one
    ".gone{animation:gone .01s step-end forwards}"
    "@media(prefers-reduced-motion:reduce){"
    ".c,.ch,.caret,.rv,.blink,.gone{animation:none}}"
)


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
CAPTION = "full stack developer"


def typed_line(x, y, size, text, dur, begin=0.0, cid="tc", persist=True):
    """Char-by-char reveal via a stepped clip, with the caret stepping in sync.

    Resting state is the finished line: the clip is full width and the caret
    sits at the end, so this degrades to plain readable text.

    textLength pins the run to an exact width so the caret lands correctly no
    matter which monospace face the viewer's machine resolves.
    """
    cell = size * 0.6
    w = len(text) * cell
    n = len(text)

    # textLength distributes the run across the tspans, so spacing stays exact
    # whichever monospace face resolves; each tspan just fades itself in.
    spans = "".join(
        '<tspan class="ch" style="animation-delay:%.3fs">%s</tspan>'
        % (begin + i * dur / n, esc(ch).replace(" ", "&#160;"))
        for i, ch in enumerate(text)
    )
    caret = ('<rect class="blink" style="animation-delay:%ss" x="%.2f" y="%.2f" '
             'width="%.2f" height="%.2f" fill="%s"/>'
             % (begin + dur, x + w, y - size * 0.76, size * 0.5, size * 0.9, BRIGHT))
    if not persist:
        caret = ('<g class="gone" style="animation-delay:%ss">%s</g>'
                 % (begin + dur + 0.2, caret))
    return (
        '<text x="%.2f" y="%.2f" fill="%s" font-family="%s" font-size="%d" '
        'font-weight="700" textLength="%.2f" lengthAdjust="spacing" '
        'xml:space="preserve">%s</text>'
        '<g class="caret" style="--w:-%.2fpx;animation-duration:%ss;'
        'animation-delay:%ss;animation-timing-function:steps(%d,end)">%s</g>'
        % (x, y, BRIGHT, FONT, size, w, spans, w, dur, begin, n, caret)
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
        svg_open(HERO_W, HERO_H, "Hello, I'm Vidhaan — %s" % CAPTION)
        + "<style>%s%s</style>" % (rain_css(), REVEAL_CSS)
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
        + '<text class="rv" style="animation-duration:.6s;animation-delay:2s" '
          'x="%.1f" y="%.1f" text-anchor="middle" fill="%s" font-family="%s" '
          'font-size="16">%s</text>'
          % (px + pw / 2, py + 168, MUTED, FONT, esc(CAPTION))
        + "</svg>"
    )


# ------------------------------------------------------------------ about ---
# Commands type out; their output prints at once. That is how a real terminal
# behaves, and it keeps one authored moment instead of eight scattered ones.
SESSION = [
    ("cmd", "whoami"),
    ("gap", None),
    ("out", "I'm currently working on Velo, a push-to-talk open-source clone of WisprFlow."),
    ("out", "I'm looking to collaborate on getting Ridr into more carpool groups at my school."),
    ("out", "I'm currently learning how AI works under the hood and how to integrate AI in my own apps."),
    ("out", "Ask me about training for ACSL; I scored 39/40 at Nationals and scored 3/3 in this year's Summer League."),
    ("out", "Fun fact: I earned my PADI Scuba Diving License when I was 10 years old!"),
]

# Wide enough for the longest line to sit on one row without wrapping.
ABOUT_W = 1120
ROW_H = 32


def build_about():
    rows = [r for r in SESSION]
    ph = 78 + len(rows) * ROW_H + 34
    px, pw = 40, ABOUT_W - 80
    py = 26
    h = ph + 52

    body, t, y = [], 0.0, py + 74
    for row in rows:
        if row[0] == "gap":
            y += ROW_H
            continue
        if row[0] == "cmd":
            text = row[1]
            dur = max(0.45, len(text) * 0.055)
            body.append(
                '<text class="rv" style="animation-delay:%.2fs" x="%d" y="%.1f" '
                'fill="%s" font-family="%s" font-size="15" font-weight="700">$</text>'
                % (t, px + 28, y, DIM, FONT)
            )
            _uid[0] += 1
            body.append(typed_line(px + 28 + 16, y, 15, text, dur,
                                   begin=t, cid="c%d" % _uid[0], persist=False))
            t += dur + 0.3
        else:
            body.append(
                '<text class="rv" style="animation-delay:%.2fs" x="%d" y="%.1f" '
                'fill="%s" font-family="%s" font-size="15">%s</text>'
                % (t, px + 28, y, BRIGHT, FONT, esc(row[1]))
            )
            t += 0.16
        y += ROW_H

    # resting prompt, blinking once the session finishes
    body.append(
        '<text class="rv" style="animation-delay:%.2fs" x="%d" y="%.1f" fill="%s" '
        'font-family="%s" font-size="16" font-weight="700">$</text>'
        % (t, px + 28, y + 6, DIM, FONT)
    )
    body.append(
        '<g class="rv" style="animation-delay:%.2fs">'
        '<rect class="blink" style="animation-delay:%.2fs" x="%d" y="%.1f" width="8" '
        'height="16" fill="%s"/></g>' % (t, t + 0.1, px + 46, y - 6, BRIGHT)
    )

    label = "whoami — " + " ".join(r[1] for r in rows if r[0] == "out")
    return (
        svg_open(ABOUT_W, h, esc(label))
        + "<style>%s%s</style>" % (rain_css(), REVEAL_CSS)
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
LC_W, LC_H = 495, 195   # identical to the streak card beside it


QUERY = ("query u($u:String!){allQuestionsCount{difficulty count}"
         "matchedUser(username:$u){submitStatsGlobal{acSubmissionNum"
         "{difficulty count}}}"
         # attempted-but-unsolved, the "Attempting" figure on the ring
         "userProfileUserQuestionProgressV2(userSlug:$u){"
         "numFailedQuestions{count difficulty}}}")


def _post_json(url, payload, headers, timeout=20):
    """POST JSON and parse the JSON response, falling back to curl.

    Python builds without a CA bundle (common on macOS python.org installs)
    can't do TLS; curl carries the system trust store.
    """
    body = json.dumps(payload)
    try:
        req = urllib.request.Request(url, data=body.encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        cmd = ["curl", "-sS", "-X", "POST", url]
        for k, v in headers.items():
            cmd += ["-H", "%s: %s" % (k, v)]
        cmd += ["-d", body]
        out = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout + 10, check=True)
        return json.loads(out.stdout)


def fetch_leetcode(user="vidhaan_j"):
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    raw = _post_json("https://leetcode.com/graphql",
                      {"query": QUERY, "variables": {"u": user}}, headers)

    d = raw["data"]
    total = {x["difficulty"]: x["count"] for x in d["allQuestionsCount"]}
    soln = {x["difficulty"]: x["count"]
            for x in d["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"]}
    if not soln.get("All"):
        raise ValueError("no solved counts returned for %s" % user)
    progress = d.get("userProfileUserQuestionProgressV2") or {}
    attempting = sum(x["count"] for x in progress.get("numFailedQuestions") or [])
    return {"user": user, "solved": soln, "total": total, "attempting": attempting}


def _arc(cx, cy, r, a0, a1):
    """Path for an arc, angles in degrees clockwise from 12 o'clock."""
    def pt(a):
        rad = math.radians(a)
        return cx + r * math.sin(rad), cy - r * math.cos(rad)
    x0, y0 = pt(a0)
    x1, y1 = pt(a1)
    large = 1 if abs(a1 - a0) > 180 else 0
    return "M %.2f %.2f A %.2f %.2f 0 %d 1 %.2f %.2f" % (x0, y0, r, r, large, x1, y1)


def build_leetcode(data):
    """LeetCode's own progress ring: one arc per difficulty, sized by how much
    of the catalogue that difficulty is, filled by how much of it is solved.
    Rendered in this page's palette and mono type so it reads as a sibling of
    the streak card rather than as a transplant from another site.
    """
    s, t, att = data["solved"], data["total"], data.get("attempting", 0)
    diffs = [("Easy", EASY, s.get("Easy", 0), t.get("Easy", 1)),
             ("Medium", MEDIUM, s.get("Medium", 0), t.get("Medium", 1)),
             ("Hard", HARD, s.get("Hard", 0), t.get("Hard", 1))]

    cx, cy, r = 139, 95, 62
    span, pad = 270.0, 2.0          # 270° of ring, small gap between segments
    catalogue = sum(d[3] for d in diffs) or 1

    body, a = [], -135.0
    for i, (name, colour, got, tot) in enumerate(diffs):
        seg = span * tot / catalogue
        a0, a1 = a + pad / 2, a + seg - pad / 2
        body.append('<path d="%s" fill="none" stroke="%s" stroke-opacity="0.2" '
                    'stroke-width="8" stroke-linecap="round"/>'
                    % (_arc(cx, cy, r, a0, a1), colour))
        if got:
            body.append(
                '<path class="arc" style="animation-delay:%.2fs" pathLength="100" '
                'd="%s" fill="none" stroke="%s" stroke-width="8" '
                'stroke-linecap="round"/>'
                % (0.15 + i * 0.12,
                   _arc(cx, cy, r, a0, a0 + (a1 - a0) * got / tot), colour))
        a += seg

    solved, whole = s.get("All", 0), t.get("All", 0)
    # Centred with text-anchor and tspans rather than measured offsets: the
    # neighbouring card's face is proportional, so per-character width maths
    # no longer holds.
    body.append(
        '<g class="rv" style="animation-duration:.5s;animation-delay:.45s">'
        '<text x="%d" y="105" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="28" font-weight="700">%s'
        '<tspan font-size="13" font-weight="400" fill="%s">/%s</tspan></text>'
        '<text x="%d" y="129" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="14" font-weight="700">Solved</text></g>'
        % (cx, BRIGHT, SANS, "{:,}".format(solved), MUTED, whole,
           cx, MINT, SANS)
    )
    if att:
        body.append(
            '<g class="rv" style="animation-duration:.5s;animation-delay:.55s">'
            '<text x="%d" y="152" text-anchor="middle" fill="%s" font-family="%s" '
            'font-size="12"><tspan font-weight="700" fill="%s">%d</tspan>'
            '&#160;Attempting</text></g>'   # nbsp: SVG would collapse a plain space
            % (cx, MUTED, SANS, BRIGHT, att)
        )

    body.append('<line x1="278" y1="32" x2="278" y2="163" stroke="%s" '
                'stroke-width="1.2"/>' % MINT)

    # 52px pitch between entries, matching the airiness of the neighbouring
    # card rather than stacking three pairs of lines tightly.
    for i, (name, colour, got, tot) in enumerate(diffs):
        body.append(
            '<g class="rv" style="animation-duration:.5s;animation-delay:%.2fs">'
            '<text x="386" y="%d" text-anchor="middle" fill="%s" font-family="%s" '
            'font-size="20" font-weight="700">%d/%d</text>'
            '<text x="386" y="%d" text-anchor="middle" fill="%s" font-family="%s" '
            'font-size="13">%s</text></g>'
            % (0.2 + i * 0.09,
               42 + i * 52, BRIGHT, SANS, got, tot,
               61 + i * 52, colour, SANS, name)
        )

    label = "LeetCode — %d of %d solved (%d attempting): %s" % (
        solved, whole, att,
        ", ".join("%d of %d %s" % (d[2], d[3], d[0].lower()) for d in diffs))
    return (
        svg_open(LC_W, LC_H, label)
        + "<style>%s@keyframes draw{from{stroke-dashoffset:100}}"
          ".arc{stroke-dasharray:100;animation:draw .9s cubic-bezier(.16,1,.3,1) "
          "backwards}@media(prefers-reduced-motion:reduce){.arc{animation:none}}"
          "</style>" % REVEAL_CSS
        + '<rect x="1" y="1" width="%d" height="%d" rx="10" fill="%s" stroke="%s"/>'
          % (LC_W - 2, LC_H - 2, VOID, LINE)
        + "".join(body)
        + "</svg>"
    )


# ----------------------------------------------------------------- streak ---
# Built locally instead of embedding streak-stats.demolab.com: that's a public
# shared instance proxying GitHub's own API, and it eats the same 60-req/hour
# unauthenticated rate limit as every other profile using it — so it goes
# down at random and renders an error card in place of the real one. Fetching
# with our own token (5,000 req/hour) and drawing the card ourselves, the
# same way leetcode.svg already is, removes that shared point of failure.
# Card size and column layout match streak-stats.demolab.com's own output —
# this card already declared itself "identical to the streak card beside it"
# (see LC_W/LC_H above) back when it sat next to that service's version.
GITHUB_USER = "realvidhaan"

STREAK_QUERY = (
    "query($l:String!,$from:DateTime!,$to:DateTime!){user(login:$l){"
    "contributionsCollection(from:$from,to:$to){contributionCalendar{"
    "weeks{contributionDays{date contributionCount}}}}}}"
)


def fetch_streak(user, token):
    """Pull the full daily contribution history and reduce it to the three
    numbers the card shows. contributionsCollection caps each query's span at
    a year, so history is walked in yearly windows from account creation.
    """
    headers = {"Authorization": "bearer %s" % token,
               "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

    created_raw = _post_json(
        "https://api.github.com/graphql",
        {"query": "query($l:String!){user(login:$l){createdAt}}",
         "variables": {"l": user}}, headers)
    if created_raw.get("errors"):
        raise ValueError(created_raw["errors"])
    created = datetime.date.fromisoformat(created_raw["data"]["user"]["createdAt"][:10])
    today = datetime.datetime.now(datetime.timezone.utc).date()

    days = {}
    cursor = created
    while cursor <= today:
        window_end = min(cursor + datetime.timedelta(days=365),
                          today + datetime.timedelta(days=1))
        variables = {"l": user, "from": cursor.strftime("%Y-%m-%dT00:00:00Z"),
                     "to": window_end.strftime("%Y-%m-%dT00:00:00Z")}
        raw = _post_json("https://api.github.com/graphql",
                          {"query": STREAK_QUERY, "variables": variables}, headers)
        if raw.get("errors"):
            raise ValueError(raw["errors"])
        weeks = raw["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for w in weeks:
            for d in w["contributionDays"]:
                date = datetime.date.fromisoformat(d["date"])
                if created <= date <= today:
                    days[date] = d["contributionCount"]
        cursor = window_end

    return _streak_stats(user, created, today, days)


def _streak_stats(user, created, today, days):
    """A day with zero contributions only breaks the current streak if it
    isn't today — today's count can still rise before the day is over.
    """
    ordered = sorted(days)
    total = sum(days.values())

    longest, run, run_start = 0, 0, None
    longest_start = longest_end = today
    for d in ordered:
        if days[d] > 0:
            if run == 0:
                run_start = d
            run += 1
            if run > longest:
                longest, longest_start, longest_end = run, run_start, d
        else:
            run = 0

    current, i = 0, len(ordered) - 1
    if i >= 0 and days[ordered[i]] == 0:
        i -= 1
    current_end = ordered[-1] if ordered else today
    while i >= 0 and days[ordered[i]] > 0:
        current += 1
        i -= 1
    current_start = ordered[i + 1] if current else current_end

    return {
        "user": user, "total": total, "total_start": created.isoformat(),
        "current": current, "current_start": current_start.isoformat(),
        "current_end": current_end.isoformat(),
        "longest": longest, "longest_start": longest_start.isoformat(),
        "longest_end": longest_end.isoformat(),
    }


def _fmt(iso, fmt):
    return datetime.date.fromisoformat(iso).strftime(fmt)


# The flame glyph streak-stats.demolab.com draws next to the current-streak
# ring; kept identical so the card reads as a continuation of the same widget
# rather than a redesign.
FIRE_PATH = (
    "M 1.5 0.67 C 1.5 0.67 2.24 3.32 2.24 5.47 C 2.24 7.53 0.89 9.2 -1.17 9.2 "
    "C -3.23 9.2 -4.79 7.53 -4.79 5.47 L -4.76 5.11 C -6.78 7.51 -8 10.62 -8 13.99 "
    "C -8 18.41 -4.42 22 0 22 C 4.42 22 8 18.41 8 13.99 C 8 8.6 5.41 3.79 1.5 0.67 Z "
    "M -0.29 19 C -2.07 19 -3.51 17.6 -3.51 15.86 C -3.51 14.24 -2.46 13.1 -0.7 12.74 "
    "C 1.07 12.38 2.9 11.53 3.92 10.16 C 4.31 11.45 4.51 12.81 4.51 14.2 "
    "C 4.51 16.85 2.36 19 -0.29 19 Z"
)


def build_streak(data):
    total, current, longest = data["total"], data["current"], data["longest"]
    total_range = "%s - Present" % _fmt(data["total_start"], "%b %-d, %Y")
    current_range = "%s - %s" % (_fmt(data["current_start"], "%b %-d"),
                                  _fmt(data["current_end"], "%b %-d"))
    longest_range = "%s - %s" % (_fmt(data["longest_start"], "%b %-d"),
                                  _fmt(data["longest_end"], "%b %-d"))

    body = [
        '<line x1="165" y1="28" x2="165" y2="170" stroke="%s"/>' % LINE,
        '<line x1="330" y1="28" x2="330" y2="170" stroke="%s"/>' % LINE,
        # total contributions (left column)
        '<g class="rv" style="animation-duration:.5s;animation-delay:.15s">'
        '<text x="82.5" y="80" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="28" font-weight="700">%s</text>'
        '<text x="82.5" y="116" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="14">Total Contributions</text>'
        '<text x="82.5" y="146" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="12">%s</text></g>'
        % (BRIGHT, SANS, "{:,}".format(total), MUTED, SANS, MUTED, SANS, esc(total_range)),
        # ring + fire behind the current-streak number (middle column)
        '<mask id="streakring"><rect width="%d" height="%d" fill="#fff"/>'
        '<ellipse cx="247.5" cy="32" rx="13" ry="18"/></mask>' % (LC_W, LC_H),
        '<g mask="url(#streakring)"><circle cx="247.5" cy="71" r="40" fill="none" '
        'stroke="%s" stroke-width="5" class="rv" style="animation-duration:.5s;'
        'animation-delay:.05s"/></g>' % MINT,
        '<g transform="translate(247.5,19.5)" class="rv" '
        'style="animation-duration:.5s;animation-delay:.25s">'
        '<path d="%s" fill="%s"/></g>' % (FIRE_PATH, MINT),
        '<text x="247.5" y="80" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="28" font-weight="700" class="rv" style="animation-duration:.6s;'
        'animation-delay:.35s">%d</text>'
        '<text x="247.5" y="140" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="14" font-weight="700" class="rv" style="animation-duration:.5s;'
        'animation-delay:.4s">Current Streak</text>'
        '<text x="247.5" y="166" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="12" class="rv" style="animation-duration:.5s;animation-delay:.4s">%s</text>'
        % (BRIGHT, SANS, current, MINT, SANS, MUTED, SANS, esc(current_range)),
        # longest streak (right column)
        '<g class="rv" style="animation-duration:.5s;animation-delay:.5s">'
        '<text x="412.5" y="80" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="28" font-weight="700">%d</text>'
        '<text x="412.5" y="116" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="14">Longest Streak</text>'
        '<text x="412.5" y="146" text-anchor="middle" fill="%s" font-family="%s" '
        'font-size="12">%s</text></g>'
        % (BRIGHT, SANS, longest, MUTED, SANS, MUTED, SANS, esc(longest_range)),
    ]

    label = "GitHub contribution streak — %d current, %d longest, %s total contributions" % (
        current, longest, "{:,}".format(total))
    return (
        svg_open(LC_W, LC_H, label)
        + "<style>%s</style>" % REVEAL_CSS
        + '<rect x="1" y="1" width="%d" height="%d" rx="10" fill="%s" stroke="%s"/>'
          % (LC_W - 2, LC_H - 2, VOID, LINE)
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
    offline = "--offline" in sys.argv

    lc_cache = os.path.join(HERE, "leetcode.json")
    if offline:
        lc_data = json.load(open(lc_cache))
    else:
        try:
            lc_data = fetch_leetcode()
            json.dump(lc_data, open(lc_cache, "w"), indent=2, sort_keys=True)
        except Exception as e:                      # network down / API changed
            print("leetcode fetch failed (%s); using cache" % e, file=sys.stderr)
            lc_data = json.load(open(lc_cache))

    streak_cache = os.path.join(HERE, "streak.json")
    token = os.environ.get("GITHUB_TOKEN")
    if offline or not token:
        if not offline:
            print("no GITHUB_TOKEN set; using cached streak stats", file=sys.stderr)
        streak_data = json.load(open(streak_cache))
    else:
        try:
            streak_data = fetch_streak(GITHUB_USER, token)
            json.dump(streak_data, open(streak_cache, "w"), indent=2, sort_keys=True)
        except Exception as e:                      # network down / API changed
            print("streak fetch failed (%s); using cache" % e, file=sys.stderr)
            streak_data = json.load(open(streak_cache))

    write("hero.svg", build_hero())
    write("about.svg", build_about())
    write("rain-a.svg", build_divider(seed=3))
    write("rain-b.svg", build_divider(seed=17))
    write("leetcode.svg", build_leetcode(lc_data))
    write("streak.svg", build_streak(streak_data))


if __name__ == "__main__":
    main()
