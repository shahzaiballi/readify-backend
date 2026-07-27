# Readify

An AI reading companion that takes a book and turns it into a daily habit instead of another thing sitting half-read on a shelf.

## Why we built this

Everyone owns books they never finished. Usually it's not laziness, it's one of a few recurring problems:

- You open a 300-page book with zero sense of how long it'll actually take, so it never gets scheduled into your day.
- Even when you do read, most of it is gone from memory within a week.
- There's nobody to talk to about it. Reading ends up being a solitary, low-feedback activity.

## What it actually does

You give Readify a book — either upload your own PDF or pick one from the catalog — and it:

- Breaks it into a day-by-day reading plan based on how much time you actually have (15 to 60 minutes a day).
- Generates content per chapter depending on what you're using the book for — a quick summary, key concepts, flashcards, or exam-style questions.
- Pings you four times a day with something relevant: a hook in the morning, a concept at midday, a story or quote in the afternoon, a recap in the evening. The idea is to keep the book present in your day rather than something you only think about at bedtime.
- Lets you just ask the book a question — "what does the author say about fear?" — and get an answer pulled from the actual pages, not a guess.
- Puts you in a group chat with other people reading the same book, if you want that.

## Four ways to read the same book

A student cramming for an exam and a founder skimming for ideas shouldn't get the same output from the same book. So you pick a mode when you add a book:

- **Skim** — one sharp sentence per chapter. For when you just need the gist.
- **Concept** — every named idea, framework, or principle in the book. Good if you want the vocabulary, not the story.
- **Deep** — the full treatment: overview, key points, examples, why it matters.
- **Exam** — five Q&A pairs per chapter, aimed at people who need to actually be tested on this.

## What using it looks like

1. Sign up with email or Google.
2. Upload a PDF or pick something from the catalog, and set your daily time budget and mode.
3. Readify shows you the chapters it detected — you confirm or fix them before anything else happens.
4. You get a plan: something like "you'll finish this in 21 days at 30 minutes a day."
5. Each day you open the app, read what's queued up, and mark it done.
6. Along the way you can pull summaries, ask questions, get your four notifications, or jump into a community chat.
7. Streaks, pages read, books finished — all tracked so you can see the habit forming.

## Under the hood

### Stack

Backend is Django 4.x with DRF, PostgreSQL for storage, Celery + Redis for anything that shouldn't block a request, and Celery Beat firing a nightly job at 23:00 UTC for notifications. The mobile client is Flutter.

For AI, we use DeepSeek V3 for actual generation and Google Gemini's free embeddings model (`text-embedding-004`, 768-dim) for the semantic search side. Similarity search is done with plain cosine similarity in NumPy — no pgvector, nothing extra to install. PDFs are parsed with PyMuPDF, images with Pillow. Media sits on Cloudinary in production. Deployment is Gunicorn behind a standard Heroku-style Procfile.

### How the code is organized

```
readify_backend/
├── apps/
│   ├── users/              # custom user model, email + Google OAuth
│   ├── books/               # books, chapters, chunks, schedules, upload pipeline
│   ├── library/             # per-user library and progress
│   ├── reading/             # reading sessions and plans
│   ├── community/           # groups, membership, messages, reactions
│   └── book_intelligence/   # the AI side: profiles, summaries, RAG, notifications, Q&A
├── config/
│   ├── settings/            # base / development / production
│   └── celery.py
└── requirements/
```

## The pipeline that runs on every upload

Uploading a book kicks off seven stages, most of them background jobs:

1. **Extract & detect** — PyMuPDF pulls the text out, and we try to figure out the chapter structure (more on this below). Status flips to `AWAITING_CONFIRM`.
2. **You review it** — the app shows you what it found so you can fix anything before committing to it. No backend work happens here, it's just waiting on you.
3. **Build the schedule** — plain math turns chapters into day-by-day chunks.
4. **Book brief** — one DeepSeek call, fed chapter titles and opening lines, produces a short "what this book is, what it argues, top ideas, verdict."
5. **First few summaries** — chapters 1–3 get generated up front in your chosen mode. Everything after that is generated the first time you actually reach it, not before.
6. **Notifications** — a nightly job writes tomorrow's four notification pieces for every active user/book pair.
7. **Q&A** — this one only runs when you actually ask something, using retrieval over the book's text.

## Figuring out the chapters

This part mattered more than it sounds like it should. Instead of throwing the whole book at an AI model and hoping for the best, we lean on whatever structure the PDF already gives us and only reach for AI when there's nothing else to go on:

| Method | What it does | Covers | AI needed |
|---|---|---|---|
| PDF bookmarks | Reads the embedded table of contents most PDFs already have | ~60% of books | None |
| Text pattern matching | Regex against the first 30 pages looking for TOC-shaped lines | ~25% of books | None |
| AI on sampled pages | Sends openings from every 8th page to DeepSeek | ~13% of books | A little |
| Fixed split | Chops the book into equal-sized chunks | ~2% of books | None |

After that, a blocklist strips out the stuff that isn't actually the book — table of contents, preface, index, bibliography, and so on. Then one more AI pass checks each remaining chapter is genuinely content (not something that slipped past the blocklist) and swaps a generic label like "Chapter 3" for something descriptive, based on how the chapter actually opens.

## Keeping AI calls cheap and fast

We set ourselves one rule early on and stuck to it everywhere: **don't send more than 8,000 words to the model in a single call.** Big prompts aren't just expensive — they're slower and more likely to produce something vague or wrong. So every call is scoped down to roughly the minimum it needs:

| Call | What's actually sent | Rough size |
|---|---|---|
| Classifying the book | First 2,000 characters | ~300 words |
| Detecting chapters (AI path) | Sampled page openings | ~1,500 words |
| Renaming/validating chapters | First 100 words of each chapter | ~2,000 words |
| Book brief | Titles + first 150 words per chapter | ~800 words |
| Chapter summary | Chapter text, capped | ≤6,000 words |
| A chapter over 8k words | Split into 6k sections, each summarized, then merged | ≤6,000 words per call |
| Daily notifications | First 3,000 characters of tomorrow's reading | ~500 words |
| Q&A | Top 3 retrieved chunks + last 3 conversation turns | ~3,000 words |

For chapters long enough to blow past the cap, we split them into sections, summarize each on its own, then run one more pass to merge those into a single coherent summary.

## The reading schedule is just math

No AI touches this part at all:

```
words_per_session = daily_minutes × 200        # average reading speed
chunks_per_chapter = ceil(chapter_word_count / words_per_session)
```

We only split on sentence boundaries — never mid-sentence — and if a chunk comes out under 100 words, it gets folded into the one before it. Every chunk gets a day number, in order, across the whole book. As an example: 30 minutes a day at 200 words a minute is 6,000 words a session, so a 60,000-word book lands at 10 days.

## Asking the book a question

This is retrieval-augmented, which just means it isn't allowed to make things up — it has to find the actual passage first.

Your question gets embedded with Gemini, then compared by cosine similarity against every page we've already embedded for that book. The top 3 matches get pulled, and DeepSeek is told, in effect, "answer only from this text, and say so if it isn't in here." The answer comes back with the page numbers it was pulled from.

A couple of things worth knowing: we only pull the top 3 matches, not 5, to keep the prompt small even for long books. We also carry the last 3 exchanges of conversation so follow-up questions make sense. And if there's no Gemini key configured, it falls back to a cruder hash-based vector instead of just breaking — not as good, but it won't crash on you.

## What's actually stored

- **Book** — where it came from, processing status, chosen reading mode, daily time, how its chapters were detected.
- **Chapter → Chunk** — chunks are the real unit of reading; each one knows which day it belongs to and how many words it is.
- **ReadingSchedule** — one per user per book, holding the full calendar and which day you're currently on.
- **BookIntelligenceProfile** — tracks where a book is in the pipeline and caches its brief so it's only ever generated once.
- **ChapterIntelligence** — the mode-specific summaries, generated the first time they're needed and kept forever after.
- **PageEmbedding** — one row per chunk, storing the text and its embedding.
- **NotificationContent** — the four daily pieces, generated the night before.
- **Community / Message / MessageReaction** — groups (public or invite-only, general or tied to a specific book), with reply threads and reactions.

## API, roughly

**Auth** (`/api/v1/auth/`) — register, login, refresh, Google sign-in, and the forgot-password/OTP/reset flow.

**Books** (`/api/v1/books/`) — browsing, search, recommended/trending, chapter and chunk detail, schedule, today's reading and marking it done, today's summary, and the upload endpoints.

**Book Intelligence** (`/api/v1/intelligence/`) — kicking off analysis, checking its status, pulling the brief, viewing/editing detected chapters, confirming them, asking questions and reading past Q&A, and today's notifications.

**Library** (`/api/v1/library/`) — your saved books, status/favorite updates, and your overall progress stats.

**Community** (`/api/v1/community/`) — creating and managing groups, joining (including via invite link), and messaging with reactions.

## Security basics

Every endpoint sits behind JWT auth. Access tokens last 60 minutes, refresh tokens 7 days, and refresh tokens are blacklisted once rotated so they can't be reused. Password reset OTPs expire in 2 minutes. Uploaded PDFs get UUID filenames so there's no way to path-traverse into something you shouldn't. API keys live in environment variables via `python-decouple`, never in code. And if an AI provider key is missing for whatever reason, the app doesn't fall over — the AI features just quietly return a safe default instead.

## Background jobs

```
Redis (broker)
├── books.task_extract_and_detect            — fires the moment a PDF is uploaded
├── books.task_build_reading_schedule         — fires once chapters are confirmed
├── book_intelligence.classify_and_structure
├── book_intelligence.generate_book_brief_task
├── book_intelligence.generate_chapter_intelligence_task
├── book_intelligence.build_rag_embeddings_task
├── book_intelligence.generate_daily_notifications_task
└── Celery Beat
    └── readify_nightly_notifications         — every night at 23:00 UTC
```

The important pipeline tasks retry up to 3 times with a 60-second gap if something fails. When an upload does fail, we record exactly which stage it failed at and why, so the app can tell you what went wrong instead of just saying "something broke." Everything in the pipeline is safe to re-run without side effects.

## Choices we made on purpose

A few decisions here go against what you'd do by default, and we made them deliberately:

- Instead of sending the whole book to an AI model, we cap every call and stage the work — cheaper, faster, and far less likely to hallucinate.
- Instead of using AI to find chapters, we check bookmarks and text patterns first and only call AI when neither works — which turns out to cover about 85% of books for free.
- Instead of generating every summary the moment a book is uploaded, we generate them lazily, the first time someone actually reaches that chapter — so we're not paying to summarize chapters nobody reads.
- Instead of pgvector, we do similarity search in plain Python — one less dependency, and it's fast enough at the scale we're operating at.
- Instead of one summary style for everyone, there are four modes, because people pick up the same book for very different reasons.
- Instead of generic push notifications, each one is generated from tomorrow's actual content — the whole point is relevance, not just a reminder to open the app.
- Instead of leaving chapter titles as "Chapter 3," a light AI pass renames them based on the opening text, for very little extra cost.

## In numbers

- 6 Django apps
- roughly 85% of books get their chapters detected without touching AI at all
- 4 reading modes, generated lazily and cached forever once made
- an 8,000-word ceiling on every single AI call
- $0 embedding cost, since Gemini's tier is free
- no pgvector dependency
- one AI call covers all 4 daily notifications for a user/book pair
- OTPs expire in 2 minutes, access tokens in 60 minutes, refresh tokens in 7 days
