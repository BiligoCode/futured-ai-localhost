import pytest

from app.slides_html import SlideTooLong, deck_material_text, sanitize_slide_html, slide_text, slide_title


def test_sanitize_keeps_whitelisted_markup():
    html = ('<h1 style="text-align: center">Τίτλος</h1>'
            '<ul><li><p><strong>a</strong> <em>b</em> <u>c</u> <mark>d</mark></p></li></ul>')
    assert sanitize_slide_html(html) == html


def test_sanitize_unwraps_unknown_tags_and_drops_unknown_styles():
    html = ('<div class="x"><p style="font-family: Arial; text-align: right; background: red">Hi '
            '<span style="color: #C93838; font-weight: bold; font-size: 34px">there</span></p></div>'
            '<script>alert(1)</script><table><tr><td>cell</td></tr></table>')
    assert sanitize_slide_html(html) == (
        '<p style="text-align: right">Hi <span style="color: #c93838; font-size: 34px">there</span></p>cell')


def test_sanitize_escapes_text_and_rejects_bad_values():
    assert sanitize_slide_html("<p>a < b &amp; c</p>") == "<p>a &lt; b &amp; c</p>"
    assert sanitize_slide_html('<span style="color: red; font-size: 200px">x</span>') == "<span>x</span>"
    assert sanitize_slide_html('<p style="text-align: justify">x</p>') == "<p>x</p>"


def test_sanitize_keeps_br_and_drops_style_content():
    assert sanitize_slide_html("<p>a<br>b</p><style>p{color:red}</style>") == "<p>a<br>b</p>"


def test_sanitize_maps_legacy_inline_tags_and_closes_implicit_items():
    assert sanitize_slide_html("<p><b>a</b> <i>b</i></p>") == "<p><strong>a</strong> <em>b</em></p>"
    assert sanitize_slide_html("<ul><li>a<li>b</ul>") == "<ul><li>a</li><li>b</li></ul>"
    assert sanitize_slide_html("<p>a<p>b") == "<p>a</p><p>b</p>"


def test_sanitize_too_long():
    with pytest.raises(SlideTooLong):
        sanitize_slide_html("<p>" + "x" * 20_001 + "</p>")


def test_slide_text_and_title():
    html = "<h1>Ταξινόμηση</h1><p>Εισαγωγή</p><ul><li><p>ένα</p></li><li>δύο</li></ul>"
    assert slide_text(html) == "Ταξινόμηση\nΕισαγωγή\n- ένα\n- δύο"
    assert slide_title(html) == "Ταξινόμηση"
    assert slide_title("<p>" + "λ" * 80 + "</p>") == "λ" * 60
    assert slide_title("") == ""


def test_slide_title_prefers_first_heading_and_decodes_entities():
    assert slide_title("<p>intro</p><h2>Α &amp; Β</h2>") == "Α & Β"


def test_deck_material_text():
    out = deck_material_text("Αλγόριθμοι", ["<h1>Α</h1><p>κείμενο</p>", "<p>μόνο σώμα</p>"])
    assert out == "Lecture slides: Αλγόριθμοι\n\nSlide 1: Α\nκείμενο\n\nSlide 2: μόνο σώμα\nμόνο σώμα"
