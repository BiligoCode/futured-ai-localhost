import json

import pytest

from app.models import Cut, SceneDraft, Segment
from app.revise import RevisionError, parse_timestamps, plan_revision
from app.store import ProjectStore
from tests.fakes import STORYBOARD_JSON, ScriptedLLM


def project(tmp_path):
    drafts = [SceneDraft(**s) for s in json.loads(STORYBOARD_JSON)["scenes"]]
    p = ProjectStore(tmp_path).create(title="t", concept="gd", style="", language="el", material_text="m",
                                      scenes=drafts)
    cut = Cut(status="done", version=1, duration=40,
              segments=[Segment(scene_id=s.id, start=i * 10, end=(i + 1) * 10) for i, s in enumerate(p.scenes)])
    return p, cut


def reply(*edits):
    return json.dumps({"edits": list(edits)}, ensure_ascii=False)


def test_parse_timestamps():
    assert parse_timestamps("at 0:32 and 1:05, not 10:61 or 12:30:00") == [32, 65]


def test_routes_to_the_part_and_hints_timestamps(tmp_path):
    p, cut = project(tmp_path)
    llm = ScriptedLLM([reply({"part": 3, "animation": True, "instruction": "Move the dot slower",
                              "narration": None, "summary": "Πιο αργή κίνηση"})])
    edits = plan_revision(llm, p, "στο 0:25 να πηγαίνει πιο αργά", cut=cut, at_seconds=12)
    assert [(e.scene_id, e.animation, e.instruction, e.narration) for e in edits] == [
        (p.scenes[2].id, True, "Move the dot slower", None)]
    brief = llm.calls[0][1][0]["content"]
    assert "0:25 in the request falls in part 3" in brief and "was at 0:12 (part 2)" in brief
    assert "Part 3 (0:20–0:30)" in brief


def test_narration_only_change(tmp_path):
    p, cut = project(tmp_path)
    llm = ScriptedLLM([reply({"part": 1, "animation": False, "instruction": "", "narration": "Νέο κείμενο.",
                              "summary": "Νέα αφήγηση"})])
    [edit] = plan_revision(llm, p, "πες το πιο απλά στην αρχή", cut=cut)
    assert (edit.scene_id, edit.animation, edit.narration) == (p.scenes[0].id, False, "Νέο κείμενο.")


def test_invalid_part_is_retried(tmp_path):
    p, cut = project(tmp_path)
    good = reply({"part": 2, "animation": True, "instruction": "x", "summary": "s"})
    llm = ScriptedLLM([reply({"part": 9, "animation": True, "instruction": "x", "summary": "s"}), good])
    assert plan_revision(llm, p, "change it", cut=cut)[0].scene_id == p.scenes[1].id
    assert "part 9 does not exist" in llm.calls[1][1][-1]["content"]


def test_falls_back_to_timestamp_when_model_fails(tmp_path):
    p, cut = project(tmp_path)
    [edit] = plan_revision(ScriptedLLM(["nope", "still nope"]), p, "at 0:32 make it red", cut=cut)
    assert (edit.scene_id, edit.instruction) == (p.scenes[3].id, "at 0:32 make it red")


def test_fails_without_any_pointer(tmp_path):
    p, cut = project(tmp_path)
    with pytest.raises(RevisionError):
        plan_revision(ScriptedLLM(["nope", "nope"]), p, "make it red", cut=cut)
