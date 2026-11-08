from html import escape
from pathlib import Path

from PyQt5.QtGui import QPainter, QTextDocument
from PyQt5.QtPrintSupport import QPrinter

from utilities.meal import Weekday
from utilities.weekly_plan import WeeklyPlan


def export_weekly_plan_pdf(
    plan: WeeklyPlan,
    weekdays: dict[int, Weekday],
    destination: Path,
    title: str,
    weekday_title: str,
    date_title: str,
    meal_title: str,
) -> None:
    rows = []
    for entry in plan.entries:
        day = weekdays[entry.weekday]
        current_date = plan.start.fromordinal(plan.start.toordinal() + entry.weekday - 1)
        rows.append(
            "<tr>"
            f"<td>{escape(day.name)}</td>"
            f"<td>{current_date:%d/%m/%Y}</td>"
            f"<td>{escape(entry.meal_name or '')}</td>"
            "</tr>"
        )
    html = f"""
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          body {{ font-family: sans-serif; color: #202020; }}
          h1 {{ color: #352060; text-align: center; }}
          h2 {{ text-align: center; font-weight: normal; }}
          table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
          th {{ background: #f28c28; color: white; }}
          th, td {{ border: 1px solid #888; padding: 10px; font-size: 13pt; }}
        </style>
      </head>
      <body>
        <h1>{escape(title)}</h1>
        <h2>{plan.start:%d/%m/%Y} – {plan.start.fromordinal(plan.start.toordinal() + 6):%d/%m/%Y}</h2>
        <table>
          <tr>
            <th>{escape(weekday_title)}</th>
            <th>{escape(date_title)}</th>
            <th>{escape(meal_title)}</th>
          </tr>
          {''.join(rows)}
        </table>
      </body>
    </html>
    """
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(destination))
    document = QTextDocument()
    document.setHtml(html)
    document.print_(printer)


def export_shopping_list_pdf(
    plan: WeeklyPlan,
    items,
    destination: Path,
    title: str,
    category_title: str,
    ingredient_title: str,
    quantity_title: str,
    unit_title: str,
    translate,
) -> None:
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{escape(translate(item.category))}</td>"
            f"<td>{escape(item.name)}</td>"
            f"<td>{escape(item.quantity_text())}</td>"
            f"<td>{escape(translate(item.unit)) if item.unit else ''}</td>"
            "</tr>"
        )
    html = f"""
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          body {{ font-family: sans-serif; color: #202020; }}
          h1 {{ color: #352060; text-align: center; }}
          h2 {{ text-align: center; font-weight: normal; }}
          table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
          th {{ background: #f28c28; color: white; }}
          th, td {{ border: 1px solid #888; padding: 3px; font-size: 9pt; }}
        </style>
      </head>
      <body>
        <h1>{escape(title)}</h1>
        <h2>{plan.start:%d/%m/%Y} – {plan.start.fromordinal(plan.start.toordinal() + 6):%d/%m/%Y}</h2>
        <table>
          <tr>
            <th>{escape(category_title)}</th>
            <th>{escape(ingredient_title)}</th>
            <th>{escape(quantity_title)}</th>
            <th>{escape(unit_title)}</th>
          </tr>
          {''.join(rows)}
        </table>
      </body>
    </html>
    """
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(destination))
    document = QTextDocument()
    document.documentLayout().setPaintDevice(printer)
    document.setHtml(html)
    page = printer.pageRect(QPrinter.DevicePixel)
    document.setTextWidth(page.width())
    scale = min(1.0, page.height() / document.size().height())
    painter = QPainter()
    if not painter.begin(printer):
        raise OSError(f"Could not create PDF: {destination}")
    try:
        painter.scale(scale, scale)
        document.drawContents(painter)
    finally:
        painter.end()
