from app.profile import build_profile_payload, profile_prompt, summarize_concepts

CONCEPTS = [
    {"id": "tcp", "title": "TCP", "chapter_id": "ch_04"},
    {"id": "arp", "title": "ARP", "chapter_id": "ch_02"},
    {"id": "tls", "title": "TLS", "chapter_id": "ch_06"},
    {"id": "cidr", "title": "CIDR", "chapter_id": "ch_03"},
]
QUESTION_CONCEPTS = {
    "q1": "arp",
    "q2": "arp",
    "q3": "tls",
    "q4": "tls",
    "q5": "tcp",
    "q6": "tcp",
    "q7": "tcp",
    "q8": "tcp",
}


def test_no_attempts_means_no_prompt_and_all_untried():
    items = summarize_concepts(CONCEPTS, QUESTION_CONCEPTS, [])
    assert all(item["state"] == "no_data" for item in items)

    profile = build_profile_payload(items, "demo_user")
    assert profile["attempts"] == 0
    assert profile["accuracy"] == 0
    assert profile_prompt(profile) == ""
    assert [item["concept_id"] for item in profile["untried"]] == ["tcp", "arp", "tls", "cidr"]


def test_weak_normal_and_mastered_are_split():
    attempts = [
        {"question_id": "q1", "is_correct": False},
        {"question_id": "q2", "is_correct": False},
        {"question_id": "q3", "is_correct": True},
        {"question_id": "q4", "is_correct": True},
        {"question_id": "q5", "is_correct": True},
        {"question_id": "q6", "is_correct": True},
        {"question_id": "q7", "is_correct": True},
        {"question_id": "q8", "is_correct": False},
    ]
    items = summarize_concepts(CONCEPTS, QUESTION_CONCEPTS, attempts)
    profile = build_profile_payload(items, "demo_user")

    assert profile["attempts"] == 8
    assert profile["accuracy"] == 62  # 5/8 = 62.5，round 半值取偶
    assert [item["concept_id"] for item in profile["weak"]] == ["arp"]
    assert profile["weak"][0]["rate"] == 0
    assert next(item for item in profile["concepts"] if item["concept_id"] == "tcp")["state"] == "normal"
    assert [item["concept_id"] for item in profile["strong"]] == ["tls"]
    assert [item["concept_id"] for item in profile["untried"]] == ["cidr"]
    assert profile["weak_chapters"] == ["ch_02", "ch_03"]


def test_prompt_mentions_weak_and_untried_but_not_raw_lists_of_all_concepts():
    attempts = [
        {"question_id": "q1", "is_correct": False},
        {"question_id": "q2", "is_correct": False},
        {"question_id": "q3", "is_correct": True},
        {"question_id": "q4", "is_correct": True},
    ]
    items = summarize_concepts(CONCEPTS, QUESTION_CONCEPTS, attempts)
    profile = build_profile_payload(items, "demo_user")
    prompt = profile_prompt(profile)

    assert "薄弱：" in prompt
    assert "ARP（0%，2 题）" in prompt
    assert "还没练过：TCP、CIDR" in prompt
    assert "不要在回答里罗列这些统计" in prompt


def test_concept_without_any_attempt_is_not_counted_in_accuracy():
    attempts = [{"question_id": "q3", "is_correct": True}]
    items = summarize_concepts(CONCEPTS, QUESTION_CONCEPTS, attempts)
    profile = build_profile_payload(items, "demo_user")

    assert profile["attempts"] == 1
    assert profile["accuracy"] == 100
    assert profile["covered"] == 1
    assert profile["untried"][0]["concept_id"] == "tcp"
