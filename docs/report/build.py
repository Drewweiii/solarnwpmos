"""Assemble the report and print it to PDF.

HTML -> Chromium -> PDF, rather than LaTeX, for one decisive reason: this
sandbox has no TeX distribution, but it does have Chromium, and Chromium renders
Thai correctly with a vendored webfont. KaTeX is rendered at BUILD time (its
auto-render pass runs in the page, then we wait for it) so the printed PDF holds
laid-out glyphs rather than depending on any script at viewing time.

Everything is inlined or file:// local - no network at print time, which is what
makes the build reproducible offline.

Run:  python3 docs/report/build.py
Out:  docs/report/NongFab-Solar-EMS-Report.pdf
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chapters import SITE, render_chapters  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_PDF = HERE / "NongFab-Solar-EMS-Report.pdf"
OUT_HTML = HERE / "report.html"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# KaTeX is installed under the scratch npm tree; copy what the page needs next
# to the report so the build does not depend on that tree surviving.
KATEX_SRC = Path("/tmp/claude-0/-home-user-solarnwpmos/660b3e3f-2f34-5c4a-8b19-7a3ce01be643/scratchpad/node_modules/katex/dist")
KATEX_DIR = HERE / "katex"

ICT = timezone(timedelta(hours=7))


def ensure_katex() -> bool:
    if (KATEX_DIR / "katex.min.css").exists():
        return True
    if not KATEX_SRC.exists():
        return False
    KATEX_DIR.mkdir(exist_ok=True)
    for name in ("katex.min.css", "katex.min.js", "contrib/auto-render.min.js"):
        src = KATEX_SRC / name
        dst = KATEX_DIR / Path(name).name
        if src.exists():
            shutil.copy(src, dst)
    fonts_src = KATEX_SRC / "fonts"
    if fonts_src.exists():
        shutil.copytree(fonts_src, KATEX_DIR / "fonts", dirs_exist_ok=True)
    return (KATEX_DIR / "katex.min.css").exists()


def font_face_css() -> str:
    """Embed the Thai font as base64 so the printed PDF never depends on what
    fonts the printing machine happens to have."""
    css = []
    for weight, fname in ((400, "IBMPlexSansThai-Regular.ttf"), (700, "IBMPlexSansThai-Bold.ttf")):
        path = HERE / "fonts" / fname
        if not path.exists():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode()
        css.append(
            f"@font-face{{font-family:'PlexThai';font-style:normal;font-weight:{weight};"
            f"src:url(data:font/ttf;base64,{b64}) format('truetype');font-display:block;}}"
        )
    return "\n".join(css)


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


CSS = r"""
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{
  font-family:'PlexThai','IBM Plex Sans Thai',sans-serif;
  /* Thai stacks vowels and tone marks two levels above the baseline, so the
     1.45 line-height used elsewhere in this project collides. 1.75 is the
     working range for Thai body text. */
  font-size:10.5pt;line-height:1.75;color:#1a1a1a;margin:0;
}
h1,h2,h3,h4{line-height:1.4;color:#0f172a;margin:1.4em 0 .5em}
h2{font-size:17pt;border-bottom:2.5px solid #2563eb;padding-bottom:.3em;margin-top:0}
h3{font-size:12.5pt;color:#1e40af;margin-top:1.6em}
h4{font-size:11pt;color:#334155}
p{margin:.55em 0;text-align:justify}
ol,ul{margin:.55em 0;padding-left:1.5em}
li{margin:.3em 0}
.chnum{display:block;font-size:9.5pt;color:#2563eb;font-weight:600;letter-spacing:.06em;margin-bottom:.15em}
.chapter{page-break-before:always}
.chapter:first-of-type{page-break-before:avoid}

/* Cover */
.cover{height:247mm;display:flex;flex-direction:column;justify-content:center;text-align:center;page-break-after:always}
.cover .kicker{font-size:11pt;color:#2563eb;letter-spacing:.18em;text-transform:uppercase;font-weight:600}
.cover h1{font-size:27pt;margin:.35em 0;line-height:1.35;border:none}
.cover .sub{font-size:13pt;color:#475569;margin-bottom:2.2em}
.cover .meta{font-size:10pt;color:#64748b;line-height:2}
.cover .rule{width:80px;height:3px;background:#2563eb;margin:1.4em auto}

/* Figures */
figure{margin:1.1em 0;page-break-inside:avoid;text-align:center}
figure img{max-width:100%;border:1px solid #e2e8f0;border-radius:5px}
figure img.narrow{max-width:74%}
figure img.phone{max-width:31%}
figure img.tall{max-width:88%}
figcaption{font-size:8.8pt;color:#475569;margin-top:.5em;text-align:left;line-height:1.65;
  border-left:3px solid #cbd5e1;padding-left:.75em}

/* Tables */
table.spec{width:100%;border-collapse:collapse;margin:.9em 0;font-size:9.5pt;page-break-inside:avoid}
table.spec th,table.spec td{border:1px solid #e2e8f0;padding:.45em .7em;text-align:left;vertical-align:top}
table.spec th{background:#f1f5f9;font-weight:600;color:#0f172a;width:32%}
table.spec tr:first-child th{background:#e0e7ff}

.num{font-variant-numeric:tabular-nums;font-weight:600}
.code{font-family:ui-monospace,Consolas,monospace;font-size:.9em;background:#f1f5f9;
  padding:.1em .35em;border-radius:3px;color:#be123c}

pre.flow{background:#f8fafc;border:1px solid #e2e8f0;border-radius:5px;padding:1em;
  font-family:ui-monospace,Consolas,monospace;font-size:8pt;line-height:1.55;overflow:hidden}

.callout{background:#f0f9ff;border-left:4px solid #0284c7;padding:.75em 1em;margin:1em 0;
  border-radius:0 5px 5px 0;page-break-inside:avoid;font-size:9.8pt}
.callout.warn{background:#fffbeb;border-left-color:#d97706}
.callout p{margin:.35em 0}

/* Maths */
.katex{font-size:1.02em}
.katex-display{margin:.85em 0;overflow-x:hidden}
.katex-display>.katex{white-space:normal}

/* TOC */
.toc{page-break-after:always}
.toc h2{border-bottom:2.5px solid #2563eb}
.toc ol{list-style:none;padding-left:0;counter-reset:t}
.toc li{counter-increment:t;padding:.42em 0;border-bottom:1px dotted #cbd5e1;font-size:10.5pt}
.toc li::before{content:"บทที่ " counter(t) " · ";color:#2563eb;font-weight:600}
"""


def build_html() -> str:
    now = datetime.now(ICT)
    katex_ok = ensure_katex()
    katex_head = (
        '<link rel="stylesheet" href="katex/katex.min.css">'
        '<script defer src="katex/katex.min.js"></script>'
        '<script defer src="katex/auto-render.min.js"></script>'
        if katex_ok
        else ""
    )
    toc = "".join(f"<li>{c}</li>" for c in [
        "บทนำและขอบเขตของงาน", "สถาปัตยกรรมระบบและการไหลของข้อมูล",
        "พีชคณิตเชิงเส้นของเรขาคณิตแผงและระบบพิกัด", "ดาราศาสตร์ดวงอาทิตย์และแบบจำลองรังสี",
        "แบบจำลองเงาแถวต่อแถวเชิงวิเคราะห์", "กำลังสองน้อยที่สุดและการถดถอยเชิงเส้น",
        "การหาค่าเหมาะที่สุด (Optimization)", "แบบจำลองพยากรณ์และการแข่งขันระหว่างโมเดล",
        "การตรวจสอบความแม่นยำ (Verification)", "แบบจำลองทางการเงิน",
        "เว็บไซต์และตัวอย่างการใช้งาน", "ข้อจำกัด สรุป และงานต่อไป",
    ])

    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<title>รายงานระบบพยากรณ์พลังงานแสงอาทิตย์ — PTT LNG Terminal 2</title>
{katex_head}
<style>{font_face_css()}
{CSS}</style></head><body>

<div class="cover">
  <div class="kicker">รายงานโครงการ</div>
  <h1>ระบบพยากรณ์และจัดการพลังงาน<br>แสงอาทิตย์</h1>
  <div class="rule"></div>
  <div class="sub">{SITE['name']}<br>จังหวัด{SITE['province']} · {SITE['lat']}°N, {SITE['lon']}°E</div>
  <div class="meta">
    ทฤษฎีการคำนวณ · พีชคณิตเชิงเส้น · การหาค่าเหมาะที่สุด<br>
    กำลังติดตั้ง {SITE['capacity_kwp']:,.1f} kWp · {SITE['modules']} แผง · {SITE['zones']}<br><br>
    จัดทำเมื่อ {now.strftime('%d/%m/')}{now.year + 543} เวลา {now.strftime('%H:%M')} น. (ICT)<br>
    อ้างอิงซอร์สโค้ด commit <span class="code">{git_commit()}</span>
  </div>
</div>

<section class="toc"><h2>สารบัญ</h2><ol>{toc}</ol>
<p style="font-size:9.5pt;color:#475569;margin-top:1.5em">
<b>หมายเหตุ</b> สมการทุกสมการในรายงานนี้เป็นสมการที่ระบบประเมินจริง
รูปภาพทุกรูปคำนวณจากสมการเหล่านั้นที่พิกัดจริงของไซต์ และภาพหน้าจอทุกภาพ
ถ่ายจากระบบที่รันจริง ค่าใดที่เป็นค่าประมาณจะระบุไว้ชัดเจนทุกครั้ง</p>
</section>

{render_chapters()}

</body></html>"""


async def render_pdf() -> None:
    from playwright.async_api import async_playwright

    OUT_HTML.write_text(build_html(), encoding="utf-8")
    print(f"  wrote {OUT_HTML.name} ({OUT_HTML.stat().st_size/1024:.0f} KB)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME)
        page = await browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(OUT_HTML.as_uri(), wait_until="load")

        # Run KaTeX's auto-render explicitly and WAIT for it. Printing before it
        # finishes yields a PDF full of raw $$...$$, which looks like a broken
        # build but exits successfully.
        rendered = await page.evaluate(
            """async () => {
                if (!window.renderMathInElement) return -1;
                window.renderMathInElement(document.body, {
                    delimiters: [
                        {left: '$$', right: '$$', display: true},
                        {left: '\\\\(', right: '\\\\)', display: false}
                    ],
                    throwOnError: false
                });
                await document.fonts.ready;
                return document.querySelectorAll('.katex').length;
            }"""
        )
        if rendered == -1:
            print("  WARNING: KaTeX did not load - equations will print as raw markup")
        else:
            print(f"  KaTeX rendered {rendered} equations")
        await page.wait_for_timeout(2500)

        await page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "bottom": "18mm", "left": "17mm", "right": "17mm"},
            display_header_footer=True,
            header_template='<div></div>',
            footer_template=(
                '<div style="font-size:7.5pt;color:#94a3b8;width:100%;padding:0 17mm;'
                'display:flex;justify-content:space-between">'
                '<span>PTT LNG Terminal 2 — ระบบพยากรณ์พลังงานแสงอาทิตย์</span>'
                '<span class="pageNumber"></span></div>'
            ),
        )
        for e in errors[:5]:
            print(f"  page error: {e}")
        await browser.close()

    print(f"  wrote {OUT_PDF.name} ({OUT_PDF.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    asyncio.run(render_pdf())
