---
name: plain-questions
description: How to phrase any question to the user — grill-me rounds, AskUserQuestion choices, design decisions, "should I do X or Y?", clarifications. Load it BEFORE asking the user anything that needs a decision. Every question and every option must be in plain English, self-contained, and free of unexplained acronyms or jargon.
---

# Plain Questions

The user answers many questions in a row, often without the context you have just built up
by reading code and results. A question they have to decode first is a question they will
answer badly. Your job is to make each question **easy to understand on the first read**.

This applies to every question: `grill-me` rounds, `AskUserQuestion` calls, decisions raised
mid-implementation, and plain-text questions in a reply. It changes **how** you ask, not
**what** you ask — `grill-me` still decides the content.

## Rules

1. **Assume no context.** The user may have just come back from something else. Say in one
   or two sentences what we are doing and why this question comes up now.
2. **No unexplained acronyms or jargon.** The first time a term appears in a question, say
   what it means in everyday words (e.g. "VUS-PR — our main score, higher is better").
   If a plain word works, use it instead of the term.
3. **One idea per question.** If the question has an "and", split it.
4. **Say why it matters.** One line on what changes depending on the answer. If nothing
   changes, don't ask.
5. **Short sentences, common words.** Prefer "use", "check", "run" over "leverage",
   "validate", "instantiate". No nested clauses.
6. **Concrete over abstract.** Give a number, a file, or a small example instead of a
   general principle.
7. **Recommendation first** (as `grill-me` requires), with the reason in plain words.

## Options

Each option must be understandable **on its own**, without reading the others.

- **Label:** a short, plain name for the choice (1–5 words). No code names, flags, or
  variable names as the label.
- **Description:** what happens if the user picks it, and the main cost or risk — in one or
  two plain sentences. "This means…", "The downside is…".
- Options must be **really different** from each other. If two only differ in a detail,
  merge them or ask about the detail separately.
- Put the recommended option first and mark it "(Recommended)".
- The `header` chip (≤12 chars) names the topic in plain words ("Window size", not "sW").

## Checklist before sending

- [ ] Would someone who skipped the last hour understand the question?
- [ ] Is every acronym, file name, or technical term explained or removed?
- [ ] Does the user know why this matters and what each answer leads to?
- [ ] Can each option be understood without reading the others?
- [ ] Is there one clear recommendation with a plain reason?

If any box is unchecked, rewrite before asking.

## Example

**Bad**

> Q: For the MI probe, pool L12 via CLS or mean, and do we keep rank-1 `find_length` for sW?
> - CLS — cheaper
> - Mean — standard
> - Both

Two questions in one, three unexplained terms (MI, L12, sW), and the options don't say what
happens.

**Good**

> We are measuring how much information about anomalies each layer of the model holds.
> Each layer gives one vector per time step, but we need **one vector per window** of the
> series. How should we combine the per-step vectors into one?
>
> Why it matters: this choice changes the numbers we compare across layers, so we must fix
> it before running anything.
>
> - **Average them (Recommended)** — take the mean of all time steps. Simple, and it treats
>   every step the same. Downside: a short anomaly can get diluted.
> - **Use the summary token** — MOMENT (one of the models we test) has a special position
>   meant to summarize the whole window. Faster, but not every model has one, so the
>   comparison across models is less fair.

The window-size question goes in a separate question.