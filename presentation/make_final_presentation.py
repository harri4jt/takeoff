# ruff: noqa: E501  (embedded slide HTML)
"""Assemble final_presentation.pdf from the decks already reviewed, plus two new slides.

    python presentation/make_final_presentation.py

Each reused slide is rendered with its own deck's HTML and styles (so it looks exactly as
approved); only the footer text and page number are unified. Groups, in order:

1. slides.html (11/13): title, the problem, solution structure, safeguarded secant, RK4
2. update_1125_slides.html: 747-100 baseline, impact of wind
3. gust_slides.html: the gust model, from "wind as a random input" to the error slide
4. new: the data-uncertainty side study and a summary of the whole project

Needs Chrome (headless print to PDF) and pdfunite (poppler).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
FOOT_TEXT = "Harrison &amp; Seng · MATH 6006"
SECTION = re.compile(r'<section class="slide[^"]*">.*?</section>', re.S)
FOOT = re.compile(r'<div class="foot"><span>.*?</span><span>\d+</span></div>', re.S)


def _keep(html: str, keep: list[int], numbers: list[int | None], edits=()) -> str:
    """Keep the listed sections (in order of appearance), renumber their footers."""
    for a, b in edits:
        if a not in html:
            raise ValueError(f"edit target not found: {a[:60]!r}")
        html = html.replace(a, b)
    sections = SECTION.findall(html)
    kept = iter(zip(keep, numbers, strict=True))
    want = dict(kept)
    out, idx = [], 0

    def repl(m: re.Match) -> str:
        nonlocal idx
        i = idx
        idx += 1
        if i not in want:
            return ""
        sec = m.group(0)
        n = want[i]
        if n is not None:
            sec = FOOT.sub(f'<div class="foot"><span>{FOOT_TEXT}</span><span>{n}</span></div>', sec)
        out.append(i)
        return sec

    html = SECTION.sub(repl, html)
    if len(out) != len(keep) or len(sections) < max(keep) + 1:
        raise ValueError("section selection failed")
    return html


PROBLEM_RIGHT_OLD = re.compile(r'<div class="panel plan">.*?</div>\s*</div>\s*</div>\s*<div class="strip"', re.S)
PROBLEM_RIGHT_NEW = """<div class="panel plan q">
        <h3>The question</h3>
        <ul>
          <li>Given lift, drag and thrust tables, weight and weather: find V1 and the BFL</li>
          <li>FAR Part 25 field length = max(BFL, 1.15 × all-engines distance to 35 ft)</li>
        </ul>
      </div>
      <div class="panel changes">
        <h3>This talk</h3>
        <ol>
          <li><span class="n">1</span><div><div class="t">Solver recap: RK4, safeguarded secant</div></div></li>
          <li><span class="n">2</span><div><div class="t">Validation: Boeing 747-100</div></div></li>
          <li><span class="n">3</span><div><div class="t">Gusts: an SDE, solved by Monte Carlo</div></div></li>
          <li><span class="n">4</span><div><div class="t">Uncertain aero and thrust data</div></div></li>
        </ol>
      </div>
    </div>
  </div>
  <div class="strip\""""


def group1() -> str:
    html = (OUT / "slides.html").read_text()
    html = html.replace(
        "How much runway does a jet need if an engine can fail at the worst possible moment?",
        "How much runway does a jet need if an engine can fail at the worst moment, on a calm "
        "day and a gusty one?",
    )
    html, n = PROBLEM_RIGHT_OLD.subn(PROBLEM_RIGHT_NEW, html, count=1)
    if n != 1:
        raise ValueError("problem slide: right column not found")
    html = html.replace("</style>", "  .plan.q li::before { content: none; }\n  .plan.q li { font-size: 16.5px; }\n"
                        "  .changes li { margin: 6px 0; }\n  .changes .t { font-size: 17px; }\n</style>", 1)
    return _keep(html, [0, 1, 2, 3, 4], [None, 2, 3, 4, 5])


def group2() -> str:
    html = (OUT / "update_1125_slides.html").read_text()
    return _keep(html, [1, 5], [6, 7])


MC_OLD_TABLE = """        <tr><td>SR-71</td><td>+414 ft</td><td class="b">+1,044 ft</td><td>+2,075 ft</td></tr>
"""
MC_OLD_KEY = """      <div class="key">Moderate turbulence: +394 ft (4 %) for 95 % of 747 takeoffs. SR-71: +1,044 ft (9 %), little
        spare engine-out thrust.</div>"""
MC_NEW_KEY = """      <div class="key">Moderate turbulence: <b>+394 ft (4 %)</b> covers 95 % of 747-100 takeoffs; severe: +501 ft.</div>"""


def group3() -> str:
    html = (OUT / "gust_slides.html").read_text()
    edits = [(MC_OLD_TABLE, ""), (MC_OLD_KEY, MC_NEW_KEY)]
    return _keep(html, [1, 2, 3, 4, 5, 6, 7], [8, 9, 10, 11, 12, 13, 14], edits)


NEW_SLIDES = """
<section class="slide">
  <h2>Uncertainty modeling on aero and thrust data</h2>
  <div class="two" style="grid-template-columns: 620px 1fr; gap: 26px;">
    <div>
      <img class="fig" src="fig_unc_odds.svg" alt="chance a runway is enough, data uncertainty">
      <div class="cap">747-100 model, 500 Latin-hypercube draws</div>
    </div>
    <div>
      <div class="box" style="padding: 11px 16px; font-size: 15px; line-height: 1.45;">
        <div class="colhead">Why</div>
        In conceptual design, lift, drag and thrust come from models (handbook methods, CFD, engine decks) and carry
        uncertainty. This puts a runway cost on it.
      </div>
      <div class="box" style="padding: 11px 16px; font-size: 15px; line-height: 1.45; margin-top: 10px;">
        <div class="colhead">Method: Monte Carlo</div>
        Each draw scales the lift, drag and thrust tables by random factors from normal distributions with their own
        standard deviations (here 1σ: lift 4 %, drag 8 %, thrust 3 %), then runs a full solve.
      </div>
      <div class="key" style="margin-top: 10px; font-size: 15.5px; line-height: 1.45;">
        <ul class="tight" style="font-size: 15.5px; margin: 0;">
          <li><b>95 % confidence: 10,543 ft</b>, +1,020 ft (+11 %) over the nominal 9,523 ft.</li>
          <li>Lift drives the spread (56 %), then thrust (34 %). Drag adds only 9 %, though it is the least certain:
            for the same 5 % error, lift moves the runway ±590 ft, thrust ±620 ft, drag only ±120 ft.</li>
          <li>Data uncertainty costs about 2.5× the runway of moderate gusts (+394 ft).</li>
        </ul>
      </div>
    </div>
  </div>
  <div class="foot"><span>Harrison &amp; Seng · MATH 6006</span><span>15</span></div>
</section>

<section class="slide">
  <h2>Summary</h2>
  <div class="tiles3">
    <div class="tile"><span>calm day</span><b>9,523 ft</b><small>747-100 field length, within 5 % of Boeing</small></div>
    <div class="tile"><span>moderate gusts, 95 %</span><b>+394 ft</b><small>± 48 ft sampling, ± 4 ft time step</small></div>
    <div class="tile"><span>uncertain data, 95 %</span><b>+1,020 ft</b><small>1σ: lift 4 %, drag 8 %, thrust 3 %</small></div>
  </div>
  <div class="cols3">
    <div class="box"><div class="colhead">Numerical methods</div>
      <ul class="tight">
        <li>RK4 equations of motion, events located exactly</li>
        <li>Safeguarded secant for V1 (order ≈ 1.6)</li>
        <li>Ornstein–Uhlenbeck gust SDE, stepped with Heun</li>
        <li>Monte Carlo, P95 from order statistics</li>
      </ul></div>
    <div class="box"><div class="colhead">Limits</div>
      <ul class="tight">
        <li>Point mass, prescribed pitch: the rotation rate is assumed</li>
        <li>Sea-level thrust tables; constant runway friction</li>
        <li>Brake energy and tire speed reported, not limited</li>
        <li>Gusts: steady mean wind, vertical spectrum approximated, Dryden extrapolated near the ground</li>
        <li>Data errors independent, each scaling a whole table</li>
      </ul></div>
    <div class="box"><div class="colhead">Next steps</div>
      <ul class="tight">
        <li><b>Pitch dynamics</b>: full aero data with pitching moment and elevator power, to check the aircraft can
          actually rotate</li>
        <li><b>Lateral axis</b>: crosswind, engine-out yaw, side gusts</li>
        <li><b>Brakes and tires</b>: anti-skid, brake heating, wet-runway friction</li>
        <li><b>Correlated data errors</b>, and rare-event sampling for P99.9</li>
      </ul></div>
  </div>
  <div class="foot"><span>Harrison &amp; Seng · MATH 6006</span><span>16</span></div>
</section>
"""


TILE_CSS = """  .tiles3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 10px; }
  .tile { background: #eaf2fc; border-left: 5px solid var(--blue); border-radius: 10px; padding: 14px 20px; }
  .tile span { display: block; font-size: 15px; color: var(--muted); font-weight: 600; }
  .tile b { display: block; font-size: 38px; margin: 4px 0 2px; }
  .tile small { font-size: 14px; color: var(--muted); }
  .cols3 { display: grid; grid-template-columns: 0.9fr 1fr 1.1fr; gap: 16px; margin-top: 18px; }
  .cols3 .box { padding: 12px 16px; }
  .cols3 ul.tight { font-size: 14.5px; line-height: 1.4; }
  .cols3 ul.tight li { margin: 5px 0; }
"""


def group4() -> str:
    html = (OUT / "gust_slides.html").read_text().replace("</style>", TILE_CSS + "</style>", 1)
    start = html.index('<section class="slide')
    end = html.index("</body>")
    return html[:start] + NEW_SLIDES + "\n" + html[end:]


def main() -> None:
    parts = []
    for i, build in enumerate((group1, group2, group3, group4), 1):
        src = OUT / f"_final_part{i}.html"
        pdf = OUT / f"_final_part{i}.pdf"
        src.write_text(build())
        subprocess.run(["google-chrome", "--headless=new", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", src.as_uri()], check=True,
                       capture_output=True)  # fmt: skip
        parts.append(pdf)
    subprocess.run(["pdfunite", *map(str, parts), str(OUT / "final_presentation.pdf")], check=True)
    for i in range(1, 5):
        (OUT / f"_final_part{i}.html").unlink()
        (OUT / f"_final_part{i}.pdf").unlink()
    print("wrote", OUT / "final_presentation.pdf")


if __name__ == "__main__":
    main()
