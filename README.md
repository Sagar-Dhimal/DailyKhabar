# News Portal ML Pipeline — `news_ml.py`

This module powers three features of the news portal:

1. **Extractive summarization** — `summarize_text()`
2. **Hybrid categorization** — `categorize_text()` (rule-based keywords + Naive Bayes)
3. **"Related articles"** — `get_recommendations()` (TF-IDF cosine similarity)

Plus CSV loading (`load_articles()`, `build_dataset()`) and two evaluation
helpers (`summarization_accuracy()`, `categorization_accuracy()`).

All public function names and signatures are unchanged from the previous
version, so any existing calling code keeps working. Every fix is marked
`FIX:` inline in the code with the reasoning; this document walks through
*why* each section works the way it does and what was wrong before.

---

## 1. Tokenization — `tokenize()`, `STOPWORDS`

Turns raw text into a list of lowercase, alphabetic "content words," with
common filler words removed. Both the summarizer and both classifiers
build on this, so its quality matters everywhere.

**What changed:** the stopword list was missing several very common words
(`i`, `you`, `can`, `do`, `did`, `been`, `also`, `no`, ...). That let filler
words sneak into frequency counts and skew both sentence-scoring and the
Naive Bayes vocabulary. The list is now broader.

---

## 2. Sentence splitting & summarization — `split_sentences()`, `summarize_text()`

A classic **frequency-based extractive summarizer**:
1. Split the article into sentences.
2. Count how often each content word appears in the whole article.
3. Score every sentence as the sum of its words' (normalized) frequencies
   — sentences using more "important" (frequent) words score higher.
4. Keep the top `max_sentences` sentences, but put them back in their
   original order so the summary still reads coherently.

**What changed:**
- `max_sentences <= 0` is now guarded against (previously undefined/odd behavior).
- Tie-breaking when two sentences have equal scores: the old code did
  `scored.sort(reverse=True)` on `(score, index, sentence_text)` tuples,
  which also reverses the *index* comparison on ties — silently preferring
  *later* sentences over earlier ones, and falling through to compare raw
  sentence text as a last tiebreaker. Sorting now explicitly uses
  `(-score, index)`, so ties are broken by "earliest sentence first," which
  is what you'd expect from a summarizer.

**Limitation worth knowing:** sentence score is a *sum*, not an average, so
longer sentences are naturally favored over short, punchy ones. This is a
standard weakness of frequency-sum summarizers — see improvement #1 below.

---

## 3. Rule-based keyword classifier — `_RULE_KEYWORDS`, `_rule_based_score()`

Scores each category by counting how many of its keywords appear in the
article, and returns whichever category has the most hits.

**Two real bugs fixed here:**

- **Case bug:** `World Cup 2026`'s keyword list contained capitalized
  entries (`"Argentina"`, `"Messi"`, `"Lamine"`, ...), but they were being
  matched against a *lowercased* copy of the article (`t = text.lower()`).
  Since Python string containment is case-sensitive, those keywords could
  **never match, ever**. Every keyword in every list is now lowercase.

- **Substring false positives:** matching used plain `kw in t`, so short
  keywords matched as substrings inside unrelated words — `"ai"` inside
  "aga**i**n" or "capt**ai**n", `"pm"` inside "ca**mp**site", `"bill"` inside
  "**bill**board". All keyword matching now uses compiled word-boundary
  regexes (`\bkeyword\b`), so only whole-word (or whole-phrase, for
  multi-word keywords like "prime minister") matches count.

---

## 4. Validity check — `is_valid_article()`

Added new. Rejects text that is empty, has fewer than 3 distinct content
words, or is dominated (>60%) by one repeated word — e.g. `"The The The
The..."` or `"score score score score..."`. These aren't real articles and
should never be force-classified into a real category; `categorize_text()`
and `categorization_accuracy()` both check this first and return
`"General"` / `0.0` immediately if it fails.

---

## 5. Naive Bayes classifier — `train_classifier()`, `predict_category()`

Standard multinomial Naive Bayes with Laplace (add-1) smoothing:
`train_classifier()` builds per-category word counts and document counts
from labeled training articles; `predict_category()` scores a new text
against every trained category using log-probabilities and returns the
highest-scoring one.

**The important bug fixed here:** the old version *always* returned some
trained category — even for text with zero real relationship to any
category — because Laplace smoothing guarantees every category gets a
nonzero (if tiny) probability, so "highest score" degenerates to "whichever
category has the largest prior" on nonsense input. `predict_category()` now
tracks whether any of the article's words were *ever seen at all* in any
training category (`total_overlap`), and also requires the top category to
beat the runner-up by a `min_margin` of log-probability — otherwise it
abstains and returns `"General"` rather than guessing.

---

## 6. TF-IDF "related articles" — `_build_tfidf_index()`, `get_recommendations()`

Builds a classic TF-IDF vector per article (title + full content +
description, smoothed IDF, L2-normalized), then `get_recommendations()`
computes cosine similarity between the target article's vector and every
other article's vector, returning the top N.

**Fixes:**
- If an article isn't in the TF-IDF index (e.g. missing `article_id` or no
  tokens) **or** it *is* indexed but happens to share zero vocabulary with
  every other article (cosine similarity of 0 everywhere), both cases now
  fall back to "other articles in the same category" instead of returning
  an empty list in the second case.
- Duplicate `article_id` values used to silently overwrite each other in
  the vector dictionary, quietly corrupting results. This now prints a
  warning identifying the duplicated IDs so it gets noticed and fixed at
  the data layer instead of surfacing as "weird recommendations" later.

**Known scaling limit:** similarity is computed against *every* other
article on every call — fine for a few thousand articles, but it's O(N)
per lookup. See improvement #4 below if the catalog grows large.

---

## 7. Hybrid categorization — `categorize_text()`

This is the actual "hybrid" combiner. Order of precedence:

1. **Invalid/degenerate text** → `"General"` immediately.
2. **Strong rule-based match** (score ≥ `rule_min_score`, default 2) →
   trust it directly; keyword hits are cheap and precise once the case
   and substring bugs above are fixed.
3. **Confident Naive Bayes match** → used when the rule-based signal
   wasn't strong enough on its own.
4. **Weak rule-based match** (1 hit, below the confidence threshold) →
   still better than nothing if Naive Bayes also couldn't decide.
5. Otherwise → `"General"`.

**The significant bug fixed here:** the previous version special-cased
`World Cup 2026` *before* anything else, triggering on just **one**
keyword hit. Since that category's list includes generic sports words
also used elsewhere (`score`, `penalty`, `semifinal`, `knockout`), a single
incidental match — e.g. *"Students **score**d well in the board exam"* —
would hijack an Education article into `World Cup 2026`. This was verified
directly: the fixed code correctly keeps that example as `Education`,
while a genuine article about Messi and Argentina still correctly resolves
to `World Cup 2026` (it accumulates far more keyword hits, including the
now-fixed proper-noun ones).

---

## 8. CSV loading — `load_articles()`, `build_dataset()`

`load_articles()` reads the CSV, builds a summary per row, fills in a
category if the CSV didn't already have one, and sorts by `published_at`
(newest first).

**Fixes:**
- Previously, the text used *for summarization* (`full_content` if present,
  else `description`) was also written back out as the row's
  `"full_content"` field. If a row had no `full_content`, the output would
  silently substitute the `description` text into the `full_content` key —
  conflating two fields that downstream code expects to be distinct. The
  stored `full_content` now always reflects the CSV's actual column.
- `published_at` was sorted as a raw string, which only produces correct
  chronological order if every row's date happens to be in an identical,
  lexicographically-sortable format. It's now parsed into a real
  `datetime` (`_parse_date_key()`), with a safe fallback for missing or
  malformed dates instead of crashing or silently misordering.
- `csv.field_size_limit(sys.maxsize)` can raise `OverflowError` on
  platforms where the C `long` is 32-bit (some Windows Python builds),
  since `sys.maxsize` is a 64-bit Python value that may not fit. The module
  now backs off to a smaller limit automatically instead of failing to
  even import.

**New: `build_dataset(csv_path)`.** There's an inherent chicken-and-egg
problem: `load_articles()` calls `categorize_text()` for any row missing a
category, but the Naive Bayes half of `categorize_text()` needs a *trained
model*, and training needs already-loaded (and at least partially labeled)
articles. `build_dataset()` resolves this as a two-pass pipeline:
1. Load the CSV (categorization here is rule-based only, since no model
   exists yet).
2. Train the Naive Bayes model + TF-IDF index on that data.
3. Re-run `categorize_text()` on anything still labeled `"General"`, now
   that the model has something to work with.

This is the recommended way to bootstrap categorization from a fresh CSV.
For ongoing use (new articles trickling in after the model is already
trained), just call `categorize_text()` directly.

---

## 9. Evaluation helpers

### `summarization_accuracy(source, summary)`
An approximate **unigram-overlap F1** between the source and its summary
(precision/recall over the set of content words each contains). This is a
lightweight stand-in for ROUGE-1, not the official ROUGE metric — fine for
a quick internal signal, but don't quote it externally as "ROUGE score."

### `categorization_accuracy(text)` — **please read this one**
The previous implementation **did not measure accuracy in any real
sense**. It counted keyword hits, mapped that into a 70–90 range, and then
added `random.uniform(-1.0, 1.0)` jitter on top — meaning it produced a
plausible-looking, entirely fabricated confidence number for *every single
article*, regardless of whether the assigned category was actually
correct. If this number was ever shown to users, editors, or in a QA
dashboard, it was actively misleading, since it carried no real
information about correctness.

The fixed version is still a **heuristic**, not measured accuracy — real
accuracy requires comparing predictions against ground-truth labels, which
this function has no access to (see improvement #2 below for how to do
that properly). But it is now deterministic (same text → same number,
always) and actually derived from the two real signals the classifier
uses: how many rule-based keywords matched, and how large the Naive Bayes
score margin was between the top two candidate categories. Treat its
output as "how strong was the classification signal," not "percent
correct."

---

## Suggested improvements (not yet implemented)

1. **Length-normalize sentence scores in the summarizer.** Currently a
   sentence's score is the *sum* of its words' frequencies, which favors
   long sentences. Dividing by sentence length (or word count) would
   reward *dense* sentences instead, which usually reads better as a
   summary.

2. **Measure real categorization accuracy with a labeled validation set.**
   Set aside a sample of articles with known-correct categories (ideally
   hand-labeled, not the same data used to train the Naive Bayes model),
   run `categorize_text()` over them, and compute actual precision,
   recall, and F1 per category. This is the only way to know whether the
   classifier is genuinely working, and would also let you tune
   `rule_min_score` / `nb_min_margin` against real numbers instead of
   guessing.

3. **Split the generic sports terms out of "World Cup 2026."** The two
   categories currently share `score`, `penalty`, `semifinal`, `knockout`.
   This works today because a genuine World Cup article also matches
   several *distinctive* terms (team names, "world cup 2026", etc.) and so
   out-scores plain Sports — but it's worth revisiting once real
   production data comes in, in case some edge case still tips the wrong
   way.

4. **Scale the recommendation engine if the catalog grows large.**
   `get_recommendations()` currently compares against every other article
   on every call (O(N) per lookup). Fine for a few thousand articles; for
   a much larger catalog, consider precomputing top-K neighbors at index
   time, or an approximate nearest-neighbor library (e.g. scikit-learn's
   `NearestNeighbors`, or FAISS) for sub-linear lookups.

5. **Move away from module-level global state** (`_NB_MODEL`,
   `_TFIDF_VECTORS`, `_TFIDF_IDS`). This works fine for a single-process
   batch script, but makes it hard to (a) serve multiple independent
   models/tenants, (b) retrain safely while requests are in flight, or (c)
   unit-test in isolation. Wrapping the state in a small class (e.g.
   `NewsClassifierEngine`) that `init_classifier`/`categorize_text`/
   `get_recommendations` become thin wrappers around would make this much
   more robust if the portal grows into a real backend service.

6. **Consider a proper ROUGE/BLEU library** (e.g. `rouge-score` on PyPI)
   if summarization quality numbers ever need to be reported externally or
   compared against published benchmarks — the current
   `summarization_accuracy()` is a reasonable quick internal signal but
   isn't a standardized metric.

7. **Log/track "General" rate over time.** Since both classifiers can now
   correctly abstain to `"General"` on weak or invalid signal (a
   deliberate fix in this update), it's worth monitoring what fraction of
   incoming articles land there in production — a rising "General" rate
   over time is a good early signal that the keyword lists or training
   data need to be expanded to cover a new topic area.
