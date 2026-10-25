import json
from pathlib import Path

EVALS = Path(__file__).resolve().parent.parent / "evals"


def test_label_files_keep_the_fields_eval_reads():
    for name in ("labels.json", "labels2.json"):
        for c in json.loads((EVALS / name).read_text()):
            assert c["label"] in {"working", "distracted"}, (name, c["file"])
            assert isinstance(c["ambiguous"], bool) and isinstance(c["holdout"], bool), (name, c["file"])


def test_batch2_labels_are_marked_hand_checked():
    cases = json.loads((EVALS / "labels2.json").read_text())
    assert len(cases) == 23
    assert all(c["reviewed_by_human"] is True and c["reviewed_on"] == "2026-10-24" for c in cases)
