// Mock data for the Sonora demo.
// Everything here is "derived from what was actually said" in a session —
// that is the product's core differentiator vs. slide/text-based tools.

export const DEMO_TRANSCRIPT = [
  { t: "00:12", speaker: "Trainer", text: "Welcome back everyone. Today is all about handling objections — not memorizing scripts, but understanding what an objection actually is." },
  { t: "00:41", speaker: "Trainer", text: "Here's the reframe I want you to leave with: an objection is not a rejection. It's a request for more information, or a sign of unmet fear." },
  { t: "01:20", speaker: "Participant", text: "But what about when they say it's just too expensive?" },
  { t: "01:28", speaker: "Trainer", text: "Great — 'too expensive' is almost never about price. It's about perceived value versus cost. Your job is to make the value visible before you ever defend the number." },
  { t: "02:05", speaker: "Trainer", text: "So the sequence is: acknowledge, ask, then reframe. Never jump straight to a counter-argument. If you argue, you win the point and lose the person." },
  { t: "03:11", speaker: "Trainer", text: "Let's practice the acknowledge step. Notice you're not agreeing — you're showing you heard them. 'I understand that the investment feels significant right now.'" },
  { t: "04:02", speaker: "Participant", text: "How long do you wait before asking the follow-up question?" },
  { t: "04:10", speaker: "Trainer", text: "A full breath. Silence does the work. Most people talk themselves into the answer if you just let the pause sit." },
  { t: "05:30", speaker: "Trainer", text: "Last thing for today: track your objections. Write down the three you hear most this week. Patterns are where the real coaching happens." },
];

export const DEMO_SCRIPT = {
  title: "Handling Objections — The Core Reframe",
  duration: "42 min session",
  summary:
    "This session reframed how to think about objections and gave the group a repeatable way to respond to them under pressure.",
  // A flowing overview written as connected prose, so a reader grasps the
  // broader lessons — not a list of isolated quotes.
  overview: [
    "The whole session turned on one idea: an objection is not a rejection. When someone pushes back, they are almost always asking for more information or revealing an unmet fear — not closing the door. Once you stop hearing objections as attacks, you stop reacting defensively, and that single shift changes every conversation that follows.",
    `From there the group worked through the most common objection of all — "it's too expensive." The lesson was that price complaints are rarely about money; they're about perceived value being lower than perceived cost. So the move is never to defend the number first. You make the value visible, and only then does the price look reasonable in comparison.`,
    `To do that consistently, the trainer introduced a simple sequence to run in the moment: acknowledge, then ask, then reframe. Acknowledging is not agreeing — it's showing the person you actually heard them ("I understand the investment feels significant right now"). Asking a genuine question buys you information and time. Reframing lands the new perspective. The warning was blunt: skip straight to a counter-argument and you win the point but lose the person.`,
    "A quieter but powerful technique threaded through the practice: let silence do the work. After you ask a question, wait a full breath instead of filling the gap. Most people will talk themselves toward the answer if you simply allow the pause to sit — the discomfort is doing your job for you.",
    "The session closed on something practical rather than theoretical. The real skill isn't memorizing lines, it's noticing patterns: write down the three objections you hear most this week. Those recurring objections are where the actual coaching — and the biggest gains — live.",
  ],
  // Kept for the "key takeaways" rail alongside the narrative.
  takeaways: [
    { text: "An objection is a request for information, not a rejection.", at: "00:41" },
    { text: '"Too expensive" is a value problem, not a price problem.', at: "01:28" },
    { text: "Respond in sequence: acknowledge → ask → reframe.", at: "02:05" },
    { text: "Acknowledge without agreeing.", at: "03:11" },
    { text: "After asking, let silence do the work.", at: "04:10" },
    { text: "Track your top three recurring objections.", at: "05:30" },
  ],
};

export const DEMO_QUIZ = [
  {
    q: "According to the session, an objection is best understood as…",
    options: [
      "A rejection of the offer",
      "A request for more information or a sign of unmet fear",
      "A negotiation tactic to lower the price",
      "A signal to end the conversation",
    ],
    correct: 1,
    source: "00:41",
    why: "The trainer explicitly reframed objections as requests for information, not rejections.",
  },
  {
    q: 'When a prospect says something is "too expensive," the session suggests the real issue is usually…',
    options: [
      "They genuinely cannot afford it",
      "They want a discount",
      "Perceived value versus cost",
      "A competitor offered less",
    ],
    correct: 2,
    source: "01:28",
    why: '"Too expensive" was framed as a value-perception problem, not a literal price problem.',
  },
  {
    q: "What is the correct order of the three-step response sequence?",
    options: [
      "Reframe → acknowledge → ask",
      "Ask → reframe → acknowledge",
      "Acknowledge → ask → reframe",
      "Counter → acknowledge → ask",
    ],
    correct: 2,
    source: "02:05",
    why: "The session defined the sequence as acknowledge, then ask, then reframe.",
  },
  {
    q: "How long should you pause after asking a follow-up question?",
    options: ["No pause — keep talking", "A full breath", "At least 30 seconds", "Until they look uncomfortable"],
    correct: 1,
    source: "04:10",
    why: "The trainer recommended waiting a full breath and letting silence do the work.",
  },
];

// ---- Chatbot mock ----
// The assistant first tries to answer from the lesson transcript. If the
// question isn't covered by what was said, it falls back to the web or its
// own general knowledge — and always tells the user which source it used.

export const CHAT_SUGGESTIONS = [
  "What's the three-step sequence again?",
  "Why is silence so effective?",
  "What did the trainer say about price?",
  "Any research backing this up?",
];

// Canned answers. `match` is a list of lowercase keywords; the first entry
// whose keywords all-or-any appear in the question wins.
export const CHAT_ANSWERS = [
  {
    match: ["sequence", "three", "step", "acknowledge", "order"],
    source: "lesson",
    answer:
      `The session laid out a three-step sequence to run in the moment: **acknowledge → ask → reframe**. Acknowledging shows you heard the person (without agreeing), asking a real question buys information and time, and reframing lands the new perspective. The trainer warned against skipping to a counter-argument — "you win the point and lose the person."`,
    cite: "02:05",
  },
  {
    match: ["silence", "pause", "wait", "quiet", "breath"],
    source: "lesson",
    answer:
      "The trainer recommended waiting **a full breath** after asking a question, and letting silence do the work. The idea is that the pause creates a little productive discomfort, and most people will talk themselves toward the answer if you simply don't rush to fill the gap.",
    cite: "04:10",
  },
  {
    match: ["expensive", "price", "cost", "money", "value"],
    source: "lesson",
    answer:
      `According to the session, "too expensive" is almost never really about money — it's a **value problem**. The complaint means perceived value is lower than perceived cost. So the move is to make the value visible *before* defending the number; once value is clear, the price looks reasonable by comparison.`,
    cite: "01:28",
  },
  {
    match: ["objection", "rejection", "reframe", "mindset"],
    source: "lesson",
    answer:
      "The core reframe of the whole session: **an objection is not a rejection.** It's a request for more information or a sign of an unmet fear. Once you stop hearing pushback as an attack, you respond with curiosity instead of defensiveness — which changes the entire conversation.",
    cite: "00:41",
  },
  {
    match: ["research", "study", "evidence", "science", "proof", "psychology"],
    source: "web",
    answer:
      `The session didn't cite specific studies, so here's context from outside the lesson: the "acknowledge before persuading" idea aligns with research on **active listening** and **tactical empathy** (popularized in Chris Voss's *Never Split the Difference*), and the pause technique echoes findings that comfortable silence increases disclosure in negotiation and therapeutic settings.`,
    cite: null,
  },
];

// Used when nothing matches — general-knowledge fallback.
export const CHAT_FALLBACK = {
  source: "knowledge",
  answer:
    "That wasn't covered in this session's transcript, so I'm answering from general knowledge rather than the lesson: I can give you a broadly reasonable take, but treat it as background rather than something the trainer actually said. Want me to tie it back to one of the points that *were* covered?",
  cite: null,
};
export const DEMO_SESSIONS = [
  { id: "s1", title: "Handling Objections — Sales Team Q3", date: "Sep 3, 2026", duration: "42 min", status: "ready", quizzes: 4 },
  { id: "s2", title: "Onboarding Workshop — Cohort 14", date: "Aug 28, 2026", duration: "1h 08m", status: "ready", quizzes: 6 },
  { id: "s3", title: "Feedback That Sticks — Leadership", date: "Aug 21, 2026", duration: "55 min", status: "ready", quizzes: 5 },
  { id: "s4", title: "Difficult Conversations — Coaching Group", date: "Aug 12, 2026", duration: "1h 22m", status: "ready", quizzes: 7 },
];

// Content for each demo session. s1 uses the full DEMO_SCRIPT/DEMO_QUIZ/DEMO_TRANSCRIPT above.
export const SESSION_CONTENT = {
  s1: {
    script: DEMO_SCRIPT,
    quiz: DEMO_QUIZ,
    transcript: DEMO_TRANSCRIPT,
  },
  s2: {
    script: {
      title: "Onboarding Workshop — First 90 Days",
      duration: "1h 08m session",
      summary: "Walked the new cohort through the first-90-days framework and set clear expectations for ramp milestones.",
      overview: [
        "The session opened with a single orienting question: what does 'fully ramped' actually mean here? The facilitator argued that most onboarding fails not because of missing information, but because new hires spend the first month guessing at what success looks like. Getting that definition explicit and agreed on — in writing — is the first deliverable.",
        "From there the group mapped out the 30/60/90-day arc. The first 30 days are listen-only: learn the product, shadow deals, sit in on team rituals. The second 30 days are contribute-with-guidance: take tasks with a buddy, run your first customer call, get your first piece of real feedback. The third 30 days are own-and-report: carry your own workload, flag blockers early, present a retrospective at day 90.",
        `A recurring theme was the cost of silent confusion. New hires who don't ask questions aren't learning faster — they're falling behind quietly. The facilitator introduced a low-friction check-in: a one-sentence daily Slack note to a buddy. Not a status report, just proof of loop-closing: "I was confused about X, I found out it means Y."`,
        "The session closed by asking each person to name one assumption they arrived with that turned out to be wrong. The answers filled a whiteboard. That exercise — surfacing bad assumptions early — is now baked into the day-three agenda for every future cohort.",
      ],
      takeaways: [
        { text: "Define 'fully ramped' in writing before day one.", at: "04:15" },
        { text: "Days 1–30: listen only. Resist the urge to fix things.", at: "09:40" },
        { text: "Days 31–60: contribute with a named buddy.", at: "18:02" },
        { text: "Days 61–90: own your workload, present a day-90 retro.", at: "24:30" },
        { text: "Daily one-sentence Slack note closes feedback loops early.", at: "38:55" },
        { text: "Surface wrong assumptions on day three — before they calcify.", at: "51:10" },
      ],
    },
    quiz: [
      {
        q: "According to the session, why does most onboarding fail?",
        options: [
          "Not enough training materials",
          "New hires guess at what success looks like",
          "Managers are too busy to help",
          "The product is too complex",
        ],
        correct: 1,
        source: "04:15",
        why: "The facilitator said onboarding fails because new hires spend the first month guessing at what success looks like — not because of missing information.",
      },
      {
        q: "What is the rule for the first 30 days?",
        options: ["Fix what looks broken", "Listen only", "Run your first customer call", "Present a retrospective"],
        correct: 1,
        source: "09:40",
        why: "Days 1–30 are explicitly 'listen-only' — resist the urge to fix things.",
      },
      {
        q: "What is the purpose of the daily one-sentence Slack note?",
        options: [
          "To write a status report for your manager",
          "To prove you worked that day",
          "To close feedback loops by sharing one confusion resolved",
          "To ask for help with blockers",
        ],
        correct: 2,
        source: "38:55",
        why: "The note is framed as proof of loop-closing: 'I was confused about X, I found out it means Y.'",
      },
    ],
    transcript: [
      { t: "00:05", speaker: "Trainer", text: "Welcome, Cohort 14. Before we touch any tools or processes, I want to answer the question nobody asks: what does fully ramped actually mean here?" },
      { t: "04:15", speaker: "Trainer", text: "Most onboarding fails not because of missing info — you'll get buried in wikis and Notion pages. It fails because new hires spend the first month guessing at what success looks like." },
      { t: "09:40", speaker: "Trainer", text: "First 30 days: listen only. I mean it. You will want to fix things. Don't. You don't know enough yet to know what's already been tried." },
      { t: "18:02", speaker: "Participant", text: "What counts as 'contributing with guidance'?" },
      { t: "18:14", speaker: "Trainer", text: "You have a named buddy. You take tasks together. You run your first customer call — they're in the room. You get feedback before the call, not after." },
      { t: "38:55", speaker: "Trainer", text: "The Slack note is one sentence. 'I was confused about X, I found out it means Y.' That's it. Not a status report. Just proof you're closing loops." },
      { t: "51:10", speaker: "Trainer", text: "Day three, we're going to ask you what assumptions you arrived with that turned out to be wrong. Write them down tonight." },
    ],
  },
  s3: {
    script: {
      title: "Feedback That Sticks — Leadership Programme",
      duration: "55 min session",
      summary: "Explored why most feedback evaporates within a week, and gave leaders a two-part structure for making it land and stay.",
      overview: [
        "The session started with a question that made the room uncomfortable: can you name a piece of feedback you received more than six months ago that actually changed how you work? Most people couldn't. The facilitator's point was that forgettable feedback isn't neutral — it's a missed intervention that the person has to pay for later.",
        "The root problem, the session argued, is that most feedback is event-driven and abstract. It fires after something went wrong, and it describes character rather than behavior. 'You need to be more strategic' tells the listener nothing actionable. 'In Monday's meeting, you skipped the why before proposing the solution — next time, spend 90 seconds on context first' tells them exactly what to do differently.",
        "To fix this, the facilitator introduced a two-part structure: situation + specific ask. State the observable situation in one sentence. Then make one specific, behavioural ask. No rating, no score, no summary judgment. The ask has to be concrete enough that the person could replay it in their next meeting.",
        "The session closed on timing. Feedback given within 24 hours has roughly double the retention of feedback given at a quarterly review. The recommendation was blunt: shrink the gap. A 90-second conversation the day after is worth more than a structured review six weeks later.",
      ],
      takeaways: [
        { text: "Forgettable feedback is a missed intervention — not neutral.", at: "03:20" },
        { text: "Most feedback is event-driven and describes character, not behaviour.", at: "11:45" },
        { text: "Structure: one-sentence situation + one specific behavioural ask.", at: "22:10" },
        { text: "The ask must be concrete enough to replay in the next meeting.", at: "28:35" },
        { text: "Feedback within 24 hours has roughly 2× the retention.", at: "41:00" },
      ],
    },
    quiz: [
      {
        q: "Why is forgettable feedback described as a 'missed intervention'?",
        options: [
          "Because it makes the person feel bad",
          "Because the person has to pay for the gap later",
          "Because it wastes the manager's time",
          "Because it creates resentment",
        ],
        correct: 1,
        source: "03:20",
        why: "The facilitator said forgettable feedback isn't neutral — it's a missed intervention the person has to pay for later.",
      },
      {
        q: "What is wrong with feedback like 'you need to be more strategic'?",
        options: [
          "It is too harsh",
          "It describes character rather than observable behaviour",
          "It is too vague to be motivating",
          "Both B and C",
        ],
        correct: 3,
        source: "11:45",
        why: "The session argued this kind of feedback is both abstract (no behaviour, just character) and not actionable.",
      },
      {
        q: "Compared to a quarterly review, when does feedback have roughly double the retention?",
        options: ["Within the same day", "Within 24 hours", "Within one week", "Within one month"],
        correct: 1,
        source: "41:00",
        why: "The facilitator stated that feedback given within 24 hours has roughly 2× the retention of feedback given at a quarterly review.",
      },
    ],
    transcript: [
      { t: "00:10", speaker: "Trainer", text: "I want you to think of a piece of feedback you received more than six months ago that actually changed how you work. Take a moment." },
      { t: "03:20", speaker: "Trainer", text: "Most people can't name one. And that's the problem. Forgettable feedback isn't neutral — it's a missed intervention that the person has to pay for later." },
      { t: "11:45", speaker: "Trainer", text: "'You need to be more strategic.' What does that mean? It describes a character trait, not a behaviour. There is nothing to replay." },
      { t: "22:10", speaker: "Trainer", text: "Here's the structure: one sentence describing the observable situation, then one specific behavioural ask. Two parts. That's it." },
      { t: "28:35", speaker: "Participant", text: "How specific does the ask need to be?" },
      { t: "28:44", speaker: "Trainer", text: "Concrete enough that they could replay it in their next meeting. If they can't picture doing it, it's still too abstract." },
      { t: "41:00", speaker: "Trainer", text: "Feedback within 24 hours has roughly double the retention of a quarterly review. Shrink the gap. A 90-second conversation the next day is worth more than a structured session six weeks later." },
    ],
  },
  s4: {
    script: {
      title: "Difficult Conversations — Coaching Group",
      duration: "1h 22m session",
      summary: "Worked through why people avoid hard conversations, and gave the group a concrete opening move to start them without the usual spiral.",
      overview: [
        "The session opened with a survey: name a conversation you've been putting off for more than two weeks. Every hand went up. The facilitator's observation was that avoidance is almost never about cowardice — it's about not having a move to open with. People know the conversation needs to happen; they just don't know how to start it without it immediately becoming a fight.",
        "The core insight was that most difficult conversations go wrong in the first thirty seconds, not the middle. The person delivers a verdict rather than an invitation. 'This isn't working' or 'I need to talk to you about your attitude' are verdicts — they put the listener on trial before the conversation has started. An invitation sounds different: 'I noticed something last week and I want to understand it better — do you have 15 minutes?'",
        "From there, the group practised the opening move: one observable fact, framed as something you want to understand rather than something you've already judged. The rule was explicit — no adjectives in the first sentence. Adjectives are opinions. 'You were dismissive in that meeting' is an opinion. 'In Tuesday's meeting you spoke over three people' is a fact you can both look at together.",
        "The session closed on the idea of the two-conversation rule: if the same topic has come up twice without resolution, it deserves a dedicated conversation rather than another hint. Hints feel safer but they accumulate frustration without moving anything. The third time is a formal conversation, scheduled in advance, with the topic named in the invite.",
      ],
      takeaways: [
        { text: "Avoidance is about lacking an opening move, not cowardice.", at: "05:30" },
        { text: "Most conversations go wrong in the first 30 seconds — the opener sets the frame.", at: "14:20" },
        { text: "Deliver an invitation, not a verdict.", at: "14:20" },
        { text: "No adjectives in the first sentence — facts only.", at: "28:00" },
        { text: "Same topic twice without resolution = schedule a dedicated conversation.", at: "58:15" },
        { text: "Name the topic in the calendar invite — no ambiguous 'quick chat'.", at: "01:04:40" },
        { text: "Hints accumulate frustration without moving anything.", at: "58:15" },
      ],
    },
    quiz: [
      {
        q: "According to the session, why do people avoid difficult conversations?",
        options: [
          "They are afraid of conflict",
          "They don't care about the outcome",
          "They lack an opening move to start without it becoming a fight",
          "They prefer to handle things by email",
        ],
        correct: 2,
        source: "05:30",
        why: "The facilitator argued avoidance is almost never cowardice — it's about not having a move to open with.",
      },
      {
        q: "What is the difference between a 'verdict' and an 'invitation' opener?",
        options: [
          "A verdict is longer",
          "A verdict puts the listener on trial; an invitation asks to understand together",
          "An invitation is more polite",
          "There is no practical difference",
        ],
        correct: 1,
        source: "14:20",
        why: "Verdicts ('This isn't working') put the listener on trial before the conversation starts. Invitations frame it as wanting to understand.",
      },
      {
        q: "Why are adjectives banned from the opening sentence?",
        options: [
          "They make sentences too long",
          "Adjectives are opinions, not facts you can both examine",
          "They sound too formal",
          "They confuse the listener",
        ],
        correct: 1,
        source: "28:00",
        why: "'Dismissive' is an opinion. 'Spoke over three people' is a fact. The opening sentence must be something both parties can look at together.",
      },
      {
        q: "What is the 'two-conversation rule'?",
        options: [
          "Never have the same conversation twice",
          "Always bring a witness to hard conversations",
          "If the same topic has come up twice without resolution, schedule a formal dedicated conversation",
          "Two conversations per week maximum",
        ],
        correct: 2,
        source: "58:15",
        why: "If the same topic has appeared twice without resolution, hints are not enough — schedule a formal conversation with the topic named in the invite.",
      },
    ],
    transcript: [
      { t: "00:15", speaker: "Trainer", text: "Name a conversation you've been putting off for more than two weeks. Everyone put your hand up." },
      { t: "05:30", speaker: "Trainer", text: "Every hand went up. And my point is: this isn't cowardice. It's that you don't have a move to open with. People know it needs to happen. They just can't start it without it becoming a fight." },
      { t: "14:20", speaker: "Trainer", text: "'This isn't working.' 'I need to talk to you about your attitude.' Those are verdicts. You've put them on trial before the conversation has started. An invitation sounds like: 'I noticed something and I want to understand it better — do you have 15 minutes?'" },
      { t: "28:00", speaker: "Trainer", text: "Rule for your first sentence: no adjectives. Adjectives are opinions. 'You were dismissive' — that's yours. 'In Tuesday's meeting you spoke over three people' — that's a fact we can both look at." },
      { t: "35:10", speaker: "Participant", text: "What if they just deny the fact?" },
      { t: "35:20", speaker: "Trainer", text: "Then you have new information. Either they saw it differently or they're not ready. Both are useful. The conversation hasn't failed — it's just started." },
      { t: "58:15", speaker: "Trainer", text: "Two-conversation rule: same topic twice without movement — that's a pattern. Stop hinting. Schedule a dedicated conversation. Name the topic in the invite." },
    ],
  },
};

// Generate a new session entry after a recording is stopped.
export function createNewSession(durationSeconds) {
  const mins = Math.floor(durationSeconds / 60);
  const secs = durationSeconds % 60;
  const duration = mins > 0 ? (secs > 0 ? `${mins}m ${secs}s` : `${mins} min`) : `${secs}s`;
  const now = new Date();
  const dateStr = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const id = "session-" + Date.now();
  return {
    id,
    title: "New Session — " + dateStr,
    date: dateStr,
    duration,
    status: "ready",
    quizzes: DEMO_QUIZ.length,
  };
}
