"""Exports (design §1): a CSV of the marks for spreadsheets and LMS upload, and a PDF report — the class summary and
one page per student that can be handed back."""
import csv
import html
import io
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.assess.models import Assessment, Paper
from app.assess.scoring import effective_points, grade_of, paper_points
from app.assess.stats import compute_stats
from app.deck_export import safe_filename
from app.slides_pdf import font_css

MEDIA_TYPES = {"csv": "text/csv; charset=utf-8", "pdf": "application/pdf",
               "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

TEXT = {
    "en": {
        "student": "Student", "id": "Student ID", "file": "File", "status": "Status", "points": "Points", "max": "Maximum",
        "grade": "Grade (/{scale})", "ai": "AI-likeness (/100)", "copy": "Copying (/100)", "match": "Most similar to",
        "flags": "Questions to check", "alerts": "Document alerts", "reviewed": "Reviewed", "note": "Note", "yes": "yes", "no": "no",
        "report": "Assessment report", "papers": "papers", "mean": "Average", "median": "Median", "pass": "Pass rate",
        "graded": "Graded", "questions": "Questions", "question": "Question", "type": "Type", "avg": "Average",
        "correct": "Correct", "insights": "Class insights", "recommendations": "Recommendations",
        "integrity": "Integrity signals", "pairs": "Pairs worth a look", "none": "None.",
        "answer": "Answer", "feedback": "Feedback", "summary": "Summary", "caution": "Scores are signals for a conversation, not proof.",
        "comment": "Professor's comment", "distribution": "Grade distribution",
        "ai_list": "Papers with AI-likeness signals", "doc_alerts": "Document alerts",
        "findings": {"hidden_text": "hidden text", "addresses_grader": "text addressed to an AI grader",
                     "ai_artifact": "chatbot leftovers", "invisible_chars": "invisible characters", "mixed_script": "look-alike letters",
                     "ai_image": "AI-made image"},
        "status_names": {
            "queued": "queued", "reading": "reading", "read": "read", "grading": "grading", "graded": "graded", "failed": "failed"},
        "types": {"true_false": "true/false", "multiple_choice": "multiple choice", "numeric": "numeric", "short": "short answer", "open": "open"},
        "result": {"correct": "✓", "incorrect": "✗", "partial": "◐", "unanswered": "—", "unreadable": "?"},
    },
    "el": {
        "student": "Φοιτητής/τρια", "id": "ΑΜ", "file": "Αρχείο", "status": "Κατάσταση", "points": "Μονάδες", "max": "Μέγιστο",
        "grade": "Βαθμός (/{scale})", "ai": "Ένδειξη AI (/100)", "copy": "Αντιγραφή (/100)", "match": "Πιο όμοιο με",
        "flags": "Ερωτήσεις για έλεγχο", "alerts": "Ειδοποιήσεις εγγράφου", "reviewed": "Ελέγχθηκε", "note": "Σημείωση", "yes": "ναι", "no": "όχι",
        "report": "Αναφορά αξιολόγησης", "papers": "γραπτά", "mean": "Μέσος όρος", "median": "Διάμεσος", "pass": "Ποσοστό επιτυχίας",
        "graded": "Βαθμολογήθηκαν", "questions": "Ερωτήσεις", "question": "Ερώτηση", "type": "Τύπος", "avg": "Μέση επίδοση",
        "correct": "Σωστές", "insights": "Η εικόνα της τάξης", "recommendations": "Προτάσεις",
        "integrity": "Ενδείξεις ακεραιότητας", "pairs": "Ζεύγη για έλεγχο", "none": "Κανένα.",
        "answer": "Απάντηση", "feedback": "Σχόλιο", "summary": "Σύνοψη", "caution": "Οι βαθμολογίες είναι ενδείξεις για συζήτηση, όχι αποδείξεις.",
        "comment": "Σχόλιο διδάσκοντα", "distribution": "Κατανομή βαθμών",
        "ai_list": "Γραπτά με ενδείξεις AI", "doc_alerts": "Ειδοποιήσεις αρχείων",
        "findings": {"hidden_text": "κρυφό κείμενο", "addresses_grader": "κείμενο προς βαθμολογητή AI",
                     "ai_artifact": "υπολείμματα chatbot", "invisible_chars": "αόρατοι χαρακτήρες", "mixed_script": "όμοια γράμματα άλλων αλφαβήτων",
                     "ai_image": "εικόνα από AI"},
        "status_names": {
            "queued": "σε αναμονή", "reading": "ανάγνωση", "read": "διαβάστηκε", "grading": "βαθμολόγηση", "graded": "βαθμολογήθηκε", "failed": "απέτυχε"},
        "types": {"true_false": "σωστό/λάθος", "multiple_choice": "πολλαπλής επιλογής", "numeric": "αριθμητική", "short": "σύντομη", "open": "ανάπτυξης"},
        "result": {"correct": "✓", "incorrect": "✗", "partial": "◐", "unanswered": "—", "unreadable": "?"},
    },
}


def _t(a: Assessment) -> dict:
    return TEXT["el" if a.language == "el" else "en"]


def _num(x: float | None, language: str = "en") -> str:
    """A number as the report's readers write it: 7,5 in Greek, 7.5 in English (CSV keeps the point)."""
    if x is None:
        return ""
    text = f"{round(x, 2):g}"
    return text.replace(".", ",") if language == "el" else text


def grade_table(a: Assessment, papers: list[Paper]) -> tuple[list[str], list[list[object]]]:
    """The marks as a header and rows of plain values (numbers stay numbers)."""
    t = _t(a)
    by_id = {p.id: p for p in papers}
    names = {p.id: p.student_name or p.filename for p in papers}
    questions = a.rubric.questions
    header = [t["student"], t["id"], t["file"], t["status"], *[f"{t['question']} {q.label} (/{q.points:g})" for q in questions],
              t["points"], t["max"], t["grade"].format(scale=a.scale), t["ai"], t["copy"], t["match"], t["flags"],
              t["alerts"], t["reviewed"], t["note"]]
    rows: list[list[object]] = []
    for row in a.papers:
        p = by_id.get(row.id)
        marks: list[object] = []
        for q in questions:
            r = p.result(q.id) if p else None
            marks.append(min(effective_points(r), q.points) if r is not None and row.status == "graded" else None)
        rows.append([row.student_name, row.student_id, row.filename, t["status_names"].get(row.status, row.status), *marks,
                     row.points, row.max_points, row.grade, row.ai_score, row.copy_score,
                     names.get(row.copy_match, "") if row.copy_match and (row.copy_score or 0) >= 30 else "",
                     row.review_flags, row.alerts, t["yes"] if row.reviewed else t["no"], p.note if p else ""])
    return header, rows


def grades_xlsx(a: Assessment, papers: list[Paper]) -> bytes:
    """The marks as an Excel workbook: numbers are numbers, so no decimal-comma or separator trouble in any locale."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    header, rows = grade_table(a, papers)
    wb = Workbook()
    ws = wb.active
    ws.title = (_t(a)["report"])[:31]
    ws.append(header)
    for row in rows:
        ws.append(row)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B2"
    for i, title in enumerate(header, start=1):
        values = [str(r[i - 1]) for r in rows if r[i - 1] is not None]
        ws.column_dimensions[get_column_letter(i)].width = min(40, max(8, len(title) * 0.6, *(len(v) + 2 for v in values)))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def grades_csv(a: Assessment, papers: list[Paper]) -> bytes:
    t = _t(a)
    by_id = {p.id: p for p in papers}
    names = {p.id: p.student_name or p.filename for p in papers}
    questions = a.rubric.questions
    out = io.StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow([t["student"], t["id"], t["file"], t["status"], *[f"{t['question']} {q.label} (/{q.points:g})" for q in questions],
                t["points"], t["max"], t["grade"].format(scale=a.scale), t["ai"], t["copy"], t["match"], t["flags"],
                t["alerts"], t["reviewed"], t["note"]])
    for row in a.papers:
        p = by_id.get(row.id)
        marks = []
        for q in questions:
            r = p.result(q.id) if p else None
            marks.append(_num(min(effective_points(r), q.points)) if r is not None and row.status == "graded" else "")
        w.writerow([row.student_name, row.student_id, row.filename, t["status_names"].get(row.status, row.status), *marks,
                    _num(row.points), _num(row.max_points), _num(row.grade), _num(row.ai_score), _num(row.copy_score),
                    names.get(row.copy_match, "") if row.copy_match and (row.copy_score or 0) >= 30 else "",
                    row.review_flags, row.alerts, t["yes"] if row.reviewed else t["no"], p.note if p else ""])
    return ("﻿" + out.getvalue()).encode("utf-8")  # the BOM makes Excel read Greek correctly


def _e(text: str | None) -> str:
    return html.escape(text or "", quote=False)


REPORT_CSS = """
@page { size: A4; margin: 18mm 16mm 18mm; @bottom-right { content: counter(page) " / " counter(pages); font: 9pt Commissioner, sans-serif; color: #8a94a3 } }
body { font-family: Commissioner, "DejaVu Sans", sans-serif; font-size: 10pt; color: #18212e; line-height: 1.4 }
h1, h2, h3 { font-family: "STIX Two Text", "DejaVu Serif", serif; font-weight: 600; margin: 0 0 6pt }
h1 { font-size: 22pt } h2 { font-size: 15pt; margin-top: 14pt } h3 { font-size: 12pt; margin-top: 10pt }
.muted { color: #566173 } .small { font-size: 8.5pt }
.kpis { display: flex; gap: 8pt; margin: 10pt 0 } .kpi { flex: 1; border: 1px solid #d7dce3; border-radius: 6pt; padding: 6pt 8pt }
.kpi b { display: block; font-size: 15pt; font-family: "STIX Two Text", serif }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 } th, td { text-align: left; vertical-align: top; padding: 4pt 5pt; border-bottom: 1px solid #e8ecf0 }
th { font-size: 8.5pt; color: #566173; font-weight: 600; border-bottom: 1px solid #b9c2cd }
.bars { display: flex; align-items: flex-end; gap: 3pt; height: 70pt; margin: 6pt 0 2pt }
.bar { flex: 1; background: #1b6f8c; border-radius: 2pt 2pt 0 0 } .bar.fail { background: #b9c2cd }
.axis { display: flex; gap: 3pt } .axis span { flex: 1; text-align: center; font-size: 7.5pt; color: #8a94a3 }
.student { page-break-before: always }
.grade { font-family: "STIX Two Text", serif; font-size: 20pt; font-weight: 600 }
.ok { color: #0f7b6c } .bad { color: #c93838 } .part { color: #74490a }
.note { border-left: 3px solid #e2a13b; background: #fbf1dd; padding: 5pt 8pt; margin: 8pt 0; color: #74490a; font-size: 9pt }
"""


def _histogram(a: Assessment, stats) -> str:
    top = max((b.count for b in stats.histogram), default=0) or 1
    bars = "".join(f'<div class="bar{" fail" if b.end <= a.scale / 2 else ""}" style="height:{max(2, b.count / top * 100):.0f}%"></div>'
                   for b in stats.histogram)
    axis = "".join(f"<span>{_num(b.start, a.language)}–{_num(b.end, a.language)}</span>" for b in stats.histogram)
    return f'<div class="bars">{bars}</div><div class="axis">{axis}</div>'


def report_html(a: Assessment, papers: list[Paper]) -> str:
    t = _t(a)
    stats = compute_stats(a)
    by_id = {p.id: p for p in papers}
    names = {p.id: p.student_name or p.filename for p in papers}
    qstats = {q.question_id: q for q in stats.questions}
    pct = lambda x: "" if x is None else f"{round(x * 100)}%"  # noqa: E731
    lang = a.language
    num = lambda x: _num(x, lang)  # noqa: E731
    parts = [f"<h1>{_e(a.title)}</h1>",
             f'<p class="muted">{_e(a.course)}{" · " if a.course else ""}{_e(t["report"])} · {datetime.now():%d/%m/%Y} · '
             f'{stats.total} {_e(t["papers"])}</p>',
             '<div class="kpis">'
             f'<div class="kpi"><b>{num(stats.mean)}</b>{_e(t["mean"])} (/{a.scale})</div>'
             f'<div class="kpi"><b>{num(stats.median)}</b>{_e(t["median"])}</div>'
             f'<div class="kpi"><b>{pct(stats.pass_rate)}</b>{_e(t["pass"])}</div>'
             f'<div class="kpi"><b>{stats.graded}/{stats.total}</b>{_e(t["graded"])}</div></div>',
             f"<h2>{_e(t['distribution'])}</h2>", _histogram(a, stats)]
    def correct(qid: str) -> str:
        qs = qstats.get(qid)
        if qs is None or qs.correct_rate is None or qs.mean_pct is None or abs(qs.correct_rate - qs.mean_pct) < 0.005:
            return ""
        return pct(qs.correct_rate)

    rows = "".join(f"<tr><td>{_e(q.label)}</td><td>{_e(t['types'][q.type])}</td><td>{num(q.points)}</td>"
                   f"<td>{pct(qstats[q.id].mean_pct) if q.id in qstats else ''}</td>"
                   f"<td>{correct(q.id)}</td>"
                   f"<td class='small'>{_e(a.analysis.question_insights.get(q.id, ''))}</td></tr>" for q in a.rubric.questions)
    parts.append(f"<h2>{_e(t['questions'])}</h2><table><tr><th>{_e(t['question'])}</th><th>{_e(t['type'])}</th>"
                 f"<th>{_e(t['max'])}</th><th>{_e(t['avg'])}</th><th>{_e(t['correct'])}</th><th></th></tr>{rows}</table>")
    if a.analysis.insights:
        parts.append(f"<h2>{_e(t['insights'])}</h2><p>{_e(a.analysis.insights)}</p>")
    if a.analysis.recommendations:
        parts.append(f"<h3>{_e(t['recommendations'])}</h3><ul>" +
                     "".join(f"<li>{_e(r)}</li>" for r in a.analysis.recommendations) + "</ul>")
    flagged = [p for p in a.analysis.pairs if p.score >= 30][:12]
    parts.append(f"<h2>{_e(t['integrity'])}</h2><p class='note'>{_e(t['caution'])}</p><h3>{_e(t['pairs'])}</h3>")
    if flagged:
        parts.append("<table>" + "".join(
            f"<tr><td>{_e(names.get(p.a, p.a))} ↔ {_e(names.get(p.b, p.b))}</td><td>{p.score}/100</td>"
            f"<td class='small'>{_e(p.explanation)}</td></tr>" for p in flagged) + "</table>")
    else:
        parts.append(f"<p class='muted'>{_e(t['none'])}</p>")
    ai = sorted((r for r in a.papers if (r.ai_score or 0) >= 30 and r.ai_level != "insufficient"), key=lambda r: -(r.ai_score or 0))
    parts.append(f"<h3>{_e(t['ai_list'])}</h3>")
    parts.append("<table>" + "".join(f"<tr><td>{_e(r.student_name or r.filename)}</td><td>{r.ai_score}/100</td></tr>" for r in ai)
                 + "</table>" if ai else f"<p class='muted'>{_e(t['none'])}</p>")
    docs = [r for r in a.papers if r.alerts]
    parts.append(f"<h3>{_e(t['doc_alerts'])}</h3>")
    parts.append("<table>" + "".join(f"<tr><td>{_e(r.student_name or r.filename)}</td><td>{', '.join(_e(t['findings'].get(f, f)) for f in r.findings)}</td></tr>"
                                     for r in docs) + "</table>" if docs else f"<p class='muted'>{_e(t['none'])}</p>")

    questions = a.rubric.questions
    for row in a.papers:
        p = by_id.get(row.id)
        if p is None or row.status != "graded":
            continue
        points, maximum = paper_points(p, a)
        grade = grade_of(points, maximum, a.scale)
        lines = []
        for q in questions:
            r = p.result(q.id)
            if r is None:
                continue
            cls = {"correct": "ok", "incorrect": "bad", "partial": "part"}.get(r.status, "muted")
            answer = r.answer or r.final or ""
            comment = f"<br><i>{_e(t['comment'])}: {_e(r.comment)}</i>" if r.comment else ""
            lines.append(f"<tr><td>{_e(q.label)}</td><td class='{cls}'>{t['result'][r.status]}</td>"
                         f"<td>{num(min(effective_points(r), q.points))}/{num(q.points)}</td>"
                         f"<td class='small'>{_e(answer[:260])}</td><td class='small'>{_e(r.feedback)}{comment}</td></tr>")
        head = f"{_e(p.student_name or p.filename)}" + (f" <span class='muted'>({_e(p.student_id)})</span>" if p.student_id else "")
        parts.append(
            f"<section class='student'><h2>{head}</h2><p><span class='grade'>{num(grade)}</span> / {a.scale} · "
            f"{num(points)}/{num(maximum)} {_e(t['points'])}</p>"
            + (f"<p><b>{_e(t['summary'])}:</b> {_e(p.summary)}</p>" if p.summary else "")
            + f"<table><tr><th>{_e(t['question'])}</th><th></th><th>{_e(t['points'])}</th><th>{_e(t['answer'])}</th>"
            f"<th>{_e(t['feedback'])}</th></tr>{''.join(lines)}</table>"
            + (f"<p class='small muted'>{_e(t['note'])}: {_e(p.note)}</p>" if p.note else "") + "</section>")
    return (f'<!doctype html><html lang="{a.language}"><head><meta charset="utf-8"><style>{font_css()}{REPORT_CSS}</style>'
            f"</head><body>{''.join(parts)}</body></html>")


def report_pdf(a: Assessment, papers: list[Paper]) -> bytes:
    from weasyprint import HTML  # slow to import; only needed for exports

    return HTML(string=report_html(a, papers)).write_pdf()


def export_assessment(out_dir: Path, a: Assessment, papers: list[Paper], fmt: Literal["csv", "xlsx", "pdf"]) -> tuple[Path, str]:
    name = safe_filename(a.title)
    if fmt == "xlsx":
        path = out_dir / "grades.xlsx"
        path.write_bytes(grades_xlsx(a, papers))
        return path, f"{name}.xlsx"
    if fmt == "csv":
        path = out_dir / "grades.csv"
        path.write_bytes(grades_csv(a, papers))
        return path, f"{name}.csv"
    path = out_dir / "report.pdf"
    path.write_bytes(report_pdf(a, papers))
    return path, f"{name}.pdf"
