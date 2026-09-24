from sonora.ai.retrieval import BM25, Passage, build_passages, rank_passages, tokenize
from sonora.ai.text import chunk_lines, estimate_tokens, language_instruction, transcript_lines

SEGMENTS = [
    {"start": 12.0, "text": "Welcome back everyone, today is about objections."},
    {"start": 41.0, "text": "An objection is not a rejection."},
    {"start": 250.0, "text": "Wait a full breath. Silence does the work."},
    {"start": 330.0, "text": "Track the three objections you hear most this week."},
]


def test_estimate_tokens_is_conservative_and_never_zero() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 300) == 100


def test_transcript_lines_are_timestamped() -> None:
    assert transcript_lines(SEGMENTS)[2] == "[04:10] Wait a full breath. Silence does the work."


def test_chunk_lines_respects_budget_without_splitting_lines() -> None:
    lines = [f"line {i} " + "x" * 30 for i in range(10)]  # ~14 tokens each
    chunks = chunk_lines(lines, max_tokens=40)
    assert [line for chunk in chunks for line in chunk] == lines
    assert all(sum(estimate_tokens(line) + 1 for line in chunk) <= 40 for chunk in chunks)
    assert chunk_lines(["y" * 500], max_tokens=10) == [["y" * 500]]  # oversized line stays whole
    assert chunk_lines([], max_tokens=10) == []


def test_language_instruction() -> None:
    assert language_instruction("de") == "Write every text field in German."
    assert language_instruction("DE") == "Write every text field in German."
    assert "same language as the transcript" in language_instruction(None)
    assert "same language as the transcript" in language_instruction("xx")


def test_tokenize_drops_stopwords_case_and_punctuation() -> None:
    assert tokenize("What did the trainer say about PRICE?") == ["trainer", "say", "about", "price"]
    assert tokenize("Was hat der Trainer über den Preis gesagt?") == ["trainer", "preis", "gesagt"]


def test_build_passages_groups_consecutive_segments() -> None:
    passages = build_passages(SEGMENTS, max_chars=120)
    assert [p.start for p in passages] == [12.0, 250.0]
    assert passages[0].text.splitlines() == [
        "[00:12] Welcome back everyone, today is about objections.",
        "[00:41] An objection is not a rejection.",
    ]
    assert build_passages([], max_chars=100) == []


def test_rank_passages_finds_the_relevant_part() -> None:
    passages = build_passages(SEGMENTS, max_chars=60)
    best = rank_passages(passages, "How long should the silence be?")
    assert best[0].start == 250.0
    assert rank_passages(passages, "quantum chromodynamics") == []
    assert rank_passages(passages, "what is the") == []  # only stopwords
    assert rank_passages([], "silence") == []


def test_bm25_prefers_rare_terms_and_normalises_length() -> None:
    documents = [["price", "value", "value"], ["value"] * 20, ["silence"]]
    scores = BM25(documents).scores(["price", "value"])
    assert scores[0] > scores[1] > 0
    assert scores[2] == 0
    assert BM25([]).scores(["x"]) == []


def test_passage_is_immutable() -> None:
    passage = Passage(1.0, "text")
    assert passage == Passage(1.0, "text")
