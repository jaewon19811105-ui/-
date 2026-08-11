#!/usr/bin/env python3
"""리포트 HTML을 인쇄용 PDF로 변환한다.

헤드리스 Chromium의 --print-to-pdf 는 기본적으로 배경색을 인쇄하지 않고, 리포트
HTML에는 @media print 규칙이 없다. 그래서 원본을 건드리지 않고 임시 복사본에
인쇄용 CSS를 주입한 뒤 렌더링한다.

사용 예
  python3 scripts/make_pdf.py reports/solar-brief-2026.html reports/solar-brief-2026.pdf
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

CHROMIUM_CANDIDATES = (
    os.environ.get("CHROMIUM_PATH", ""),
    "/opt/pw-browsers/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
)

# 배경 인쇄를 강제하고, 표·섹션이 페이지 경계에서 어색하게 잘리지 않게 한다.
PRINT_CSS = """
<style id="print-overrides">
@page { size: A4; margin: 14mm 12mm; }
@media print {
  *, *::before, *::after {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  html, body { background: #fff !important; }
  h1, h2, h3, h4 { break-after: avoid-page; page-break-after: avoid; }
  table, figure, blockquote { break-inside: avoid-page; page-break-inside: avoid; }
  thead { display: table-header-group; }
  tr, li { break-inside: avoid-page; page-break-inside: avoid; }
  a { text-decoration: none; }
  /* A4 폭에서는 마스트헤드 메타 그리드가 한 줄에 다 안 들어가 빈 칸이 생긴다.
     최소 폭을 줄여 항목 수와 무관하게 한 줄에 배치되도록 한다. */
  .meta { grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)) !important; }
}
</style>
"""


def find_chromium():
    for path in CHROMIUM_CANDIDATES:
        if path and os.path.exists(path):
            return path
    found = shutil.which("chromium") or shutil.which("google-chrome")
    if found:
        return found
    raise SystemExit("Chromium 실행 파일을 찾지 못했습니다. CHROMIUM_PATH 로 지정하세요.")


def inject_print_css(html):
    """</head> 직전에 인쇄용 CSS를 넣는다. </head>가 없으면 맨 앞에 붙인다."""
    if "print-overrides" in html:
        return html
    m = re.search(r"</head\s*>", html, re.I)
    if m:
        return html[: m.start()] + PRINT_CSS + html[m.start():]
    return PRINT_CSS + html


def page_count(pdf_bytes):
    return max(0, pdf_bytes.count(b"/Type /Page") - pdf_bytes.count(b"/Type /Pages"))


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용법: make_pdf.py <입력.html> <출력.pdf>")
    src, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    if not os.path.exists(src):
        raise SystemExit("입력 파일이 없습니다: " + src)

    with open(src, encoding="utf-8") as f:
        html = inject_print_css(f.read())

    # 상대 경로 자산이 있어도 깨지지 않도록 원본과 같은 디렉터리에 임시 파일을 만든다.
    tmp_dir = os.path.dirname(src)
    fd, tmp = tempfile.mkstemp(suffix=".print.html", dir=tmp_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html)

        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        cmd = [
            find_chromium(),
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--no-pdf-header-footer",
            "--print-to-pdf=" + out,
            "file://" + tmp,
        ]
        # Chromium은 렌더링과 무관한 네트워크·DBus 오류를 stderr로 쏟는다. 조용히 돌린다.
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise SystemExit(
            "PDF 생성 실패 (exit %s)\n%s" % (proc.returncode, (proc.stderr or "")[-1500:])
        )

    with open(out, "rb") as f:
        data = f.read()
    pages = page_count(data)
    if pages == 0:
        raise SystemExit("PDF가 만들어졌지만 페이지를 찾을 수 없습니다: " + out)
    print("PDF 생성 완료: %s (%d쪽, %.1fMB)" % (out, pages, len(data) / 1024 / 1024))


if __name__ == "__main__":
    main()
