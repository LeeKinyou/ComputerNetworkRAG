from app.practice import answer_summary, is_correct, normalize_answer


def test_choice_answer_is_case_insensitive():
    assert is_correct("b", "B")
    assert is_correct(" B ", "B")
    assert normalize_answer("c") == "C"


def test_judge_answers_accept_chinese_and_english_tokens():
    assert is_correct("对", "T")
    assert is_correct("正确", "T")
    assert is_correct("TRUE", "T")
    assert is_correct("错误", "F")
    assert is_correct("false", "F")


def test_empty_or_missing_answer_is_wrong():
    assert not is_correct("", "A")
    assert not is_correct(None, "A")
    assert not is_correct("   ", "T")


def test_wrong_choice_is_graded_false():
    assert not is_correct("A", "B")


def test_summary_contains_given_and_expected():
    result = answer_summary("single", "c", "B")
    assert result == {"type": "single", "answer": "C", "expected": "B", "correct": False}
