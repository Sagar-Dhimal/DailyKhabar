from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
# pyrefly: ignore [missing-import]
from bson import ObjectId
import os
import math
from datetime import datetime
from functools import wraps

from mongo import db, DATASET_PATH, utc_iso, export_to_json, COLLECTION_MAP
from portal_ml import (
    load_articles, 
    summarize_text, 
    categorize_text, 
    init_classifier,
    summarization_accuracy,
    categorization_accuracy,
    get_recommendations
)
from generate_metrics import get_confusion_matrix_data

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-flask-secret")

def sync_db(collection):
    if collection in COLLECTION_MAP:
        export_to_json(collection, COLLECTION_MAP[collection])

UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

from werkzeug.utils import secure_filename

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

ARTICLES_CACHE = []

def refresh_articles_cache():
    global ARTICLES_CACHE
    
    csv_articles = load_articles(DATASET_PATH)
    
    db_articles = list(db.articles.find())
    db_map = {str(a.get("article_id")): a for a in db_articles}
    
    deleted_ids = {str(d["article_id"]) for d in db.deleted_articles.find()}
    
    final_data = []
    for csv_a in csv_articles:
        aid = str(csv_a.get("article_id"))
        if aid in deleted_ids:
            continue
        if aid in db_map:
            final_data.append(db_map[aid])
            del db_map[aid] 
        else:
            final_data.append(csv_a)
            
    for db_a in db_map.values():
        if str(db_a.get("article_id")) not in deleted_ids:
            final_data.append(db_a)
            
    final_data.sort(key=lambda x: str(x.get("published_at", "")), reverse=True)
    ARTICLES_CACHE = final_data
    
    init_classifier(ARTICLES_CACHE)

refresh_articles_cache()

def user_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login first.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login", next=request.path, tab="admin"))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_global_context():
    categories = sorted({a.get("category", "General") for a in ARTICLES_CACHE if a.get("category")})
    custom_cats = [c.get("name") for c in db.categories.find() if c.get("name")]
    for c in custom_cats:
        if c not in categories:
            categories.append(c)
    categories = sorted(list(set(categories)))
    return {"nav_categories": categories}

@app.route("/")
def index():
    q = (request.args.get("q") or "").strip().lower()
    cat = (request.args.get("category") or "").strip()
    page = int(request.args.get("page") or 1)
    per_page = 6
    
    data = ARTICLES_CACHE[:]
    if cat:
        data = [a for a in data if a.get("category") == cat]
    if q:
        data = [a for a in data if q in (a.get("title", "").lower() + " " + a.get("description", "").lower())]
    
    total_posts = len(data)
    total_pages = math.ceil(total_posts / per_page)
    
    start = (page - 1) * per_page
    end = start + per_page
    paged_articles = data[start:end]
    
    world_cup_articles = [a for a in ARTICLES_CACHE if a.get("category") == "World Cup 2026"][:5]
    
    return render_template(
        "index.html",
        articles=paged_articles,
        world_cup_articles=world_cup_articles,
        recent_articles=data[:5],
        query=request.args.get("q", ""),
        selected_category=cat,
        page=page,
        total_pages=total_pages
    )

@app.route("/article/<article_id>/")
def article_detail(article_id):
    article = next((a for a in ARTICLES_CACHE if str(a.get("article_id")) == str(article_id)), None)
    if not article:
        abort(404)
    
    all_comments = list(db.comments.find({"article_id": str(article_id), "status": "approved"}).sort("created_at", 1))
    
    roots = []
    by_parent = {}
    for c in all_comments:
        pid = str(c.get("parent_id", ""))
        if not pid:
            roots.append(c)
        else:
            if pid not in by_parent: by_parent[pid] = []
            by_parent[pid].append(c)
    
    recommendations = get_recommendations(article_id, ARTICLES_CACHE, top_n=4)
            
    return render_template("article.html", article=article, comments=roots, replies=by_parent, recommendations=recommendations)

@app.route("/article/<article_id>/comment", methods=["POST"])
@user_login_required
def add_comment(article_id):
    content = request.form.get("content", "").strip()
    parent_id = request.form.get("parent_id", "").strip()
    
    if not content:
        flash("Comment cannot be empty.", "warning")
        return redirect(url_for("article_detail", article_id=article_id))
        
    db.comments.insert_one({
        "article_id": str(article_id),
        "user_id": session.get("user_id"),
        "username": session.get("username"),
        "content": content,
        "parent_id": parent_id,
        "status": "pending", # Needs admin approval
        "created_at": utc_iso()
    })
    sync_db("comments")
    
    flash("Your comment has been submitted and is awaiting moderation.", "success")
    return redirect(url_for("article_detail", article_id=article_id))

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("user_dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        
        if not username or not email or not password:
            flash("All fields are required.", "warning")
            return redirect(url_for("register"))
        
        if db.users.find_one({"username": username}):
            flash("Username already taken.", "danger")
            return redirect(url_for("register"))
        
        if db.users.find_one({"email": email}):
            flash("Email already exists.", "danger")
            return redirect(url_for("register"))
        
        rec = {
            "username": username,
            "email": email,
            "password": generate_password_hash(password),
            "created_at": utc_iso(),
        }
        inserted = db.users.insert_one(rec)
        sync_db("users")
        session["user_id"] = str(inserted.inserted_id)
        session["username"] = username
        return redirect(request.form.get("next") or url_for("user_dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    tab = request.args.get("tab", "user")
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        login_type = request.form.get("login_type", "user") 
        
        if login_type == "admin":
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                session["admin_logged_in"] = True
                return redirect(request.form.get("next") or url_for("admin_dashboard"))
            else:
                flash("Invalid admin credentials.", "danger")
                return redirect(url_for("login", tab="admin"))
            
        user = db.users.find_one({"username": username})
        if user and check_password_hash(user.get("password", ""), password):
            session["user_id"] = str(user["_id"])
            session["username"] = user.get("username")
            return redirect(request.form.get("next") or url_for("user_dashboard"))
        
        flash("Invalid username or password.", "danger")
    return render_template("login.html", next=request.args.get("next", ""), tab=tab)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")
        db.queries.insert_one({
            "name": name,
            "email": email,
            "message": message,
            "status": "pending",
            "created_at": utc_iso(),
            "user_id": session.get("user_id")
        })
        sync_db("queries")
        flash("Thank you for your message. We'll get back to you soon!", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")

@app.route("/tools")
@user_login_required
def tools():
    return render_template("tools.html")

def handle_text_or_file():
    text = (request.form.get("raw_text") or "").strip()
    file = request.files.get("file_upload")
    if file and file.filename.endswith(".txt"):
        try:
            text = file.read().decode("utf-8")
        except Exception:
            flash("Error reading uploaded file. Ensure it is a valid .txt file.", "danger")
            return None
    return text

@app.route("/summarize", methods=["GET", "POST"])
@user_login_required
def summarize():
    result = None
    if request.method == "POST":
        text = handle_text_or_file()
        if not text:
            flash("Please provide text or upload a .txt file.", "warning")
            return redirect(url_for("summarize"))
        
        max_sentences = int(request.form.get("max_sentences") or 3)
        summary = summarize_text(text, max_sentences=max_sentences)
        acc = summarization_accuracy(text, summary)
        
        result = {
            "summary": summary,
            "accuracy_pct": acc,
            "classification_confidence": categorization_accuracy(text),
            "words_in": len(text.split()),
            "words_out": len(summary.split()),
        }
        
        db.user_activities.insert_one({
            "user_id": session.get("user_id"),
            "event_type": "summary",
            "title": "Summarized news text",
            "details": result,
            "created_at": utc_iso(),
        })
        sync_db("user_activities")
    return render_template("summarize.html", result=result)

@app.route("/classify", methods=["GET", "POST"])
@user_login_required
def classify():
    result = None
    if request.method == "POST":
        text = handle_text_or_file()
        if not text:
            flash("Please provide text or upload a .txt file.", "warning")
            return redirect(url_for("classify"))
        
        category = categorize_text(text)
        accuracy = categorization_accuracy(text)
        
        result = {
            "category": category,
            "accuracy_pct": accuracy,
            "words_in": len(text.split()),
        }
        
        db.user_activities.insert_one({
            "user_id": session.get("user_id"),
            "event_type": "classification",
            "title": f"Classified text as {category}",
            "details": result,
            "created_at": utc_iso(),
        })
        sync_db("user_activities")
    return render_template("classify.html", result=result)

@app.route("/user/dashboard")
@user_login_required
def user_dashboard():
    uid = session.get("user_id")
    activities = list(db.user_activities.find({"user_id": uid}).sort("created_at", -1).limit(20))
    comments = list(db.comments.find({"user_id": uid}).sort("created_at", -1).limit(10))
    queries = list(db.queries.find({"user_id": uid}).sort("created_at", -1).limit(10))
    
    stats = {
        "total_activities": db.user_activities.count_documents({"user_id": uid}),
        "total_summaries": db.user_activities.count_documents({"user_id": uid, "event_type": "summary"}),
        "total_classifications": db.user_activities.count_documents({"user_id": uid, "event_type": "classification"}),
        "total_comments": db.comments.count_documents({"user_id": uid}),
        "total_queries": db.queries.count_documents({"user_id": uid}),
        "approved_comments": db.comments.count_documents({"user_id": uid, "status": "approved"}),
        "answered_queries": db.queries.count_documents({"user_id": uid, "status": "answered"}),
    }
    
    return render_template(
        "user_dashboard.html",
        activities=activities,
        comments=comments,
        queries=queries,
        stats=stats
    )

@app.route("/admin/dashboard")
@admin_login_required
def admin_dashboard():
    total_posts = len(ARTICLES_CACHE)
    training_data = int(total_posts * 0.7)
    testing_data = total_posts - training_data
    
    sample = ARTICLES_CACHE[:20] if ARTICLES_CACHE else []
    cat_scores = []
    sum_scores = []
    for a in sample:
        text = ((a.get('title') or '') + ' ' + (a.get('full_content') or '')).strip()
        if text:
            cat_scores.append(categorization_accuracy(text))
            sm = a.get('summary', '')
            if sm:
                sum_scores.append(summarization_accuracy(text, sm))
    classifier_acc = round(sum(cat_scores) / len(cat_scores), 1) if cat_scores else 78.0
    summary_acc = round(sum(sum_scores) / len(sum_scores), 1) if sum_scores else 80.0
    
    cat_counts = {}
    for a in ARTICLES_CACHE:
        c = a.get("category", "General")
        cat_counts[c] = cat_counts.get(c, 0) + 1
    
    sorted_cats = sorted(cat_counts.items())
    chart_labels = [c[0] for c in sorted_cats]
    chart_values = [c[1] for c in sorted_cats]

    cm_data = get_confusion_matrix_data()
    
    stats = {
        "total_posts": total_posts,
        "training_data": training_data,
        "testing_data": testing_data,
        "classifier_acc": classifier_acc,
        "summary_acc": summary_acc,
        "total_categories": len(cat_counts),
        "total_users": db.users.count_documents({}),
        "total_summaries": db.user_activities.count_documents({"event_type": "summary"}),
        "total_queries": db.queries.count_documents({}),
        "unread_queries": db.queries.count_documents({"status": "pending"}),
        "read_queries": db.queries.count_documents({"status": "answered"}),
        "pending_comments": db.comments.count_documents({"status": "pending"}),
        "approved_comments": db.comments.count_documents({"status": "approved"}),
    }
    return render_template(
        "admin_dashboard.html", 
        stats=stats, 
        articles=ARTICLES_CACHE[:8], 
        admin_section="dashboard",
        chart_labels=chart_labels,
        chart_values=chart_values,
        cm_data=cm_data
    )

@app.route("/admin/posts")
@admin_login_required
def admin_posts():
    q = request.args.get("q", "").lower()
    cat = request.args.get("category", "")
    
    filtered = ARTICLES_CACHE
    if q:
        filtered = [a for a in filtered if q in a.get("title", "").lower() or q in a.get("full_content", "").lower()]
    if cat:
        filtered = [a for a in filtered if a.get("category") == cat]
        
    categories = sorted(list(set(a.get("category", "General") for a in ARTICLES_CACHE)))
    
    return render_template(
        "admin_posts.html", 
        posts=filtered, 
        categories=categories,
        selected_category=cat,
        query=q,
        admin_section="posts"
    )

@app.route("/admin/posts/new", methods=["GET", "POST"])
@admin_login_required
def admin_post_create():
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        
        image_url = None
        file = request.files.get("article_image")
        if file and file.filename:
            filename = secure_filename(f"{int(datetime.now().timestamp())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = f"/static/uploads/{filename}"
            
        category = categorize_text(content)
        category_acc = categorization_accuracy(content)
        summary = summarize_text(content, 3)
        
        if category == "General" and category_acc == 0.0:
            flash("Cannot save and publish: Article classification is invalid (0% confidence/General category). Please check the content.", "danger")
            temp_post = {
                "title": title,
                "full_content": content,
                "category": category,
                "summary": summary,
                "accuracy": category_acc
            }
            return render_template("admin_post_form.html", action="Create", post=temp_post, admin_section="posts")
            
        max_cache = max([int(a.get("article_id", 0)) for a in ARTICLES_CACHE if str(a.get("article_id", 0)).isdigit()] + [0])
        max_deleted = max([int(d.get("article_id", 0)) for d in db.deleted_articles.find() if str(d.get("article_id", 0)).isdigit()] + [0])
        max_db = max([int(a.get("article_id", 0)) for a in db.articles.find() if str(a.get("article_id", 0)).isdigit()] + [0])
        new_id = max(max_cache, max_deleted, max_db) + 1
        new_post = {
            "article_id": str(new_id),
            "title": title,
            "category": category,
            "description": summary,
            "summary": summary,
            "full_content": content,
            "url_to_image": image_url,
            "published_at": utc_iso()
        }
        db.articles.insert_one(new_post) 
        sync_db("articles")
        refresh_articles_cache()
        
        flash(f"Post created and auto-classified as '{category}'.", "success")
        return redirect(url_for("admin_posts"))
    
    return render_template("admin_post_form.html", action="Create", admin_section="posts")

@app.route("/admin/posts/edit/<article_id>", methods=["GET", "POST"])
@admin_login_required
def admin_post_edit(article_id):
    post = next((a for a in ARTICLES_CACHE if str(a.get("article_id")) == str(article_id)), None)
    if not post:
        abort(404)
        
    if request.method == "POST":
        content = request.form.get("content")
        category = categorize_text(content)
        category_acc = categorization_accuracy(content)
        summary = summarize_text(content, 3)
        
        image_url = post.get("url_to_image")
        file = request.files.get("article_image")
        if file and file.filename:
            filename = secure_filename(f"{int(datetime.now().timestamp())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = f"/static/uploads/{filename}"
            
        if category == "General" and category_acc == 0.0:
            flash("Cannot save and publish: Article classification is invalid (0% confidence/General category). Please check the content.", "danger")
            temp_post = {
                "article_id": article_id,
                "title": request.form.get("title"),
                "full_content": content,
                "category": category,
                "summary": summary,
                "url_to_image": image_url,
                "accuracy": category_acc
            }
            return render_template("admin_post_form.html", action="Edit", post=temp_post, admin_section="posts")
        
        post["title"] = request.form.get("title")
        post["category"] = category
        post["description"] = summary
        post["summary"] = summary
        post["full_content"] = content
        post["url_to_image"] = image_url
        
        db.articles.update_one({"article_id": str(article_id)}, {"$set": post}, upsert=True)
        sync_db("articles")
        
        refresh_articles_cache()
        
        flash(f"Post updated and re-classified as '{category}'.", "success")
        return redirect(url_for("admin_posts"))
        
    post_copy = post.copy()
    post_copy["accuracy"] = categorization_accuracy(post.get("full_content", ""))
    return render_template("admin_post_form.html", action="Edit", post=post_copy, admin_section="posts")

@app.route("/api/predict", methods=["POST"])
@admin_login_required
def api_predict():
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        return {"category": "N/A", "accuracy": 0, "summary": "", "summary_accuracy": 0}
    
    category = categorize_text(text)
    category_acc = categorization_accuracy(text)
    
    summary = summarize_text(text, 3)
    sum_acc = summarization_accuracy(text, summary)
    
    return {
        "category": category, 
        "accuracy": category_acc,
        "summary": summary,
        "summary_accuracy": sum_acc
    }

@app.route("/admin/posts/delete/<article_id>", methods=["POST"])
@admin_login_required
def admin_post_delete(article_id):
    db.articles.delete_one({"article_id": str(article_id)})
    sync_db("articles")
    db.deleted_articles.update_one(
        {"article_id": str(article_id)}, 
        {"$set": {"article_id": str(article_id), "deleted_at": utc_iso()}}, 
        upsert=True
    )
    refresh_articles_cache()
    flash("Post deleted successfully.", "success")
    return redirect(url_for("admin_posts"))

@app.route("/admin/posts/bulk-delete", methods=["POST"])
@admin_login_required
def admin_posts_bulk_delete():
    article_ids = request.form.getlist("article_ids")
    if not article_ids:
        flash("No articles selected for deletion.", "warning")
        return redirect(url_for("admin_posts"))
        
    for aid in article_ids:
        db.articles.delete_one({"article_id": str(aid)})
        db.deleted_articles.update_one(
            {"article_id": str(aid)}, 
            {"$set": {"article_id": str(aid), "deleted_at": utc_iso()}}, 
            upsert=True
        )
        
    sync_db("articles")
    refresh_articles_cache()
    flash(f"{len(article_ids)} posts deleted successfully.", "success")
    return redirect(url_for("admin_posts"))

@app.route("/admin/categories", methods=["GET", "POST"])
@admin_login_required
def admin_categories():
    if request.method == "POST":
        new_cat = request.form.get("category_name")
        if new_cat:
            if not db.categories.find_one({"name": new_cat}):
                db.categories.insert_one({"name": new_cat, "created_at": utc_iso()})
                sync_db("categories")
            flash(f"Category '{new_cat}' added.", "success")
        return redirect(url_for("admin_categories"))
    
    counts = {}
    for a in ARTICLES_CACHE:
        cat = a.get("category", "General")
        counts[cat] = counts.get(cat, 0) + 1
        
    for c in db.categories.find():
        name = c.get("name")
        if name and name not in counts:
            counts[name] = 0
            
    return render_template("admin_categories.html", category_counts=counts, admin_section="categories")

@app.route("/admin/categories/edit", methods=["POST"])
@admin_login_required
def admin_categories_edit():
    old_name = request.form.get("old_name")
    new_name = request.form.get("new_name")
    if old_name and new_name and old_name != new_name:
        db.categories.update_many({"name": old_name}, {"$set": {"name": new_name}})
        sync_db("categories")
        
        db.articles.update_many({"category": old_name}, {"$set": {"category": new_name}})
        sync_db("articles")
        
        for a in ARTICLES_CACHE:
            if a.get("category") == old_name:
                a["category"] = new_name
                
        init_classifier(ARTICLES_CACHE)
        flash(f"Category renamed to '{new_name}'.", "success")
    return redirect(url_for("admin_categories"))

@app.route("/admin/categories/delete", methods=["POST"])
@admin_login_required
def admin_categories_delete():
    cat_name = request.form.get("category_name")
    if cat_name:
        db.categories.delete_many({"name": cat_name})
        sync_db("categories")
        
        db.articles.update_many({"category": cat_name}, {"$set": {"category": "General"}})
        sync_db("articles")
        
        for a in ARTICLES_CACHE:
            if a.get("category") == cat_name:
                a["category"] = "General"
                
        init_classifier(ARTICLES_CACHE)
        flash(f"Category '{cat_name}' deleted.", "success")
    return redirect(url_for("admin_categories"))

@app.route("/admin/comments/action", methods=["POST"])
@admin_login_required
def admin_comment_action():
    comment_id = request.form.get("comment_id")
    action = request.form.get("action")
    
    if action == "approve":
        db.comments.update_one({"_id": ObjectId(comment_id)}, {"$set": {"status": "approved"}})
        flash("Comment approved.", "success")
    elif action == "reject":
        db.comments.update_one({"_id": ObjectId(comment_id)}, {"$set": {"status": "rejected"}})
        flash("Comment rejected.", "warning")
    elif action == "delete":
        db.comments.delete_one({"_id": ObjectId(comment_id)})
        flash("Comment deleted.", "danger")
    
    sync_db("comments")
        
    return redirect(url_for("admin_comments"))

@app.route("/admin/comments/reply", methods=["POST"])
@admin_login_required
def admin_comment_reply():
    parent_id = request.form.get("parent_id")
    content = request.form.get("content", "").strip()
    
    parent = db.comments.find_one({"_id": ObjectId(parent_id)})
    if not parent or not content:
        flash("Invalid reply.", "warning")
        return redirect(url_for("admin_comments"))
        
    db.comments.insert_one({
        "article_id": parent.get("article_id"),
        "user_id": "admin",
        "username": "Admin",
        "content": content,
        "parent_id": parent_id,
        "status": "approved", # Admin replies are auto-approved
        "created_at": utc_iso()
    })
    sync_db("comments")
    
    flash("Reply posted.", "success")
    return redirect(url_for("admin_comments"))

@app.route("/admin/comments")
@admin_login_required
def admin_comments():
    comments = list(db.comments.find().sort("created_at", -1))
    for c in comments:
        c["id"] = str(c["_id"])
    return render_template("admin_comments.html", comments=comments, admin_section="comments")

@app.route("/admin/comments/approve/<comment_id>")
@admin_login_required
def approve_comment(comment_id):
    db.comments.update_one({"_id": ObjectId(comment_id)}, {"$set": {"status": "approved"}})
    flash("Comment approved.", "success")
    return redirect(url_for("admin_comments"))

@app.route("/admin/comments/reject/<comment_id>")
@admin_login_required
def reject_comment(comment_id):
    db.comments.update_one({"_id": ObjectId(comment_id)}, {"$set": {"status": "rejected"}})
    flash("Comment rejected.", "success")
    return redirect(url_for("admin_comments"))

@app.route("/admin/queries")
@admin_login_required
def admin_queries():
    queries = list(db.queries.find().sort("created_at", -1))
    for q in queries:
        q["id"] = str(q["_id"])
    return render_template("admin_queries.html", queries=queries, admin_section="queries")

@app.route("/admin/queries/<query_id>")
@admin_login_required
def admin_query_detail(query_id):
    query = db.queries.find_one({"_id": ObjectId(query_id)})
    if not query:
        abort(404)
    query["id"] = str(query["_id"])
    return render_template("admin_query_detail.html", query=query, admin_section="queries")

@app.route("/admin/queries/reply/<query_id>", methods=["POST"])
@admin_login_required
def admin_query_reply(query_id):
    reply_content = request.form.get("reply_content", "").strip()
    if not reply_content:
        flash("Reply content cannot be empty.", "warning")
        return redirect(url_for("admin_query_detail", query_id=query_id))
    
    db.queries.update_one(
        {"_id": ObjectId(query_id)}, 
        {"$set": {"status": "answered", "admin_reply": reply_content, "replied_at": utc_iso()}}
    )
    sync_db("queries")
    
    flash("Reply dispatched successfully.", "success")
    return redirect(url_for("admin_queries"))

from news_sync import run_sync

@app.route("/admin/sync")
@admin_login_required
def admin_dataset_sync():
    new_articles = run_sync(db, ARTICLES_CACHE, categorize_text, summarize_text, utc_iso, sync_db)
    refresh_articles_cache()
    
    if new_articles > 0:
        flash(f"Sync complete. Added {new_articles} new articles and rotated out old content.", "success")
    else:
        flash("Sync complete. No new articles found at this time.", "info")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=True, port=8000)
