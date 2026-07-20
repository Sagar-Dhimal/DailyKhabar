# Daily Khabar — Final Year Project Justification & Analysis

> **Project Name:** Daily Khabar — AI-Powered News Aggregation Portal  
> **Degree Level:** Bachelor of Science in Computer Science and Information Technology (BSc CSIT)  
> **Document Purpose:** Academic justification, real-world problem statement, and SWOT analysis

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Real-World Problem This Project Solves](#2-the-real-world-problem-this-project-solves)
3. [Why This Is Sufficient as a Final Year Project](#3-why-this-is-sufficient-as-a-final-year-project)
4. [Technical Domains Covered](#4-technical-domains-covered)
5. [SWOT Analysis](#5-swot-analysis)
6. [Comparison With Typical Final Year Projects](#6-comparison-with-typical-final-year-projects)
7. [Conclusion](#7-conclusion)

---

## 1. Executive Summary

**Daily Khabar** is a full-stack, AI-integrated news aggregation portal built for the Nepali online news ecosystem. It automatically fetches articles from live RSS feeds (The Rising Nepal, The Himalayan Times, BBC Sport), scrapes their full content, classifies them into categories using a hybrid machine learning model, generates extractive summaries, and presents them through a polished web interface — all without relying on any external paid AI service.

The system is entirely self-contained: the database (MongoDB), the ML engine (pure Python Naive Bayes + TF-IDF), the web server (Flask), and the frontend (HTML/CSS/JS with Bootstrap) are integrated into a single deployable application.

---

## 2. The Real-World Problem This Project Solves

### 2.1 The Information Overload Problem

Nepal has dozens of active online news sources — The Rising Nepal, The Himalayan Times, Setopati, Onlinekhabar, and more — each publishing hundreds of articles per day across multiple categories. The average reader faces:

- **Fragmentation:** Having to visit 5–10 different websites to stay informed.
- **No personalisation:** No way to filter by topic (Politics, Sports, Technology, etc.) across sources.
- **Long articles:** Most articles are 400–800 words. Busy readers cannot read every story in full.
- **No discovery:** No mechanism to find related articles once you finish reading one.

### 2.2 The Solution Daily Khabar Provides

| Problem | How Daily Khabar Solves It |
|---|---|
| Multi-source fragmentation | Aggregates RSS feeds from multiple publishers into one unified feed |
| Topic overwhelm | Auto-classifies every article into one of 10 categories; filterable by category |
| Long-form reading fatigue | Generates 3-sentence extractive summaries for every article |
| No content discovery | TF-IDF cosine-similarity recommendation engine shows related articles |
| No reader tools | Provides a standalone summariser and classifier tool for any user-pasted text |
| No admin control | Full admin panel for content moderation, category management, and comment review |
| Reader isolation | Threaded comment system for community discussion on every article |

### 2.3 Local Relevance

Nepal's digital journalism sector is growing rapidly but remains underserved by technology. There is no widely-used, locally-focused, AI-powered news aggregator for Nepali news outlets. Daily Khabar directly addresses a gap in the local information ecosystem by building infrastructure that is:

- **Free** — no API subscription fees, no third-party AI costs
- **Local** — tailored to Nepali news sources and categories like "Agriculture" and "Environment" which matter most to Nepali readers
- **Transparent** — the model's decisions (category, confidence, summary) are shown to the user

---

## 3. Why This Is Sufficient as a Final Year Project

A strong final year project for BSc CSIT must demonstrate mastery across **multiple computer science disciplines**, solve a **real and identifiable problem**, and produce a **working, demonstrable system**. Daily Khabar satisfies all three criteria.

### 3.1 Breadth of Computer Science Concepts Applied

This project is not a single-topic assignment. It integrates knowledge from at least **seven distinct CS/IT subject areas**:

#### Artificial Intelligence & Machine Learning
The project implements three distinct ML/AI techniques from scratch in `portal_ml.py`:

1. **Naive Bayes Text Classifier** — a probabilistic model trained dynamically on the live article dataset. Implements Laplace smoothing, log-probability scoring, and a confidence margin filter to reduce false positives.

2. **Extractive Text Summarisation** — a TF (term frequency) scoring approach that ranks sentences by how many high-frequency domain words they contain, then reconstructs a coherent summary in original sentence order.

3. **TF-IDF Content-Based Recommendation Engine** — builds L2-normalised TF-IDF vectors for every article and computes cosine similarity in real time to recommend related articles. Implemented in pure Python with no sklearn or numpy dependency.

4. **Rule-Based Hybrid Classifier** — keyword pattern matching using compiled regex (word-boundary aware) that works as a high-confidence override layer before the probabilistic model.

None of these use a pre-trained model or external API. They are fully implemented, understood, and explained by the student.

#### Database Engineering
- **MongoDB** with a multi-collection schema (`articles`, `users`, `comments`, `queries`, `categories`, `deleted_articles`, `user_activities`)
- **Soft-delete** design pattern to preserve data integrity
- **Upsert** operations for edit-without-overwrite semantics
- **Local JSON mirroring** (backup pattern) via `export_to_json`
- **CSV-MongoDB hybrid persistence** with priority-merge logic

#### Web Application Development
- Full **MVC-style Flask** application with 25+ routes
- **Jinja2 templating** with inheritance (`base.html`, `admin_base.html`) and context processors
- **Session management** and **two-tier authentication** (user + admin) using decorator pattern
- **RESTful JSON API** endpoint (`/api/predict`) with live frontend prediction
- **Pagination**, **search**, and **category filtering** on the news feed

#### Data Engineering & Web Scraping
- **RSS feed parsing** using `feedparser` across 10+ feed URLs
- **Full article scraping** using `trafilatura` (state-of-the-art content extraction library)
- **Deduplication** using both exact URL matching and Jaccard-similarity title comparison
- **Featured image extraction** via OpenGraph meta tags using BeautifulSoup
- Robust **date parsing** and **timezone normalisation** for multi-source feeds

#### Security
- **Password hashing** with `werkzeug.security.generate_password_hash` (pbkdf2/sha256)
- **Route-level access control** via custom decorators
- **Secure file upload** with `werkzeug.utils.secure_filename` (path traversal prevention)
- **Session-based authentication** with signed cookies

#### Software Engineering
- **Separation of concerns** across 5 modules (`app.py`, `portal_ml.py`, `mongo.py`, `news_sync.py`, `generate_metrics.py`)
- **In-memory caching** pattern for performance (`ARTICLES_CACHE`)
- **Lazy initialisation** of ML model (trained after cache load, retrained after any content change)
- **Error handling** throughout scraping and ML pipelines
- Input validation and guard clauses at every user-facing endpoint

#### Data Visualisation & Reporting
- **Confusion matrix** with heatmap styling (CSS `--intensity` custom property)
- **TF-IDF keyword bar chart** (Chart.js)
- **Category distribution chart** (Chart.js, dynamic data from live cache)
- **Per-class precision/recall/F1 bar charts** with colour-coded metric bars
- All charts generated from real computed data, not placeholders

### 3.2 Volume and Quality of Code

| File | Purpose | Lines |
|------|---------|-------|
| `app.py` | Flask application, 25+ routes | ~760 |
| `portal_ml.py` | Full ML engine (NB, TF-IDF, summariser) | ~428 |
| `news_sync.py` | RSS + scraping pipeline | ~290 |
| `generate_metrics.py` | Confusion matrix + chart generation | ~100 |
| `mongo.py` | Database layer | ~60 |
| `templates/` | 19 HTML templates | ~2,500+ |
| **Total** | | **~4,100+ lines** |

This is a substantial codebase for a single-person or small-team undergraduate project, with real architectural decisions made and justified at every level.

### 3.3 Demonstrable, Live System

The project produces a **running web application** that can be demonstrated to an evaluation committee in real time:
- Live news feed with real articles fetched from real Nepali news websites
- Working login/registration system
- Live ML prediction shown as the user types in the admin panel
- Admin dashboard with real charts and metrics from the running system
- Threaded comments, contact queries, and category management — all persisted and functioning

This is far stronger than a prototype or a Jupyter notebook analysis.

---

## 4. Technical Domains Covered

The following table maps each BSc CSIT course to the corresponding component in this project:

| BSc CSIT Subject | Project Component |
|---|---|
| Object-Oriented Programming | Flask app architecture, Python classes and modules |
| Database Management Systems | MongoDB schema design, CRUD operations, upsert/soft-delete patterns |
| Artificial Intelligence | Naive Bayes classifier, rule-based system, confidence scoring |
| Data Mining & Warehousing | TF-IDF vectorisation, cosine similarity, extractive summarisation |
| Web Technology | Flask routing, Jinja2 templates, REST API, HTML/CSS/JS |
| Computer Networks | HTTP requests, RSS feed fetching, SSL/TLS handling |
| Software Engineering | Modular architecture, separation of concerns, error handling |
| Data Structures & Algorithms | Token frequency counting, heap-free top-N selection, sorted merging |

---

## 5. SWOT Analysis

### Strengths

| # | Strength | Detail |
|---|---|---|
| S1 | **Zero external AI dependency** | All ML is implemented from scratch in pure Python — no OpenAI, Google, or Hugging Face API needed. This means no running costs and full academic ownership of the algorithm. |
| S2 | **Hybrid ML architecture** | Combining rule-based classification with Naive Bayes provides higher accuracy than either approach alone. The system gracefully degrades: if NB has low confidence, rule-based wins; if both fail, "General" is returned rather than a wrong category. |
| S3 | **Real data, real sources** | Articles come from live Nepali news RSS feeds — not synthetic or downloaded datasets. The system works on genuinely unseen data every time it syncs. |
| S4 | **Full-stack implementation** | From database schema design to frontend interactivity, every layer is built and understood by the developer. No black-box frameworks or no-code tools. |
| S5 | **Admin + User dual role system** | Two completely separate access control levels with different capabilities — demonstrating real-world multi-tier application design. |
| S6 | **Live demonstrability** | The project runs on localhost and can be shown working to evaluators in real time, with live data, not mocked screenshots. |
| S7 | **Content recommendation** | TF-IDF cosine similarity is a real, industry-standard technique used by news platforms. Its presence elevates the project above a simple CRUD application. |

---

### Weaknesses

| # | Weakness | Detail |
|---|---|---|
| W1 | **Hardcoded admin credentials** | Admin username/password are currently stored as plain-text constants in `app.py`. In production this would be a security risk — they should be moved to environment variables or a config file. |
| W2 | **In-memory cache not persistent across restarts** | `ARTICLES_CACHE` is rebuilt on every app start. If the CSV or MongoDB is unavailable, the cache is empty. A production system would use Redis or a persistent store. |
| W3 | **Naive Bayes cold-start problem** | Until enough categorised articles are present in the database, the NB model has poor training data. The system relies on rule-based classification as a fallback during this phase. |
| W4 | **No user-to-user interaction** | Users can comment but cannot follow other users, like articles, or receive personalised recommendations based on reading history. |
| W5 | **Single-language only** | The classifier and keyword system only works for English-language articles. Nepali-language content would not be categorised correctly. |
| W6 | **Scraping fragility** | Web scraping is inherently brittle — if a news website changes its HTML structure, content extraction may degrade until the scraper is updated. |

---

### Opportunities

| # | Opportunity | Detail |
|---|---|---|
| O1 | **Expand to Nepali language** | Integrating a Nepali tokeniser and keyword set would make the platform far more useful for the majority of Nepali internet users who prefer content in Nepali. |
| O2 | **User personalisation** | Adding a reading history tracker and user-preference profile would allow the recommendation engine to be personalised rather than content-only. |
| O3 | **Mobile application** | The existing `/api/predict` JSON API could be extended into a full REST API, enabling a Flutter or React Native mobile app front-end. |
| O4 | **Sentiment analysis layer** | Adding sentiment analysis (positive/negative/neutral tone) to articles and comments would provide richer analytics for the admin dashboard. |
| O5 | **More news sources** | The RSS feed list (`RSS_URLS` in `news_sync.py`) can be trivially extended to include more Nepali and international sources, growing the content base. |
| O6 | **Monetisation potential** | With enough traffic, the platform could host editorial advertisements or offer premium categorised feeds as a subscription product. |
| O7 | **Research publication** | The hybrid rule-based + Naive Bayes approach for low-resource Nepali news classification could be written up as a short research paper for a student conference. |

---

### Threats

| # | Threat | Detail |
|---|---|---|
| T1 | **RSS feed deprecation** | News publishers may disable or restructure their RSS feeds without notice, breaking the sync pipeline. |
| T2 | **Scraping legal risk** | Some publishers have terms-of-service clauses prohibiting automated scraping. The project should ideally use only RSS-provided content in production. |
| T3 | **Established competitors** | Platforms like Google News, Flipboard, and local aggregators like Nepali Times already exist. Daily Khabar differentiates through its open-source, locally-deployable, AI-transparent approach. |
| T4 | **Scalability ceiling** | The in-memory cache and file-based backup approach will not scale beyond a few thousand articles without architectural changes (e.g., proper search indexing, pagination at the DB level). |
| T5 | **ML model accuracy limitations** | Naive Bayes is a strong baseline but will be outperformed by transformer-based models (BERT, etc.) for edge cases and ambiguous articles. For a final year project this is acceptable; for a commercial product it would need upgrading. |

---

## 6. Comparison With Typical Final Year Projects

| Typical Project | Daily Khabar Advantage |
|---|---|
| Library Management System | Daily Khabar adds ML classification, live data fetching, and NLP — all absent from a basic CRUD app |
| Student Result Management | Daily Khabar involves real-time web scraping, RSS parsing, and AI-driven content processing |
| Online Shopping Cart | Daily Khabar builds a recommendation engine from scratch instead of using a pre-built e-commerce plugin |
| Hospital Management System | Daily Khabar demonstrates data pipeline design, ML model training, and text analytics |
| Blog CMS | Daily Khabar adds auto-categorisation, auto-summarisation, and content-based recommendations — making it an intelligent CMS |

Daily Khabar sits **above the average** for BSc CSIT final year projects in terms of:
- **Technical depth** (multiple ML algorithms implemented without libraries)
- **System integration** (5 distinct modules working together)
- **Real-world applicability** (live data, real news, real users can sign up and use it today)
- **Academic coverage** (touches at least 8 distinct CS subject areas)

---

## 7. Conclusion

Daily Khabar is not a minimum viable product assembled from tutorials. It is a thoughtfully designed, multi-layered information system that:

1. **Solves a real problem** — fragmented Nepali online news, reading fatigue, and lack of local content tools
2. **Applies genuine CS theory** — Bayes' theorem for classification, vector space model for recommendations, TF scoring for summarisation
3. **Demonstrates engineering discipline** — modular architecture, error handling, security awareness, and a clean separation of concerns
4. **Produces a live, demonstrable result** — a running web application with real data that evaluators can use and test during viva

It comfortably meets — and in several respects exceeds — the standard expected of a **final year project for a Bachelor of Science in Computer Science and Information Technology**, particularly in a Nepali academic context where projects combining web development, database design, natural language processing, and data engineering in a single coherent system are relatively rare.

---

*Document prepared as part of the Daily Khabar Final Year Project submission.*
