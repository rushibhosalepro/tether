"""Self-contained static HTML for the two-arm result. No framework, no server, no CDN.

This is the entire "frontend". It exists for exactly one reader: a judge who will not start
Docker and needs to see the number in ten seconds. Everything Tether actually produces lives
in DataHub and in the PR, which is where it belongs.
"""

from __future__ import annotations

from pathlib import Path

CSS = """
:root { color-scheme: light dark; --fg:#111; --bg:#fff; --mut:#666; --line:#e3e3e3;
        --block:#c0392b; --ok:#1e8449; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8e8e8; --bg:#131313; --mut:#9a9a9a; --line:#2c2c2c;
          --block:#ff6b5a; --ok:#4ade80; }
}
* { box-sizing:border-box }
body { margin:0; padding:3rem 1.5rem; background:var(--bg); color:var(--fg);
       font:16px/1.6 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif; }
main { max-width:860px; margin:0 auto }
h1 { font-size:1.6rem; margin:0 0 .25rem }
.sub { color:var(--mut); margin:0 0 2.5rem }
.arms { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:1rem }
.arm { border:1px solid var(--line); border-radius:10px; padding:1.25rem }
.arm h2 { font-size:.8rem; text-transform:uppercase; letter-spacing:.08em;
          color:var(--mut); margin:0 0 1rem }
.big { font-size:2.6rem; font-weight:600; line-height:1 }
.big.miss { color:var(--block) }
.big.good { color:var(--ok) }
.metric { display:flex; justify-content:space-between; padding:.4rem 0;
          border-top:1px solid var(--line); font-variant-numeric:tabular-nums }
.metric:first-of-type { border-top:0 }
table { width:100%; border-collapse:collapse; margin:2rem 0; font-size:.9rem }
th,td { text-align:left; padding:.55rem .5rem; border-bottom:1px solid var(--line) }
th { color:var(--mut); font-weight:500; font-size:.8rem }
code { font:.85em ui-monospace,SFMono-Regular,Menlo,monospace;
       background:color-mix(in srgb, var(--fg) 8%, transparent); padding:.1em .35em; border-radius:4px }
.note { color:var(--mut); font-size:.9rem; border-left:2px solid var(--line);
        padding-left:1rem; margin:2rem 0 }
.wrap { overflow-x:auto }
"""


def render(scores, out_dir: Path) -> Path:
    cards = []
    for s in scores:
        d = s.to_dict()
        cls = "miss" if s.fn else "good"
        cards.append(
            f"""<div class="arm">
  <h2>{s.arm}</h2>
  <div class="big {cls}">{d['recall']:.0%}</div>
  <div class="metric"><span>recall</span><span>{d['recall']:.0%}</span></div>
  <div class="metric"><span>precision</span><span>{d['precision']:.0%}</span></div>
  <div class="metric"><span>missed breakages</span><span>{s.fn}</span></div>
  <div class="metric"><span>false alarms</span><span>{s.fp}</span></div>
  <div class="metric"><span>changes scored</span><span>{d['n']}</span></div>
</div>"""
        )

    rows = []
    for s in scores:
        for m in s.misses:
            rows.append(
                f"<tr><td>{s.arm}</td><td><code>{m['column']}</code></td>"
                f"<td>{m['case_id']}</td><td>predicted {m['predicted']}, actually broke</td></tr>"
            )

    misses_table = (
        f"""<h3>Every miss, named</h3><div class="wrap"><table>
<thead><tr><th>Arm</th><th>Column</th><th>Case</th><th>What happened</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>"""
        if rows
        else ""
    )

    html = f"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tether benchmark</title><style>{CSS}</style>
<main>
<h1>Same agent, same PRs, one difference</h1>
<p class="sub">One arm walks DataHub lineage into the ML layer. The other has the dbt
manifest, which is what most teams actually have.</p>
<div class="arms">{''.join(cards)}</div>
{misses_table}
<p class="note">The control arm is not crippled. It does full manifest traversal across
<code>child_map</code>. It reports zero ML impacts because dbt's graph contains no
<code>mlFeature</code>, <code>mlModel</code> or <code>mlModelDeployment</code> entities to
find. That is the structural gap DataHub closes.</p>
</main>"""

    path = out_dir.parent.parent / "examples" / "report.html"
    path.parent.mkdir(exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
