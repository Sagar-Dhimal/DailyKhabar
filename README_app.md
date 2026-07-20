# Daily Khabar — `app.py` Deep Dive

> **File:** `app.py`  
> **Role:** Central Flask application — the entry point that ties together the database, machine-learning layer, news-sync pipeline, and every user-facing URL.

---

## Table of Contents

1. [Imports — What They Are and Why They Are Used](#1-imports)
2. [App Initialisation](#2-app-initialisation)
3. [Global State & Helpers](#3-global-state--helpers)
4. [Authentication Decorators](#4-authentication-decorators)
5. [Context Processor](#5-context-processor)
6. [Public Routes](#6-public-routes)
7. [ML Tool Routes (User)](#7-ml-tool-routes-user)
8. [User Dashboard Route](#8-user-dashboard-route)
9. [Admin Routes](#9-admin-routes)
10. [Data Flow Diagram](#10-data-flow-diagram)

---

## 1. Imports

### 1.1 Flask Framework Imports

```python
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
```

| Name | What It Does |
|------|-------------|
| `Flask` | The main class. Creates the WSGI web application object (`app = Flask(__name__)`). |
| `render_template` | Loads an HTML file from the `templates/` folder and renders it with Jinja2, merging Python variables into the HTML. |
| `request` | Gives access to the current HTTP request — form data (`request.form`), query strings (`request.args`), uploaded files (`request.files`), and JSON bodies (`request.get_json()`). |
| `redirect` | Returns an HTTP 302 redirect response, sending the browser to a different URL. |
| `url_for` | Generates a URL for a named route function (e.g. `url_for('index')` → `"/"`). Keeps URLs consistent even if you rename a route path. |
| `session` | A signed cookie that stores per-browser state — used here to remember `user_id` (logged-in user) and `admin_logged_in` (admin flag). |
| `flash` | Stores a one-time message in the session that the next rendered template can display (e.g., "Post created successfully."). |
| `abort` | Immediately stops the request and returns an HTTP error — `abort(404)` returns a "Not Found" page. |

---

### 1.2 Werkzeug Security & Utils

```python
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
```

| Name | What It Does |
|------|-------------|
| `generate_password_hash` | Hashes a plain-text password using a strong one-way algorithm (pbkdf2/sha256) before saving it to MongoDB. Passwords are **never** stored in plain text. |
| `check_password_hash` | Verifies a plain-text login attempt against the stored hash during login. |
| `secure_filename` | Sanitises an uploaded file's name — strips directory traversal characters (e.g., `../../evil`) to prevent path-injection attacks. Used when saving uploaded article images. |

> **Werkzeug** is the WSGI utility library that Flask is built on top of.

---

### 1.3 BSON ObjectId

```python
from bson import ObjectId  # pyrefly: ignore [missing-import]
```

MongoDB stores every document with a field `_id` of type `ObjectId` — a 12-byte binary value (not a plain string). When you retrieve a document and then need to query by its `_id` again (e.g., to approve a comment), you must convert the string back to an `ObjectId`. This import provides that conversion class.

```python
# Example usage in the codebase
db.comments.update_one({"_id": ObjectId(comment_id)}, {"$set": {"status": "approved"}})
```

---

### 1.4 Standard Library

```python
import os
import math
from datetime import datetime
from functools import wraps
```

| Name | What It Does |
|------|-------------|
| `os` | Provides OS-level utilities: reading environment variables (`os.environ.get`), joining file paths (`os.path.join`), and creating directories (`os.makedirs`). Used to configure the upload folder and the Flask secret key. |
| `math` | Used for `math.ceil()` — calculating the total number of pages for pagination on the news feed. |
| `datetime` | Creates timestamps. Used when naming uploaded files with a Unix timestamp (`datetime.now().timestamp()`) to avoid filename collisions. |
| `functools.wraps` | Preserves the original function's name and docstring when it is wrapped by a decorator. Without it, every decorated route would appear to Flask as a function named `decorated_function`, causing name collisions. |

---

### 1.5 Local Module: `mongo`

```python
from mongo import db, DATASET_PATH, utc_iso, export_to_json, COLLECTION_MAP
```

`mongo.py` centralises all MongoDB connection logic so `app.py` doesn't have to repeat connection strings.

| Name | What It Does |
|------|-------------|
| `db` | The live MongoDB database handle (a `pymongo.Database` object). Used throughout `app.py` to query collections like `db.articles`, `db.users`, `db.comments`, `db.queries`, etc. |
| `DATASET_PATH` | A `pathlib.Path` pointing to the CSV file (`article_meta.csv` or similar) that holds the base article dataset. Passed to `load_articles()`. |
| `utc_iso` | A helper function that returns the current UTC time as an ISO 8601 string (e.g. `"2026-07-18T04:00:00+00:00"`). Used as `created_at` / `published_at` timestamps in every DB insert. |
| `export_to_json` | Mirrors a MongoDB collection to a local JSON file inside `MongoData/`. This acts as an offline backup/sync. |
| `COLLECTION_MAP` | A dictionary mapping collection names to their JSON file names (e.g., `{"articles": "article_meta.json"}`). Used by the local `sync_db()` helper. |

---

### 1.6 Local Module: `portal_ml`

```python
from portal_ml import (
    load_articles,
    summarize_text,
    categorize_text,
    init_classifier,
    summarization_accuracy,
    categorization_accuracy,
    get_recommendations
)
```

`portal_ml.py` is the entire machine-learning layer — pure Python, no external ML libraries.

| Name | What It Does |
|------|-------------|
| `load_articles` | Reads the CSV dataset into a list of article dictionaries. Auto-generates a summary and category for articles that are missing one. |
| `summarize_text` | Extractive text summariser. Scores sentences by TF (term frequency) of their tokens and picks the top N. |
| `categorize_text` | Hybrid categoriser: (1) World Cup 2026 keyword override → (2) Rule-based keyword matching → (3) Naive Bayes classifier trained on existing articles → (4) falls back to "General". |
| `init_classifier` | Trains the in-memory Naive Bayes model on the current article cache. Called every time the cache is refreshed. |
| `summarization_accuracy` | Measures how well the summary captures the source using token-overlap F1, then maps the result into a 70–90% confidence band. |
| `categorization_accuracy` | Returns a confidence score (70–90%) for how certain the classifier is about its category prediction, based on keyword hit depth and Naive Bayes score margin. |
| `get_recommendations` | Returns the top-N most similar articles using TF-IDF cosine similarity for the "Read More" section on the article page. |

---

### 1.7 Local Module: `generate_metrics`

```python
from generate_metrics import get_confusion_matrix_data
```

`generate_metrics.py` computes the confusion matrix, per-class precision/recall/F1, and overall accuracy from a fixed set of synthetic evaluation data (`Y_TRUE` / `Y_PRED` arrays). `get_confusion_matrix_data()` returns a JSON-serialisable dictionary that the admin dashboard uses to render the matrix table and per-class bar charts.

---

### 1.8 Late Import: `news_sync`

```python
from news_sync import run_sync   # Line 743 — intentionally placed late
```

Imported at the bottom to avoid circular dependencies (it also imports from `portal_ml`). `run_sync` fetches RSS feeds, scrapes article pages, deduplicates, and inserts new articles into MongoDB. It is called only when the admin triggers `/admin/sync`.

---

## 2. App Initialisation

```python
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-flask-secret")
```

- `Flask(__name__)` creates the app, using `__name__` to locate the `templates/` and `static/` folders relative to `app.py`.
- `secret_key` is used to cryptographically sign the session cookie. Reading it from an environment variable means the production server can set a strong random key without touching the source code.

```python
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
```

Creates `static/uploads/` on disk (if it doesn't exist) for storing uploaded article images. Images saved here are automatically served by Flask as static files under `/static/uploads/<filename>`.

---

## 3. Global State & Helpers

### `ARTICLES_CACHE`

```python
ARTICLES_CACHE = []
```

An in-memory list of all articles (dictionaries), kept at module level. Every route reads from this list instead of hitting MongoDB or the CSV on every request, which would be far too slow. It is refreshed by `refresh_articles_cache()`.

---

### `refresh_articles_cache()`

The most important startup function. Called once at import time and again after any write operation.

```
┌─────────────────────────┐
│ 1. Load from CSV        │  (base dataset, already categorised + summarised)
│ 2. Load from MongoDB    │  (admin-created / edited posts override CSV entries)
│ 3. Load deleted IDs     │  (soft-deleted articles to exclude)
│ 4. Merge & sort         │  (newest first by published_at)
│ 5. Train classifier     │  init_classifier(ARTICLES_CACHE)
└─────────────────────────┘
```

Priority: **DB record > CSV record**. A MongoDB article with the same `article_id` as a CSV row wins, allowing admins to edit CSV-sourced articles without touching the CSV file.

---

### `sync_db(collection)`

```python
def sync_db(collection):
    if collection in COLLECTION_MAP:
        export_to_json(collection, COLLECTION_MAP[collection])
```

A one-liner helper called after every write to MongoDB. It mirrors the updated collection to a JSON file — effectively keeping a local, human-readable backup in sync.

---

## 4. Authentication Decorators

### `user_login_required`

Wraps any route that requires a logged-in reader. Checks `session["user_id"]`. If missing, redirects to `/login` with the original URL preserved as a `?next=` parameter so the user is returned there after login.

### `admin_login_required`

Same pattern but checks `session["admin_logged_in"]`. Admin credentials are hard-coded constants (`ADMIN_USERNAME`, `ADMIN_PASSWORD`) — for production these should move to environment variables.

Both use `@wraps(f)` from `functools` to preserve the original function name for Flask's routing system.

---

## 5. Context Processor

```python
@app.context_processor
def inject_global_context():
    ...
    return {"nav_categories": categories}
```

A context processor runs before **every** template render and injects variables into the Jinja2 context automatically. Here it builds the sorted list of all categories (from articles + any custom categories created by the admin) and makes it available as `nav_categories` in every template — used to populate the navigation bar's category dropdown.

---

## 6. Public Routes

### `GET /` — `index()`
The news feed homepage. Supports:
- **Search** (`?q=...`) — filters by title/description.
- **Category filter** (`?category=...`) — shows only one category.
- **Pagination** (`?page=N`) — 6 articles per page using `math.ceil`.
- Also extracts up to 5 "World Cup 2026" articles for the featured slider.

### `GET /article/<article_id>/` — `article_detail()`
Renders a single article. Also:
1. Fetches all **approved** comments, sorted oldest-first.
2. Organises them into a **threaded tree** (roots + child replies keyed by `parent_id`).
3. Calls `get_recommendations()` for TF-IDF-based "Read More" suggestions.

### `POST /article/<article_id>/comment` — `add_comment()`
Requires login. Inserts a comment with `status: "pending"` — it won't appear publicly until an admin approves it.

### `GET|POST /register` — `register()`
Validates username + email uniqueness, hashes the password with `generate_password_hash`, saves to `db.users`, and immediately logs the user in.

### `GET|POST /login` — `login()`
Handles both a **user login tab** and an **admin login tab** on the same page, distinguished by a hidden `login_type` field.
- Admin: compares against hardcoded credentials, sets `session["admin_logged_in"]`.
- User: verifies hashed password with `check_password_hash`.

### `GET /logout` — `logout()`
Calls `session.clear()` — wipes all session data for the browser.

### `GET /about`, `GET|POST /contact`
Static pages. The contact form saves the message to `db.queries` with `status: "pending"` for admin follow-up.

---

## 7. ML Tool Routes (User)

These routes are login-protected and expose the ML layer directly to readers.

### `GET|POST /tools` — `tools()`
Landing page listing the available tools (Summarize, Classify).

### `handle_text_or_file()` (helper)
Used by both tool routes. Reads text from either:
- A `<textarea>` (`raw_text` form field), or
- An uploaded `.txt` file (`file_upload` field).

### `GET|POST /summarize` — `summarize()`
1. Accepts text + a "max sentences" setting.
2. Calls `summarize_text()` to produce an extractive summary.
3. Calls `summarization_accuracy()` and `categorization_accuracy()` to produce confidence scores.
4. Logs the activity to `db.user_activities`.

### `GET|POST /classify` — `classify()`
1. Accepts text input.
2. Calls `categorize_text()` for the predicted category.
3. Calls `categorization_accuracy()` for confidence (always 70–90% for valid text).
4. Logs the activity to `db.user_activities`.

---

## 8. User Dashboard Route

### `GET /user/dashboard` — `user_dashboard()`

Queries MongoDB for the logged-in user's:
- Recent **activities** (last 20 summarisations/classifications)
- Recent **comments** (last 10)
- Recent **queries/messages** (last 10)
- **Stats counts** (total activities, approved comments, answered queries, etc.)

All passed to `user_dashboard.html`.

---

## 9. Admin Routes

All admin routes are protected by `@admin_login_required`.

### `GET /admin/dashboard` — `admin_dashboard()`
The control centre. Computes:
- **ML accuracy metrics** — averages `categorization_accuracy()` and `summarization_accuracy()` over a sample of 20 articles (ensuring results land in the realistic 70–90% band).
- **Category distribution** — count per category for the bar chart.
- **Confusion matrix data** — from `get_confusion_matrix_data()`.
- **System stats** — total posts, users, queries, comments (pending + approved), summaries run.

### `GET /admin/posts` — `admin_posts()`
Filterable/searchable list of all articles. Reads from `ARTICLES_CACHE` (in-memory, fast).

### `GET|POST /admin/posts/new` — `admin_post_create()`
Creates a new article:
1. Handles optional image upload via `secure_filename`.
2. Auto-classifies content with `categorize_text()`.
3. Auto-summarises with `summarize_text()`.
4. Generates the next `article_id` by taking `max(all existing IDs) + 1`.
5. Inserts into `db.articles`, syncs to JSON, refreshes the cache.

### `GET|POST /admin/posts/edit/<id>` — `admin_post_edit()`
Edits an existing article using MongoDB's `update_one` with `upsert=True` (so CSV articles that haven't been edited yet get their first DB record created on first edit). Re-classifies and re-summarises on save.

### `POST /api/predict` — `api_predict()`
A JSON API endpoint (admin-only) used by the "Create Post" form's live preview panel. Accepts `{"text": "..."}` and returns category, confidence, summary, and summary accuracy in real time as the admin types (with a 1.2-second debounce in the frontend).

### `POST /admin/posts/delete/<id>` — `admin_post_delete()`
**Soft delete** pattern:
1. Removes the article from `db.articles`.
2. Adds the `article_id` to `db.deleted_articles` so that if the same article ID appears in the CSV, it won't be re-imported by `refresh_articles_cache()`.

### `POST /admin/posts/bulk-delete` — `admin_posts_bulk_delete()`
Same as single delete but accepts a list of `article_ids` from a multi-select form.

### `GET|POST /admin/categories` — `admin_categories()`
Lists all categories with article counts. Allows creating new custom categories stored in `db.categories`.

### `POST /admin/categories/edit` — `admin_categories_edit()`
Renames a category across `db.categories`, `db.articles`, and the in-memory `ARTICLES_CACHE`. Re-trains the classifier afterwards.

### `POST /admin/categories/delete` — `admin_categories_delete()`
Deletes a category and re-assigns its articles to "General". Re-trains the classifier.

### Comment Management (`/admin/comments/...`)
- **`admin_comments()`** — lists all comments sorted newest-first.
- **`admin_comment_action()`** — approve / reject / delete a comment by its `ObjectId`.
- **`admin_comment_reply()`** — inserts an admin reply comment (auto-approved) linked to the parent comment's `article_id`.
- **`approve_comment()` / `reject_comment()`** — GET shortcuts for quick approve/reject.

### Query (Contact) Management (`/admin/queries/...`)
- **`admin_queries()`** — lists all contact form submissions.
- **`admin_query_detail()`** — shows one query's full message.
- **`admin_query_reply()`** — marks query as `"answered"` and stores the admin's reply text.

### `GET /admin/sync` — `admin_dataset_sync()`
Triggers the full news sync pipeline:
1. Calls `run_sync(...)` from `news_sync.py` — fetches RSS feeds, scrapes article pages, deduplicates, categorises, summarises, and inserts new articles.
2. Calls `refresh_articles_cache()` to pick up the new articles.
3. Flashes a success/info message with the count of new articles added.

---

## 10. Data Flow Diagram

```
Browser Request
      |
      v
  app.py (Flask)
      |
      +-- Reads ARTICLES_CACHE (in-memory)
      |       +-- Built from CSV  ---- portal_ml.load_articles()
      |       +-- Overridden by MongoDB articles
      |
      +-- portal_ml.py  (ML layer)
      |       +-- categorize_text()   -> Hybrid keyword + Naive Bayes
      |       +-- summarize_text()    -> Extractive TF-score summariser
      |       +-- get_recommendations() -> TF-IDF cosine similarity
      |       +-- *_accuracy()        -> Confidence score (70-90%)
      |
      +-- mongo.py  (Database layer)
      |       +-- db.*                -> Live MongoDB operations
      |       +-- export_to_json()    -> Local JSON backup (sync_db)
      |
      +-- generate_metrics.py  (Evaluation)
      |       +-- get_confusion_matrix_data() -> Confusion matrix for dashboard
      |
      +-- news_sync.py  (RSS pipeline -- admin only)
              +-- run_sync()  -> Fetch -> Scrape -> Categorise -> Insert
```

---

## Running the App

```bash
python app.py
# Runs on http://localhost:8000 (debug mode enabled)
```

For production, run with a WSGI server (Gunicorn/Waitress) and set the `FLASK_SECRET_KEY` environment variable to a long random string.

```bash
set FLASK_SECRET_KEY=your-very-long-random-secret
gunicorn app:app
```
