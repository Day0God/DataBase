from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = ROOT / ".pdf-temp" / "MongoForm-第一阶段项目报告.pdf"
OUTPUT_PDF = ROOT / "2026_ECNU_PJ1_1_徐文杰.pdf"
REPOSITORY_URL = "https://github.com/Day0God/DataBase/tree/homework01"
FONT_PATH = Path("C:/Windows/Fonts/simhei.ttf")


def build_cover():
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdfmetrics.registerFont(TTFont("SimHei", str(FONT_PATH)))
    page.setTitle("基于 MongoDB 的在线问卷系统第一阶段项目完成报告")
    page.setAuthor("徐文杰")
    page.setSubject("2026 ECNU PJ1 第一阶段项目报告")

    page.setFillColorRGB(0.10, 0.16, 0.14)
    page.setFont("SimHei", 10)
    page.drawString(64, height - 90, "2026 ECNU PJ1")

    page.setFillColorRGB(0, 0, 0)
    page.setFont("SimHei", 25)
    page.drawString(64, height - 164, "基于 MongoDB 的在线问卷系统")

    page.setFont("SimHei", 14)
    page.drawString(64, height - 200, "第一阶段项目完成报告")

    page.setFont("SimHei", 9.5)
    page.setFillColorRGB(0.29, 0.34, 0.32)
    page.drawString(64, height - 250, "GitHub 仓库")

    page.setFillColorRGB(0.08, 0.13, 0.11)
    page.setFont("SimHei", 10.5)
    page.drawString(64, height - 273, REPOSITORY_URL)
    page.linkURL(
        REPOSITORY_URL,
        (64, height - 280, 490, height - 260),
        relative=0,
    )

    details = [
        ("项目成员", "徐文杰"),
        ("提交分支", "homework01"),
        ("系统技术栈", "Python / Flask / MongoDB / 原生前端"),
        ("测试结果", "13 项自动测试通过"),
        ("报告日期", "2026 年 10 月 22 日"),
    ]
    y = height - 380
    for label, value in details:
        page.setFillColorRGB(0.20, 0.24, 0.22)
        page.setFont("SimHei", 9)
        page.drawString(64, y, label)
        page.setFillColorRGB(0, 0, 0)
        page.setFont("SimHei", 10.5)
        page.drawString(155, y, value)
        y -= 30

    page.setFillColorRGB(0.38, 0.42, 0.40)
    page.setFont("SimHei", 8.5)
    page.drawString(64, 62, "DataBase / homework01")

    page.showPage()
    page.save()
    buffer.seek(0)
    return buffer


def main():
    if not SOURCE_PDF.exists():
        raise FileNotFoundError(SOURCE_PDF)

    writer = PdfWriter()
    cover = PdfReader(build_cover())
    writer.add_page(cover.pages[0])

    report = PdfReader(str(SOURCE_PDF))
    if len(report.pages) < 2:
        raise ValueError("源报告页数不足")
    for source_page in report.pages[1:]:
        writer.add_page(source_page)

    writer.add_metadata(
        {
            "/Title": "基于 MongoDB 的在线问卷系统第一阶段项目完成报告",
            "/Author": "徐文杰",
            "/Subject": "2026 ECNU PJ1 第一阶段项目报告",
            "/Keywords": "MongoDB, Flask, 在线问卷, AI 使用说明",
        }
    )
    with OUTPUT_PDF.open("wb") as output:
        writer.write(output)
    print(OUTPUT_PDF)


if __name__ == "__main__":
    main()
