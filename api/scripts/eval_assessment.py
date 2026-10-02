"""Run the real assessment pipeline (Bedrock models) on a synthetic class and score it against the truth.

    cd api && uv run python scripts/make_exam_class.py /tmp/class
    cd api && uv run python scripts/eval_assessment.py /tmp/class [--grader zai.glm-5] [--vision …] [--verify …] [--no-exam]

Prints reading accuracy of definitive answers, grading accuracy, open-question error, copying and AI scores of the
planted cases, hidden-text detection and timings, and writes them to <class>/eval-<grader>.json."""
import argparse
import asyncio
import dataclasses
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.assess.answers import normalize_text  # noqa: E402
from app.assess.models import Question  # noqa: E402
from app.assess.similarity import final_value  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.main import create_app  # noqa: E402


def norm_label(label: str) -> str:
    text = normalize_text(label).replace("θεμα", "").replace("ερωτηση", "")
    return re.sub(r"[\s.()\-:]", "", text)


async def wait(c: httpx.AsyncClient, aid: str, until, timeout: float = 3600) -> dict:
    start = time.time()
    while True:
        a = (await c.get(f"/assessments/{aid}")).json()
        if until(a):
            return a
        if time.time() - start > timeout:
            raise TimeoutError("the pipeline did not finish in time")
        await asyncio.sleep(2)


async def run(args) -> dict:
    base = Path(args.class_dir)
    truth = json.loads((base / "truth.json").read_text(encoding="utf-8"))
    settings = load_settings()
    overrides = {k: v for k, v in (("grading_model", args.grader), ("vision_model", args.vision),
                                   ("verify_model", args.verify)) if v is not None}
    data_dir = Path(tempfile.mkdtemp(prefix="lara-eval-"))
    settings = dataclasses.replace(settings, data_dir=data_dir, **overrides)
    app = create_app(settings)
    timings = {}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://eval", timeout=600) as c:
            t0 = time.time()
            files = [] if args.no_exam else [("exam_files", ("exam.pdf", (base / "exam.pdf").read_bytes(), "application/pdf"))]
            r = await c.post("/assessments", data={"title": truth["title"], "language": args.language, "scale": "10"}, files=files)
            r.raise_for_status()
            aid = r.json()["id"]
            papers = sorted((base / "papers").glob("*.pdf"))
            r = await c.post(f"/assessments/{aid}/papers",
                             files=[("files", (p.name, p.read_bytes(), "application/pdf")) for p in papers])
            r.raise_for_status()
            a = await wait(c, aid, lambda a: a["rubric"]["status"] in ("draft", "failed", "confirmed"))
            timings["rubric_ready_s"] = round(time.time() - t0, 1)
            if a["rubric"]["status"] == "failed":
                raise RuntimeError(f"rubric failed: {a['rubric']['error']}")
            rubric = a["rubric"]["questions"]
            r = await c.put(f"/assessments/{aid}/rubric", json={"questions": rubric, "confirm": True})
            if r.status_code != 200:
                print("rubric could not be confirmed:", r.json()["detail"], "— fixing it from the truth")
                rubric = fix_rubric(rubric, truth)
                r = await c.put(f"/assessments/{aid}/rubric", json={"questions": rubric, "confirm": True})
                r.raise_for_status()
            a = await wait(c, aid, lambda a: not a["stats"]["busy"] and a["analysis"]["status"] in ("done", "failed"))
            timings["total_s"] = round(time.time() - t0, 1)
            details = {row["filename"]: (await c.get(f"/assessments/{aid}/papers/{row['id']}")).json() for row in a["papers"]}
    return report(truth, a, details, timings, data_dir)


def fix_rubric(rubric: list[dict], truth: dict) -> list[dict]:
    by_label = {norm_label(q["label"]): q for q in truth["questions"]}
    for q in rubric:
        t = by_label.get(norm_label(q["label"]))
        if t and t["type"] != "open":
            q["type"], q["answer"] = t["type"], t["key"]
    return rubric


def report(truth: dict, a: dict, details: dict, timings: dict, data_dir: Path) -> dict:
    rubric = a["rubric"]["questions"]
    by_label = {norm_label(q["label"]): q for q in rubric}
    out: dict = {"timings": timings, "data_dir": str(data_dir), "rubric": [], "students": []}
    print(f"\n=== Rubric ({len(rubric)} questions; truth {len(truth['questions'])}) — {a['rubric']['note'][:200]}")
    for tq in truth["questions"]:
        q = by_label.get(norm_label(tq["label"]))
        ok = q is not None and q["type"] == tq["type"] and abs(q["points"] - tq["points"]) < 1e-6 and \
            (tq["type"] == "open" or final_value(Question(**q), q["answer"]) == final_value(Question(**q), tq["key"]) or
             (tq["type"] == "short" and normalize_text(tq["key"]) in normalize_text(q["answer"])))
        out["rubric"].append({"label": tq["label"], "found": q is not None, "ok": bool(ok)})
        print(f"  {tq['label']:>3} {'OK ' if ok else 'BAD'} truth {tq['type']}/{tq['points']}/{tq['key']!r}  "
              f"got {(q['type'], q['points'], q['answer'], q['key_from']) if q else None}")
    read_ok = read_n = grade_ok = grade_n = flagged_wrong = 0
    open_err, total_err = [], []
    rows = {r["filename"]: r for r in a["papers"]}
    print("\n=== Papers")
    for s in truth["students"]:
        paper = details[s["file"]]
        row = rows[s["file"]]
        results = {r["question_id"]: r for r in paper["results"]}
        issues = []
        for tq in truth["questions"]:
            q = by_label.get(norm_label(tq["label"]))
            r = results.get(q["id"]) if q else None
            if r is None:
                issues.append(f"{tq['label']}: no result")
                continue
            got = r["override_final"] if r["override_final"] is not None else r["final"]
            question = Question(**q)
            if tq["type"] != "open":
                read_n += 1
                want = final_value(question, s["finals"][tq["label"]])
                same = final_value(question, got) == want or (tq["type"] == "short" and normalize_text(got or "") == normalize_text(s["finals"][tq["label"]]))
                read_ok += same
                if not same:
                    flagged = "readings_differ" in r["flags"] or r["confidence"] == "low"
                    flagged_wrong += flagged
                    issues.append(f"{tq['label']}: read {got!r} (2nd {r['second_final']!r}) want {s['finals'][tq['label']]!r}"
                                  + (" [flagged]" if flagged else ""))
                grade_n += 1
                expected = s["points"][tq["label"]]
                grade_ok += abs(r["points"] - expected) < 1e-6
            elif s["points"][tq["label"]] is not None:
                open_err.append(abs(r["points"] - s["points"][tq["label"]]))
                issues.append(f"{tq['label']}: open {r['points']} vs {s['points'][tq['label']]} — {r['feedback'][:120]}")
        if s["total"] is not None:
            total_err.append(abs((row["points"] or 0) - s["total"]))
        ai = paper.get("ai") or {}
        alerts = [f["code"] for f in (paper.get("forensics") or {}).get("findings", []) if f["severity"] == "alert"]
        rec = {"id": s["id"], "name_ok": normalize_text(row["student_name"]) == normalize_text(s["name"]),
               "student_name": row["student_name"], "student_id": row["student_id"], "points": row["points"],
               "truth": s["total"], "ai": row["ai_score"], "ai_level": ai.get("level"), "copy": row["copy_score"],
               "copy_match": row["copy_match"], "alerts": alerts, "flags": row["review_flags"], "issues": issues}
        out["students"].append(rec)
        print(f"  {s['id']} {row['student_name'][:24]:<24} {row['points']}/{s['total']}  AI {row['ai_score']} ({ai.get('level')})  "
              f"copy {row['copy_score']}  alerts {alerts}  flags {row['review_flags']}")
        for issue in issues:
            print(f"      {issue}")
    ids = {s["file"]: rows[s["file"]]["id"] for s in truth["students"]}
    sid_to_file = {s["id"]: s["file"] for s in truth["students"]}
    pair_scores = {(p["a"], p["b"]): p for p in a["analysis"]["pairs"]}

    def pair(x, y):
        k = tuple(sorted((ids[sid_to_file[x]], ids[sid_to_file[y]])))
        return pair_scores.get(k)
    planted = {f"{x}-{y}": (pair(x, y) or {}).get("score", 0) for x, y in truth["copy_pairs"]}
    planted_keys = {tuple(sorted((ids[sid_to_file[x]], ids[sid_to_file[y]]))) for x, y in truth["copy_pairs"]}
    others = max((p["score"] for k, p in pair_scores.items() if k not in planted_keys), default=0)
    out["metrics"] = {
        "reading_accuracy": round(read_ok / max(read_n, 1), 3), "reading_errors": read_n - read_ok,
        "reading_errors_flagged": flagged_wrong, "definitive_grading_accuracy": round(grade_ok / max(grade_n, 1), 3),
        "open_mae": round(sum(open_err) / max(len(open_err), 1), 3), "total_mae": round(sum(total_err) / max(len(total_err), 1), 3),
        "planted_copy_scores": planted, "max_other_pair": others,
        "ai_scores": {s["id"]: next(r["ai"] for r in out["students"] if r["id"] == s["id"]) for s in truth["students"]},
        "hidden_found": all("hidden_text" in next(r["alerts"] for r in out["students"] if r["id"] == h) for h in truth["hidden"]),
        "names_ok": sum(r["name_ok"] for r in out["students"]),
    }
    print("\n=== Metrics")
    for k, v in out["metrics"].items():
        print(f"  {k}: {v}")
    for p in a["analysis"]["pairs"][:8]:
        names = {v: k for k, v in ids.items()}
        print(f"  pair {names[p['a']]}–{names[p['b']]} {p['score']} {p['verdict']} {[e['code'] for e in p['evidence']]}")
    print(f"  insights: {a['analysis']['insights'][:300]}")
    print(f"  timings: {timings}")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("class_dir")
    parser.add_argument("--grader")
    parser.add_argument("--vision")
    parser.add_argument("--verify")
    parser.add_argument("--no-exam", action="store_true")
    parser.add_argument("--language", default="el", choices=["el", "en"])
    args = parser.parse_args()
    result = asyncio.run(run(args))
    name = (args.grader or "default").replace("/", "_").replace(":", "_")
    path = Path(args.class_dir) / f"eval-{name}{'-noexam' if args.no_exam else ''}-{args.language}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
