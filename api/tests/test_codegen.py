import manim

from app.codegen import build_system_prompt, generate_code, precheck, repair_code, revise_code, target_seconds
from app.models import Scene
from tests.fakes import VALID_CODE, ScriptedLLM


def test_target_seconds():
    assert target_seconds(" ".join(["w"] * 25)) == 10
    assert target_seconds("too short") == 6


def test_system_prompt_rules():
    p = build_system_prompt("el")
    for s in ["GeneratedScene", 'font="DejaVu Sans"', "MathTex", manim.__version__, "Greek",
              "Never write the narration as on-screen text", "font_size"]:
        assert s in p


def test_precheck():
    assert precheck(VALID_CODE) is None
    assert precheck("def (").startswith("SyntaxError")
    assert precheck("x = 1") == "Code must define class GeneratedScene"


def test_generate_code_prompt_and_extraction():
    llm = ScriptedLLM([f"```python\n{VALID_CODE}\n```"])
    scene = Scene(id="s", title="T", visual="Draw a parabola", narration=" ".join(["w"] * 25))
    code = generate_code(llm, scene, concept="gd", style="minimal", material="M" * 20_000, language="el")
    assert code == VALID_CODE.strip()
    user = llm.calls[0][1][0]["content"]
    assert "Draw a parabola" in user and "10 seconds" in user
    assert "M" * 8000 in user and "M" * 8001 not in user


def test_repair_sends_error_tail():
    llm = ScriptedLLM([VALID_CODE])
    repair_code(llm, "bad", "E" * 5000 + "TAIL", language="en")
    msg = llm.calls[0][1][0]["content"]
    assert "TAIL" in msg and "E" * 3001 not in msg


def test_revise_includes_instruction_and_code():
    llm = ScriptedLLM([VALID_CODE])
    revise_code(llm, "OLD_CODE", Scene(id="s", title="t", visual="v", narration="n"),
                "make the arrow red", language="el")
    msg = llm.calls[0][1][0]["content"]
    assert "OLD_CODE" in msg and "make the arrow red" in msg
