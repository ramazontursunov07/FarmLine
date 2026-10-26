"""Davolash va vaksinatsiya tarixini PDF qilib beradi (veterinar, xaridor yoki bank uchun)."""
import io

from django.utils import timezone

TREATMENT_TYPES = ('kasallik', 'davolash', 'vaksinatsiya')


def _esc(text):
    return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def build_pdf(farm, events, title, period_text='', generated_by=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from apps.finance.report import FONT_DIR, GREEN

    if 'DejaVu' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('DejaVu', str(FONT_DIR / 'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('DejaVu-Bold', str(FONT_DIR / 'DejaVuSans-Bold.ttf')))
        pdfmetrics.registerFontFamily('DejaVu', normal='DejaVu', bold='DejaVu-Bold')

    green = colors.HexColor('#' + GREEN)
    grid = colors.HexColor('#D8D8D0')
    h1 = ParagraphStyle('h1', fontName='DejaVu-Bold', fontSize=15, leading=19, textColor=green)
    small = ParagraphStyle('small', fontName='DejaVu', fontSize=8, leading=10, textColor=colors.HexColor('#555555'))
    cell = ParagraphStyle('cell', fontName='DejaVu', fontSize=8, leading=10)

    who = (generated_by.get_full_name() or generated_by.username) if generated_by else ''
    story = [
        Paragraph(_esc(title), h1),
        Spacer(1, 2),
        Paragraph(
            f"{_esc(farm.name)} · {_esc(farm.location)}" + (f" · {period_text}" if period_text else '')
            + f" · Tayyorlandi: {timezone.localtime():%d.%m.%Y %H:%M}" + (f" · {_esc(who)}" if who else ''),
            small),
        Spacer(1, 8),
    ]

    rows = [['Sana', 'Hayvon', 'Turi', 'Nomi / tashxis', 'Dori', 'Ushlab turish', 'Holat', 'Yozgan']]
    for e in events:
        animal = f"№{e.animal.tag_number}" + (f" {e.animal.name}" if e.animal.name else '') if e.animal_id \
            else f"{e.animal_group.animal_type.name} ({e.animal_group.count} ta)"
        desc = _esc(e.title) + (
            f"<br/><font size=7 color='#555555'>{_esc(e.description)}</font>" if e.description else '')
        rows.append([
            f"{e.start_date:%d.%m.%Y}",
            Paragraph(_esc(animal), cell),
            e.get_event_type_display(),
            Paragraph(desc, cell),
            Paragraph(_esc(e.medicine.item_name) if e.medicine_id else '—', cell),
            f"{e.withdrawal_days} kun" if e.withdrawal_days else '—',
            e.get_status_display(),
            Paragraph(_esc((e.recorded_by.get_full_name() or e.recorded_by.username) if e.recorded_by else ''), cell),
        ])
    if len(rows) == 1:
        story.append(Paragraph("Bu davrda davolash yoki vaksinatsiya yozuvlari yo'q.", small))
    else:
        t = Table(rows, colWidths=[20 * mm, 34 * mm, 24 * mm, 62 * mm, 32 * mm, 22 * mm, 24 * mm, 29 * mm],
                  repeatRows=1)
        t.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'DejaVu', 8),
            ('FONT', (0, 0), (-1, 0), 'DejaVu-Bold', 8),
            ('BACKGROUND', (0, 0), (-1, 0), green),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, grid),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F6F6F1')]),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Jami yozuvlar: {len(rows) - 1}", small))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('DejaVu', 7)
        canvas.setFillColor(colors.HexColor('#777777'))
        canvas.drawString(15 * mm, 8 * mm, 'FarmLine')
        canvas.drawRightString(landscape(A4)[0] - 15 * mm, 8 * mm, f"{doc.page}-bet")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm, title=title, author='FarmLine'
                      ).build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
