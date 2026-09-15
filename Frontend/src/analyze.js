// Client-side analysis of a raw transcript string → session content.
// No backend needed. Uses simple NLP heuristics.

// Split raw transcript text into timestamped lines.
// Input: array of { time: Date, text: string, isFinal: boolean }
// Output: SESSION_CONTENT-compatible object
export function analyzeTranscript(entries, durationSeconds) {
  if (!entries || entries.length === 0) {
    return null;
  }

  // Build display transcript lines
  const transcript = entries
    .filter((e) => e.text.trim().length > 0)
    .map((e, i) => ({
      t: formatTime(e.offsetSeconds ?? i * 8),
      speaker: "Speaker",
      text: e.text.trim(),
    }));

  const fullText = entries.map((e) => e.text).join(" ");
  const sentences = splitSentences(fullText);

  // Pick a title from the first meaningful sentence
  const firstSentence = sentences.find((s) => s.split(" ").length > 4) ?? "Recording";
  const title = truncate(firstSentence, 60);

  // Summary: first 2 sentences joined
  const summary = sentences.slice(0, 2).join(" ") || "Recorded session.";

  // Overview: group sentences into ~4 paragraphs
  const overview = groupIntoParagraphs(sentences, 4);

  // Takeaways: sentences that sound like key points
  const takeaways = extractTakeaways(sentences, transcript);

  // Quiz: generate questions from key sentences
  const quiz = generateQuiz(sentences, transcript);

  const now = new Date();
  const dateStr = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  return {
    sessionMeta: {
      title: title + " — " + dateStr,
      date: dateStr,
      duration: formatDuration(durationSeconds),
      quizzes: quiz.length,
    },
    content: {
      script: { title, duration: formatDuration(durationSeconds) + " session", summary, overview, takeaways },
      quiz,
      transcript,
    },
  };
}

// ---- helpers ----

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  if (s === 0) return `${m} min`;
  return `${m}m ${s}s`;
}

function truncate(str, max) {
  if (str.length <= max) return str;
  return str.slice(0, max - 1).trimEnd() + "…";
}

function splitSentences(text) {
  return text
    .replace(/([.!?])\s+/g, "$1\n")
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 10);
}

function groupIntoParagraphs(sentences, count) {
  if (sentences.length === 0) return ["Nothing was detected in this recording."];
  const size = Math.max(1, Math.ceil(sentences.length / count));
  const paragraphs = [];
  for (let i = 0; i < sentences.length; i += size) {
    const chunk = sentences.slice(i, i + size).join(" ");
    if (chunk.trim()) paragraphs.push(chunk);
  }
  return paragraphs.slice(0, count);
}

function extractTakeaways(sentences, transcript) {
  // Prefer shorter, declarative sentences as takeaways
  const scored = sentences
    .map((s, i) => ({ s, i, score: scoreAsTakeaway(s) }))
    .sort((a, b) => b.score - a.score);

  return scored.slice(0, Math.min(5, scored.length)).map((item) => {
    const tLine = transcript[Math.floor((item.i / sentences.length) * transcript.length)];
    return { text: truncate(item.s, 90), at: tLine?.t ?? "00:00" };
  });
}

function scoreAsTakeaway(s) {
  let score = 0;
  const words = s.split(" ").length;
  // Prefer medium-length sentences
  if (words >= 8 && words <= 20) score += 2;
  // Prefer sentences with strong verbs / actionable language
  if (/\b(is|are|should|must|need|have|always|never|key|important|remember|make sure)\b/i.test(s)) score += 1;
  // Prefer sentences that start with a subject
  if (/^[A-Z]/.test(s)) score += 1;
  return score;
}

function generateQuiz(sentences, transcript) {
  // Pick 3 good candidate sentences for questions
  const candidates = sentences
    .filter((s) => s.split(" ").length >= 8 && s.split(" ").length <= 30)
    .slice(0, 12);

  if (candidates.length < 2) {
    return [{
      q: "What was the main topic discussed in this session?",
      options: [
        truncate(sentences[0] ?? "The recorded topic", 60),
        "A completely unrelated topic",
        "No clear topic was mentioned",
        "The session was about introductions only",
      ],
      correct: 0,
      source: transcript[0]?.t ?? "00:00",
      why: "This was stated at the beginning of the session.",
    }];
  }

  return candidates.slice(0, 3).map((sentence, i) => {
    const tLine = transcript[Math.floor((i / candidates.length) * transcript.length)];
    const words = sentence.split(" ");
    // Blank out a key word (roughly the middle noun/verb)
    const blankIdx = Math.floor(words.length * 0.6);
    const blankedWord = words[blankIdx];
    const questionText = words.map((w, wi) => (wi === blankIdx ? "___" : w)).join(" ");

    // Wrong options: nearby sentences truncated
    const wrong = candidates
      .filter((_, ci) => ci !== i)
      .slice(0, 3)
      .map((s) => truncate(s.split(" ").slice(0, 6).join(" ") + "…", 60));

    const options = shuffle([blankedWord, ...wrong.slice(0, 3)]);
    const correct = options.indexOf(blankedWord);

    return {
      q: `Complete the sentence from the session: "${questionText}"`,
      options,
      correct,
      source: tLine?.t ?? "00:00",
      why: `This was said verbatim in the session at ${tLine?.t ?? "the beginning"}.`,
    };
  });
}

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
