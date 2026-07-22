"""Build the repository-safe D1 competition report PDF."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import fitz
from pypdf import PdfReader
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/delivery/D1-technical-report-draft.md"
OUTPUT = ROOT / "output/pdf/XA-Guard-XA-202620-technical-report.pdf"
NAVY, BLUE, CYAN = colors.HexColor("#0B1F3A"), colors.HexColor("#1769AA"), colors.HexColor("#00A6A6")
INK, MUTED, PALE = colors.HexColor("#172033"), colors.HexColor("#596579"), colors.HexColor("#EAF2F8")


def register_font() -> str:
    candidates = [Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
                  Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf")]
    for path in candidates:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("CN", str(path), subfontIndex=0))
                return "CN"
            except Exception:
                continue
    raise RuntimeError("No usable Chinese font found in C:/Windows/Fonts")


class Diagram(Flowable):
    LABELS = {
        "threat": ["不可信输入", "身份/授权", "工具执行", "真实副作用", "可验证证据"],
        "architecture": ["Human + Agent", "Governance", "Gate1–6", "Effect + Worker", "业务系统"],
        "identity": ["OIDC 登录", "Token Exchange", "双主体声明", "动态 Assignment", "最小权限"],
        "state": ["prepared", "executed", "available", "undo_pending", "compensated"],
        "oar": ["攻击任务", "Null / Guard", "工具尝试", "审计对齐", "A/B 结论"],
        "results": ["11/11 故障", "kind HA", "p95 < 50ms", "Undo < 1s", "证据签名"],
        "deployment": ["Console/BFF", "XA-Guard API", "Worker", "PostgreSQL", "Keycloak/业务"],
    }

    def __init__(self, name: str):
        super().__init__()
        self.name, self.width, self.height = name, 168 * mm, 27 * mm

    def draw(self):
        labels = self.LABELS.get(self.name, [self.name])
        gap, arrow = 3 * mm, 5 * mm
        width = (self.width - (len(labels) - 1) * (gap + arrow)) / len(labels)
        self.canv.setFont("CN", 7.7)
        for index, label in enumerate(labels):
            x = index * (width + gap + arrow)
            self.canv.setFillColor(PALE if index % 2 == 0 else colors.HexColor("#D9F3F2"))
            self.canv.setStrokeColor(BLUE)
            self.canv.roundRect(x, 5 * mm, width, 15 * mm, 2 * mm, fill=1, stroke=1)
            self.canv.setFillColor(INK)
            self.canv.drawCentredString(x + width / 2, 11 * mm, label)
            if index < len(labels) - 1:
                ax = x + width + gap
                self.canv.setStrokeColor(CYAN)
                self.canv.line(ax, 12.5 * mm, ax + arrow, 12.5 * mm)
                self.canv.line(ax + arrow - 2 * mm, 14 * mm, ax + arrow, 12.5 * mm)
                self.canv.line(ax + arrow - 2 * mm, 11 * mm, ax + arrow, 12.5 * mm)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text: str) -> str:
    text = esc(text.strip())
    text = re.sub(r"`([^`]+)`", r'<font color="#1769AA">\1</font>', text)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)


def styles(font: str):
    base = getSampleStyleSheet()
    return {
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=font, fontSize=14, leading=19,
                              textColor=NAVY, spaceBefore=2 * mm, spaceAfter=4 * mm),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=font, fontSize=11, leading=15,
                              textColor=BLUE, spaceBefore=2 * mm, spaceAfter=2 * mm),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=font, fontSize=9.2, leading=15,
                                alignment=TA_JUSTIFY, textColor=INK, spaceAfter=2.8 * mm, wordWrap="CJK"),
        "bullet": ParagraphStyle("bullet", parent=base["BodyText"], fontName=font, fontSize=8.9, leading=14,
                                  leftIndent=5 * mm, firstLineIndent=-3 * mm, textColor=INK,
                                  spaceAfter=1.5 * mm, wordWrap="CJK"),
        "code": ParagraphStyle("code", parent=base["Code"], fontName=font, fontSize=7.5, leading=11,
                                leftIndent=5 * mm, textColor=colors.HexColor("#31465F"),
                                backColor=colors.HexColor("#F4F7FA"), borderPadding=3 * mm, spaceAfter=2 * mm),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontName=font, fontSize=7.2, leading=10,
                                textColor=INK, wordWrap="CJK"),
        "headcell": ParagraphStyle("headcell", parent=base["BodyText"], fontName=font, fontSize=7.2,
                                    leading=10, textColor=colors.white, wordWrap="CJK"),
    }


def cover(font: str):
    title = ParagraphStyle("cover-title", fontName=font, fontSize=27, leading=38,
                           alignment=TA_CENTER, textColor=NAVY)
    sub = ParagraphStyle("cover-sub", fontName=font, fontSize=13, leading=20,
                         alignment=TA_CENTER, textColor=BLUE)
    meta = ParagraphStyle("cover-meta", fontName=font, fontSize=10, leading=18,
                          alignment=TA_CENTER, textColor=MUTED)
    rule = Table([[""]], colWidths=[42 * mm], rowHeights=[1.5 * mm],
                 style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), CYAN)]))
    return [Spacer(1, 43 * mm), Paragraph("XA-Guard", title), Spacer(1, 4 * mm),
            Paragraph("面向政企智能体的身份约束、六关防护与可验证撤销", sub),
            Spacer(1, 15 * mm), rule, Spacer(1, 15 * mm),
            Paragraph("题目编号：XA-202620", meta), Paragraph("D1 技术方案报告", meta),
            Paragraph("工程冻结版 · 仓库安全封面", meta), Spacer(1, 40 * mm),
            Paragraph("XA-Guard Project · 2026-07", meta), PageBreak()]


def table_from(lines: list[str], st) -> Table:
    rows = []
    for line in lines:
        raw_cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]+", cell) for cell in raw_cells):
            continue
        cell_style = st["headcell"] if not rows else st["cell"]
        rows.append([Paragraph(inline(cell), cell_style) for cell in raw_cells])
    count = max(len(row) for row in rows)
    table = Table(rows, colWidths=[168 * mm / count] * count, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "CN"),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B9C8D6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F9FB")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def parse(markdown: str, st) -> list:
    lines = markdown.splitlines()
    lines = lines[lines.index("<!-- pagebreak -->") + 1:]
    story, index = [], 0
    while index < len(lines):
        raw, stripped = lines[index], lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped == "<!-- pagebreak -->":
            story.append(PageBreak())
            index += 1
            continue
        match = re.fullmatch(r"\[DIAGRAM:([a-z]+)\]", stripped)
        if match:
            story.extend([Spacer(1, 2 * mm), Diagram(match.group(1)), Spacer(1, 3 * mm)])
            index += 1
            continue
        if stripped.startswith("|"):
            block = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            story.extend([table_from(block, st), Spacer(1, 3 * mm)])
            continue
        if raw.startswith("    "):
            block = []
            while index < len(lines) and (lines[index].startswith("    ") or not lines[index].strip()):
                if lines[index].strip():
                    block.append(esc(lines[index].strip()))
                index += 1
            story.append(Paragraph("<br/>".join(block), st["code"]))
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(inline(stripped[4:]), st["h3"]))
            index += 1
            continue
        if stripped.startswith("## "):
            story.append(Paragraph(inline(stripped[3:]), st["h2"]))
            index += 1
            continue
        if re.match(r"^(?:[-*]|\d+\.)\s+", stripped):
            label = re.sub(r"^(?:[-*]|\d+\.)\s+", "", re.sub(r"\s+", " ", stripped))
            story.append(Paragraph("• " + inline(label), st["bullet"]))
            index += 1
            continue
        paragraph = [stripped]
        index += 1
        special = r"^(?:#{2,3} |\| |    |[-*] |\d+\. |<!--|\[DIAGRAM:)"
        while index < len(lines) and lines[index].strip() and not re.match(special, lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        story.append(Paragraph(inline(" ".join(paragraph)), st["body"]))
    return story


def decorate(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 8 * mm, A4[0], 8 * mm, fill=1, stroke=0)
    if doc.page > 1:
        canvas.setFont("CN", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(21 * mm, 11 * mm, "XA-Guard · D1 技术方案报告")
        canvas.drawRightString(A4[0] - 21 * mm, 11 * mm, str(doc.page))
        canvas.setStrokeColor(colors.HexColor("#D5DEE7"))
        canvas.line(21 * mm, 15 * mm, A4[0] - 21 * mm, 15 * mm)
    canvas.restoreState()


def build(source: Path, output: Path, render_dir: Path | None):
    rl_config.invariant = 1
    font = register_font()
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(output), pagesize=A4, leftMargin=21 * mm, rightMargin=21 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title="XA-Guard XA-202620 技术方案报告", author="XA-Guard Project",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates(PageTemplate(id="report", frames=[frame], onPage=decorate))
    doc.build(cover(font) + parse(source.read_text(encoding="utf-8"), styles(font)))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii")
    if render_dir:
        render_dir.mkdir(parents=True, exist_ok=True)
        pdf = fitz.open(output)
        for number, page in enumerate(pdf, 1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
            pixmap.save(render_dir / f"page-{number:02d}.png")
    pages = len(PdfReader(str(output)).pages)
    print(json.dumps({"output": str(output), "pages": pages, "sha256": digest,
                      "render_dir": str(render_dir) if render_dir else None},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--render-dir", type=Path)
    args = parser.parse_args()
    build(args.source, args.output, args.render_dir)
