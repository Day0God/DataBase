"""Build the second-stage project report as a verified A4 PDF."""

import html
import re
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "phase2-final-report.md"
AI_LOG = ROOT / "docs" / "ai-usage-log.md"
TEST_CASES = ROOT / "docs" / "test-cases.md"
RICH_TEST = ROOT / "docs" / "phase2-rich-test-record.md"
OUTPUT = ROOT / "2026_ECNU_PJ1_2_徐文杰.pdf"
REPOSITORY_URL = "https://github.com/Day0God/DataBase/tree/homework01"
FONT_PATH = Path("C:/Windows/Fonts/simhei.ttf")

PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN = 2.15 * cm
RIGHT_MARGIN = 2.0 * cm
TOP_MARGIN = 2.0 * cm
BOTTOM_MARGIN = 1.9 * cm
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

INK = colors.HexColor("#17231F")
MUTED = colors.HexColor("#5D6C65")
ACCENT = colors.HexColor("#1F6B4F")
ACCENT_DARK = colors.HexColor("#164E3A")
LINE = colors.HexColor("#D9D2C4")
PAPER = colors.HexColor("#F3F0E7")
CODE_BG = colors.HexColor("#F2F3F4")


def register_fonts():
    if not FONT_PATH.exists():
        raise FileNotFoundError(f"Chinese font not found: {FONT_PATH}")
    pdfmetrics.registerFont(TTFont("SimHei", str(FONT_PATH)))


def styles():
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "BodyCN",
            parent=base["BodyText"],
            fontName="SimHei",
            fontSize=9.6,
            leading=15.2,
            textColor=INK,
            alignment=TA_JUSTIFY,
            wordWrap="CJK",
            spaceAfter=5,
        ),
        "h1": ParagraphStyle(
            "H1CN",
            fontName="SimHei",
            fontSize=19,
            leading=25,
            textColor=INK,
            spaceBefore=12,
            spaceAfter=10,
            keepWithNext=True,
            wordWrap="CJK",
        ),
        "h2": ParagraphStyle(
            "H2CN",
            fontName="SimHei",
            fontSize=13,
            leading=19,
            textColor=INK,
            spaceBefore=9,
            spaceAfter=6,
            keepWithNext=True,
            wordWrap="CJK",
        ),
        "h3": ParagraphStyle(
            "H3CN",
            fontName="SimHei",
            fontSize=10.8,
            leading=16,
            textColor=ACCENT_DARK,
            spaceBefore=6,
            spaceAfter=3,
            keepWithNext=True,
            wordWrap="CJK",
        ),
        "table": ParagraphStyle(
            "TableCN",
            fontName="SimHei",
            fontSize=7.25,
            leading=10,
            textColor=INK,
            wordWrap="CJK",
            spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "TableHeaderCN",
            fontName="SimHei",
            fontSize=7.4,
            leading=10,
            textColor=colors.white,
            alignment=TA_CENTER,
            wordWrap="CJK",
            spaceAfter=0,
        ),
        "blockquote": ParagraphStyle(
            "QuoteCN",
            fontName="SimHei",
            fontSize=9,
            leading=14,
            leftIndent=0.55 * cm,
            rightIndent=0.35 * cm,
            textColor=MUTED,
            wordWrap="CJK",
            spaceBefore=3,
            spaceAfter=5,
        ),
        "code": ParagraphStyle(
            "CodeCN",
            fontName="SimHei",
            fontSize=7.6,
            leading=11,
            textColor=colors.HexColor("#26332D"),
            leftIndent=0.35 * cm,
            rightIndent=0.25 * cm,
            spaceBefore=4,
            spaceAfter=7,
            backColor=CODE_BG,
            borderPadding=(7, 8, 7, 8),
            wordWrap="CJK",
        ),
        "caption": ParagraphStyle(
            "CaptionCN",
            fontName="SimHei",
            fontSize=7.8,
            leading=11,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=8,
            wordWrap="CJK",
        ),
    }


STYLES = None


def inline(value):
    value = html.escape(value, quote=False)
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<link href="\2" color="#1F6B4F"><u>\1</u></link>',
        value,
    )
    value = re.sub(r"`([^`]+)`", r'<font name="SimHei" color="#174A37">\1</font>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    return value


def markdown_table(rows):
    headers = [cell.strip() for cell in rows[0].strip("|").split("|")]
    body = []
    for row in rows[1:]:
        if re.match(r"^\s*\|?\s*:?-{3,}", row):
            continue
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        cells += [""] * (len(headers) - len(cells))
        body.append(cells[: len(headers)])

    count = len(headers)
    ratios = {
        2: [0.28, 0.72],
        3: [0.23, 0.39, 0.38],
        4: [0.13, 0.29, 0.29, 0.29],
        5: [0.09, 0.24, 0.25, 0.26, 0.16],
    }.get(count, [1 / count] * count)
    widths = [CONTENT_WIDTH * ratio for ratio in ratios]
    data = [
        [Paragraph(inline(cell), STYLES["table_header"]) for cell in headers]
    ]
    for row in body:
        data.append([Paragraph(inline(cell), STYLES["table"]) for cell in row])
    table = Table(
        data,
        colWidths=widths,
        repeatRows=1,
        hAlign="CENTER",
        splitByRow=1,
    )
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "SimHei"),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for row_index in range(1, len(data)):
        if row_index % 2 == 0:
            commands.append(
                ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F5F7F6"))
            )
    table.setStyle(TableStyle(commands))
    return table


def image_flowable(path_value, caption):
    path = (REPORT.parent / path_value).resolve()
    if not path.exists():
        return Paragraph(f"图片未找到：{inline(path_value)}", STYLES["caption"])
    with PILImage.open(path) as image:
        width, height = image.size
    max_width = 13.6 * cm
    max_height = 19.2 * cm
    scale = min(max_width / width, max_height / height)
    rendered = Image(str(path), width=width * scale, height=height * scale)
    rendered.hAlign = "CENTER"
    return KeepTogether(
        [
            rendered,
            Paragraph(inline(caption), STYLES["caption"]),
            Spacer(1, 5),
        ]
    )


def markdown_flowables(markdown, include_title=False):
    lines = markdown.splitlines()
    result = []
    index = 0
    paragraph_parts = []

    def flush_paragraph():
        nonlocal paragraph_parts
        if paragraph_parts:
            result.append(
                Paragraph(inline(" ".join(paragraph_parts)), STYLES["body"])
            )
            paragraph_parts = []

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            index += 1
            code = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            result.append(Preformatted("\n".join(code), STYLES["code"]))
            result.append(Spacer(1, 3))
            index += 1
            continue

        image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            flush_paragraph()
            result.append(image_flowable(image_match.group(2), image_match.group(1)))
            index += 1
            continue

        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            if level == 1 and not include_title:
                index += 1
                continue
            style = STYLES["h1"] if level <= 1 else STYLES["h2"] if level == 2 else STYLES["h3"]
            result.append(Paragraph(inline(heading.group(2)), style))
            index += 1
            continue

        if stripped.startswith("|"):
            flush_paragraph()
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index].strip())
                index += 1
            result.append(markdown_table(rows))
            result.append(Spacer(1, 5))
            continue

        if re.match(r"^[-*]\s+", stripped):
            flush_paragraph()
            items = []
            while index < len(lines):
                match = re.match(r"^[-*]\s+(.*)$", lines[index].strip())
                if not match:
                    break
                items.append(ListItem(Paragraph(inline(match.group(1)), STYLES["body"])))
                index += 1
            result.append(
                ListFlowable(
                    items,
                    bulletType="bullet",
                    start="circle",
                    leftIndent=16,
                    bulletFontName="SimHei",
                    bulletFontSize=7,
                    spaceAfter=5,
                )
            )
            continue

        numbered = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if numbered:
            flush_paragraph()
            number = int(numbered.group(1))
            items = []
            while index < len(lines):
                match = re.match(r"^(\d+)\.\s+(.*)$", lines[index].strip())
                if not match:
                    break
                items.append(ListItem(Paragraph(inline(match.group(2)), STYLES["body"])))
                index += 1
            result.append(
                ListFlowable(
                    items,
                    bulletType="1",
                    start=number,
                    leftIndent=18,
                    bulletFontName="SimHei",
                    bulletFontSize=8,
                    spaceAfter=5,
                )
            )
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote = [stripped.lstrip("> ").strip()]
            index += 1
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip("> ").strip())
                index += 1
            result.append(
                Paragraph(inline(" ".join(quote)), STYLES["blockquote"])
            )
            continue

        paragraph_parts.append(stripped)
        index += 1

    flush_paragraph()
    return result


class ReportDocument(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        body_frame = Frame(
            LEFT_MARGIN,
            BOTTOM_MARGIN,
            CONTENT_WIDTH,
            PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN,
            id="body",
        )
        cover_frame = Frame(
            LEFT_MARGIN,
            BOTTOM_MARGIN,
            CONTENT_WIDTH,
            PAGE_HEIGHT - 2.4 * cm - BOTTOM_MARGIN,
            id="cover",
        )
        self.addPageTemplates(
            [
                PageTemplate(
                    id="cover",
                    frames=[cover_frame],
                    onPage=self.draw_cover,
                ),
                PageTemplate(
                    id="body",
                    frames=[body_frame],
                    onPage=self.draw_body_page,
                ),
            ]
        )

    @staticmethod
    def draw_cover(canvas, document):
        canvas.saveState()
        canvas.setFillColor(PAPER)
        canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        canvas.setFillColor(ACCENT_DARK)
        canvas.roundRect(
            LEFT_MARGIN,
            PAGE_HEIGHT - 2.1 * cm,
            2.0 * cm,
            0.16 * cm,
            0.08 * cm,
            fill=1,
            stroke=0,
        )
        canvas.restoreState()

    @staticmethod
    def draw_body_page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.35)
        canvas.line(
            LEFT_MARGIN,
            PAGE_HEIGHT - 1.35 * cm,
            PAGE_WIDTH - RIGHT_MARGIN,
            PAGE_HEIGHT - 1.35 * cm,
        )
        canvas.setFont("SimHei", 7.2)
        canvas.setFillColor(MUTED)
        canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT - 1.13 * cm, "2026 ECNU PJ1 / 第二阶段项目报告")
        canvas.drawRightString(
            PAGE_WIDTH - RIGHT_MARGIN,
            PAGE_HEIGHT - 1.13 * cm,
            "MongoDB 在线问卷系统",
        )
        canvas.setFillColor(MUTED)
        canvas.drawRightString(
            PAGE_WIDTH - RIGHT_MARGIN,
            0.9 * cm,
            f"第 {document.page} 页",
        )
        canvas.restoreState()


def cover_flowables():
    result = [
        Spacer(1, 1.6 * cm),
        Paragraph("2026 ECNU PJ1 · PHASE 2", STYLES["h3"]),
        Spacer(1, 0.8 * cm),
        Paragraph(
            "基于 MongoDB 的在线问卷系统",
            ParagraphStyle(
                "CoverTitle",
                fontName="SimHei",
                fontSize=25,
                leading=34,
                textColor=INK,
                spaceAfter=8,
                wordWrap="CJK",
            ),
        ),
        Paragraph(
            "第二阶段项目完成报告",
            ParagraphStyle(
                "CoverSubtitle",
                fontName="SimHei",
                fontSize=15,
                leading=22,
                textColor=INK,
                spaceAfter=26,
                wordWrap="CJK",
            ),
        ),
        Paragraph(
            f'<link href="{REPOSITORY_URL}" color="#1F6B4F"><u>{REPOSITORY_URL}</u></link>',
            STYLES["body"],
        ),
        Spacer(1, 0.75 * cm),
    ]
    details = [
        ("项目成员", "徐文杰"),
        ("提交分支", "homework01"),
        ("系统技术栈", "Python / Flask / MongoDB / 原生前端"),
        ("自动化测试", "17 项通过"),
        ("报告日期", "2026 年 10 月 27 日"),
    ]
    table_data = [
        [
            Paragraph("项目信息", STYLES["table_header"]),
            Paragraph("内容", STYLES["table_header"]),
        ]
    ]
    for key, value in details:
        table_data.append(
            [
                Paragraph(inline(key), STYLES["table"]),
                Paragraph(inline(value), STYLES["table"]),
            ]
        )
    table = Table(table_data, colWidths=[3.0 * cm, 12.0 * cm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT_DARK),
                ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    result.extend(
        [
            table,
            Spacer(1, 2.8 * cm),
            Paragraph("DataBase / homework01", STYLES["caption"]),
            NextPageTemplate("body"),
            PageBreak(),
        ]
    )
    return result


def main():
    global STYLES
    register_fonts()
    STYLES = styles()

    report_text = REPORT.read_text(encoding="utf-8")
    ai_text = AI_LOG.read_text(encoding="utf-8")
    test_text = TEST_CASES.read_text(encoding="utf-8")
    rich_text = RICH_TEST.read_text(encoding="utf-8")

    story = cover_flowables()
    story.extend(markdown_flowables(report_text))

    story.extend(
        [
            PageBreak(),
            Paragraph("附录 A　完整 AI 使用日志", STYLES["h1"]),
            Paragraph(
                "以下内容来自项目实际工作记录，保留真实提示摘要、生成结果、修改情况和验证输出。",
                STYLES["body"],
            ),
        ]
    )
    story.extend(markdown_flowables(ai_text))

    story.extend(
        [
            PageBreak(),
            Paragraph("附录 B　测试用例与结果", STYLES["h1"]),
            Paragraph(
                "自动化与浏览器测试均按测试步骤、输入、输出、结果记录。",
                STYLES["body"],
            ),
        ]
    )
    story.extend(markdown_flowables(test_text))

    story.extend(
        [
            PageBreak(),
            Paragraph("附录 C　复杂问卷与统计验收", STYLES["h1"]),
        ]
    )
    story.extend(markdown_flowables(rich_text))

    document = ReportDocument(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title="基于 MongoDB 的在线问卷系统第二阶段项目完成报告",
        author="徐文杰",
        subject="2026 ECNU PJ1 第二阶段项目报告",
    )
    document.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
