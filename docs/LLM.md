# LLM usage

Sonora uses one local model, served by [Ollama](https://ollama.com), for everything that
needs language understanding. The default is **Qwen3.5-9B** (`qwen3.5:9b`, 6.6 GB at
Q4_K_M, native 256K context, German and English).

| Task | Where | Output | Reasoning | Sampling |
|---|---|---|---|---|
| Notes (long lectures only) | `ai/generation.py` | timestamped key points per chunk | off | default |
| Recap script | `ai/generation.py` | title, summary, overview, takeaways, questions | off | default |
| Quiz | `ai/generation.py` | 3-8 questions, answer + 3 distractors each | off | default |
| Topics | `ai/analysis.py` | topic titles + start timestamps | off | presence penalty 0 |
| Scores (3 judgements, median) | `ai/analysis.py` | content, rhetoric, structure: assessment, score 1-10, tip | off | temperature 0.3, presence penalty 0 |
| Chat answer | `ai/chat.py` | answer, source, timestamp | off | default |

"Default" sampling is Qwen3.5's recommendation for answers without reasoning:
temperature 0.7, top_p 0.8, top_k 20, presence penalty 1.5 (`SONORA_LLM_TEMPERATURE`,
`_TOP_P`, `_TOP_K`, `_PRESENCE_PENALTY`). Every call sends `think` explicitly, because
Qwen3.5 reasons ("thinks") by default.

## How the prompts are built

- **Same prefix for every task.** All tasks on one lecture share the system prompt, and the
  transcript comes first in the user message with the task after it. Ollama reuses its
  cache of the identical prefix: on the reference GPU the 6,200-token transcript of a
  29-minute lecture took 4.5 s to read for the first task and 0.2-0.8 s for every further
  task. Instructions after a long document also work better than before it.
- **Transcripts are data.** They are fenced in `<transcript>` tags and every prompt says to
  ignore instructions inside them (anyone in the room can speak). The model has no tools.
- **Constrained, then validated.** Each call passes a JSON schema as Ollama's `format`;
  the result is still validated and normalised: lengths are bounded, duplicates dropped,
  timestamps snapped onto real transcript segments (within 30 s, else discarded), quiz
  options assembled and shuffled on the server, scores checked to be integers 1-10.
- **Reasoning fields first.** In the score schema the `assessment` comes before the
  `score`, so the model writes its justification before committing to a number.
- **The model only judges.** Topic durations, time shares and speaking pace are computed
  from the transcript, never by the model. The prompt also states whether the pace is
  below, within or above the typical 110-160 words/min instead of leaving the comparison
  to the model: given only the number, 1 of 20 judgements of a 157 words/min lecture
  called it "slightly faster than the typical range" (the Docker test run showed the same
  slip); with the verdict, 0 of 20, at unchanged scores.
- **Output caps.** Each call has a `num_predict` limit sized to its task, so a repetition
  loop ends in a retry instead of running until the context is full.
- **Long lectures.** When a transcript doesn't fit `SONORA_LLM_CONTEXT_TOKENS`, it is first
  condensed chunk by chunk into timestamped notes (map), and the tasks run on the notes.

## Measured decisions

Measured with `qwen3.5:9b` (Q4_K_M, Ollama 0.35, RTX 2080 8 GB, 16K context) on two
synthetic lectures with known topic boundaries: a well-structured 29-minute English
lecture and a deliberately rambling 20-minute German one.

| Question | Result | Decision |
|---|---|---|
| Does reasoning ("thinking") improve the scores? | Same scores (good lecture 9/8/8 with and without), but 3,600-5,000 extra tokens and 7-9x the time (136-188 s instead of ~20 s per call); on longer lectures the reasoning would not fit the context | No reasoning for any task |
| Does the presence penalty (1.5) hurt numeric output? | Scores: one severe outlier in 9 runs (rhetoric 10 for the rambling lecture, otherwise 3-4); none in 18 runs without penalty. Topic boundaries: slightly more accurate without (median error 16 vs 18 s and 95 vs 165 s) | Penalty 0 for scores and topics |
| ...and the timestamps in recap and quiz? | Cited segment exactly right: 79% with penalty, 67% without | Keep Qwen's default (1.5) for prose tasks |
| How stable are single score judgements? | Any temperature: about ±1 point between runs (spread up to 2) | Median of 3 judgements per category (repeats reuse the cached prompt), temperature 0.3 |
| Greedy decoding (temperature 0) for scores? | Deterministic, but a deterministic failure would repeat identically on every retry | Not used |
| Does the model tell good from bad lectures? | Good lecture: 8-9 in every category; rambling lecture: 4-5 / 3-4 / 2-3, with specific, polite feedback in the lecture's language | - |
| Does the chat stay on the lecture's subject? (chat is public on share links) | Lecture on memory plus a short Spanish lesson, every question twice. "Decline requests unrelated to the subject" declined 4 of 10 unrelated requests: poems and essays, but not trivia or translations. "Only help with the lecture and its subject; decline anything else, even a short factual question" declined 10 of 12. All 12 related questions the lectures didn't cover were still answered (translations included in the Spanish lesson), and all 6 covered ones cited the lecture. A variant that also called applying the lecture to one's own studies on-topic refused such a request once and declined fewer (7 of 10) | The stricter rule. It saves GPU time, but it's no security boundary: the rate limits are. Known quirk: requests like "make me a study plan from the lecture" are answered, sometimes after "I can only help with this lecture" |

Rerun the opt-in integration tests after changing prompts or models:
`uv run pytest -m integration` (needs Ollama with the model; see `tests/integration`).

## Choosing a different model

`SONORA_LLM_MODEL` takes any Ollama model. Things to check:

- **Memory.** The model plus its context cache must fit the GPU, or Ollama splits it with the
  CPU and gets slower. `qwen3.5:9b` with 16K context runs 84% on an 8 GB GPU; use 32K
  context with 12 GB or more (the Docker default). `qwen3.5:27b` (17 GB) needs a 24 GB+ GPU.
- **Sampling.** The defaults are Qwen3.5's recommendations. For other model families, set
  the four `SONORA_LLM_*` sampling values to that model's recommended non-reasoning values.
- **Reasoning.** Every call states `think` explicitly (currently always `false`, see the
  measurements above); a task can opt in per call. If a model can't reason, Ollama says so
  ("does not support thinking") and the client continues without the flag. The former
  `SONORA_LLM_THINK` setting no longer exists and is ignored if still set.
- **Context window.** `SONORA_LLM_CONTEXT_TOKENS` must stay the same for all calls (a
  change makes Ollama reload the model); the Docker setup starts Ollama with the same value.
