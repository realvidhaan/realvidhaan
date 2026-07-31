#!/usr/bin/env python3
"""Regenerate assets/header.svg. Pure stdlib, no deps. Edit the constants below and rerun."""
import random

random.seed(7)

WIDTH, HEIGHT = 1000, 300
BG = "#05070A"
PANEL_BORDER = "#0B3B24"
BRIGHT = "#F2FFF8"
MINT = "#39FF88"
MID = "#00B368"
MUTED = "#5B6B63"
FONT = "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace"

PROMPT = "$ "
TYPED = "Hello, I'm Vidhaan"
CAPTION = "full-stack dev — currently building Velo &amp; BasisRide"

FONT_SIZE = 30
CELL_W = FONT_SIZE * 0.6
TYPE_DURATION = 1.9

CHARSET = list("01010101010101010101" + "ABCDEF#$%")

RAIN_ROWS = 9
ROW_H = 15
UNIT_H = RAIN_ROWS * ROW_H
ROW_STYLES = [
    (BRIGHT, 0.90), (MINT, 0.78), (MINT, 0.60),
    (MID, 0.46), (MID, 0.34), (MID, 0.24),
    (MID, 0.15), (MID, 0.09), (MID, 0.05),
]

LEFT_COLS = [24, 42, 60, 78, 96, 114]
RIGHT_COLS = [886, 904, 922, 940, 958, 976]


def rain_column(x, idx):
    dur = round(random.uniform(2.6, 5.2), 2)
    delay = -round(random.uniform(0, dur), 2)
    rows = []
    for copy in range(2):
        for r in range(RAIN_ROWS):
            ch = random.choice(CHARSET)
            color, op = ROW_STYLES[r]
            y = copy * UNIT_H + r * ROW_H
            rows.append(
                f'<text x="0" y="{y}" fill="{color}" fill-opacity="{op}" '
                f'font-family="{FONT}" font-size="13">{ch}</text>'
            )
    return (
        f'<g class="rain-col" style="animation-duration:{dur}s;animation-delay:{delay}s" '
        f'transform="translate({x},0)">{"".join(rows)}</g>'
    )


def typed_chars(start_x, y):
    """Each character pops in via SMIL (not CSS clip-path — that never animates
    when this SVG is embedded via <img>, which is how GitHub renders it)."""
    step = TYPE_DURATION / len(TYPED)
    out = []
    for i, ch in enumerate(TYPED):
        x = start_x + i * CELL_W
        begin = round(i * step, 3)
        ch_display = "&#160;" if ch == " " else ch
        out.append(
            f'<text x="{x}" y="{y}" fill="{BRIGHT}" font-family="{FONT}" '
            f'font-size="{FONT_SIZE}" font-weight="700" opacity="0">{ch_display}'
            f'<animate attributeName="opacity" from="0" to="1" begin="{begin}s" '
            f'dur="0.01s" fill="freeze" /></text>'
        )
    return "".join(out)


def build():
    cols = [rain_column(x, i) for i, x in enumerate(LEFT_COLS + RIGHT_COLS)]

    prompt_w = len(PROMPT) * CELL_W
    typed_w = len(TYPED) * CELL_W
    total_w = prompt_w + typed_w
    start_x = (WIDTH - total_w) / 2
    text_y = 158
    cursor_x = start_x + prompt_w + typed_w + 4
    cursor_w = FONT_SIZE * 0.5
    cursor_h = FONT_SIZE * 0.85
    cursor_y = text_y - FONT_SIZE * 0.72

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Terminal greeting from Vidhaan">
  <style>
    @keyframes rain-fall {{ from {{ transform: translateY(0); }} to {{ transform: translateY({UNIT_H}px); }} }}
    .rain-col {{ animation-name: rain-fall; animation-timing-function: linear; animation-iteration-count: infinite; }}
  </style>

  <defs>
    <clipPath id="panel-clip"><rect x="2" y="2" width="{WIDTH - 4}" height="{HEIGHT - 4}" rx="14" /></clipPath>
    <linearGradient id="rain-fade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#fff" stop-opacity="1" />
      <stop offset="16%" stop-color="#fff" stop-opacity="1" />
      <stop offset="34%" stop-color="#fff" stop-opacity="0" />
      <stop offset="66%" stop-color="#fff" stop-opacity="0" />
      <stop offset="84%" stop-color="#fff" stop-opacity="1" />
      <stop offset="100%" stop-color="#fff" stop-opacity="1" />
    </linearGradient>
    <mask id="rain-mask"><rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="url(#rain-fade)" /></mask>
  </defs>

  <rect x="0.75" y="0.75" width="{WIDTH - 1.5}" height="{HEIGHT - 1.5}" rx="14" fill="{BG}" stroke="{PANEL_BORDER}" stroke-width="1.5" />

  <g clip-path="url(#panel-clip)">
    <g mask="url(#rain-mask)" opacity="0.65">{"".join(cols)}</g>

    <line x1="0" y1="34" x2="{WIDTH}" y2="34" stroke="{PANEL_BORDER}" stroke-opacity="0.6" />
    <circle cx="24" cy="17" r="5" fill="none" stroke="{MUTED}" stroke-width="1.3" />
    <circle cx="44" cy="17" r="5" fill="none" stroke="{MUTED}" stroke-width="1.3" />
    <circle cx="64" cy="17" r="5" fill="none" stroke="{MUTED}" stroke-width="1.3" />
    <text x="{WIDTH / 2}" y="21" text-anchor="middle" fill="{MUTED}" font-family="{FONT}" font-size="12" letter-spacing="1">guest@vidhaan:~</text>

    <text x="{start_x}" y="{text_y}" fill="{MID}" font-family="{FONT}" font-size="{FONT_SIZE}" font-weight="700">{PROMPT}</text>
    {typed_chars(start_x + prompt_w, text_y)}
    <rect x="{cursor_x}" y="{cursor_y}" width="{cursor_w}" height="{cursor_h}" fill="{BRIGHT}" opacity="0">
      <animate attributeName="opacity" values="1;0" dur="1s" begin="{TYPE_DURATION}s" repeatCount="indefinite" />
    </rect>

    <text x="{WIDTH / 2}" y="205" text-anchor="middle" fill="{MUTED}" font-family="{FONT}" font-size="15">{CAPTION}</text>
  </g>
</svg>
'''
    return svg


if __name__ == "__main__":
    out = build()
    with open(__file__.rsplit("/", 1)[0] + "/header.svg", "w") as f:
        f.write(out)
    print(f"wrote {len(out)} bytes")
