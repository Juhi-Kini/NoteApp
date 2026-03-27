# app.py
from flask import Flask, render_template, request, redirect, session
from flask_pymongo import PyMongo
from flask_ckeditor import CKEditor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from bson.objectid import ObjectId
from collections import Counter

# ----------------------------
# Flask app configuration
# ----------------------------
app = Flask(__name__)
app.config["MONGO_URI"] = "mongodb+srv://juhikini25_db_user:TIFewpuIXoRLdtKt@cluster0.mhimqp8.mongodb.net/noteapp?retryWrites=true&w=majority"
app.secret_key = "supersecretkey"  # Needed for sessions

# CKEditor configuration - DISABLE CSRF for simplicity
app.config['WTF_CSRF_ENABLED'] = False  # This disables CSRF for CKEditor
app.config['CKEDITOR_SERVE_LOCAL'] = True
app.config['CKEDITOR_HEIGHT'] = 400
app.config['CKEDITOR_ENABLE_CSRF'] = False  # Explicitly disable CSRF for CKEditor

ckeditor = CKEditor(app)
mongo = PyMongo(app)

# ----------------------------
# ALL ROUTES GO HERE
# ----------------------------

@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/dashboard")
    return redirect("/login")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        
        # Check if user already exists
        existing_user = mongo.db.users.find_one({"email": email})
        if existing_user:
            return "User already exists!"
        
        # Insert new user
        mongo.db.users.insert_one({
            "name": name, 
            "email": email, 
            "password": password
        })
        return redirect("/login")
    
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        # Find user by email
        user = mongo.db.users.find_one({"email": email})
        
        # Check if user exists and password is correct
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["user_name"] = user["name"]
            return redirect("/dashboard")
        else:
            return "Invalid credentials!"
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    
    # Get search query from URL
    search_query = request.args.get('search', '').strip()
    
    # Build the query
    query = {"user_id": session["user_id"]}
    
    if search_query:
        # Search in title OR tags (case-insensitive)
        query["$or"] = [
            {"title": {"$regex": search_query, "$options": "i"}},
            {"tags": {"$regex": search_query, "$options": "i"}}
        ]
    
    # Get notes with search filter
    notes = mongo.db.notes.find(query).sort("updated_at", -1)
    
    # Convert cursor to list and get count
    notes_list = list(notes)
    notes_count = len(notes_list)
    
    return render_template("dashboard.html", notes=notes_list, notes_count=notes_count, search_query=search_query)
    
@app.route("/note/new", methods=["GET", "POST"])
def new_note():
    if "user_id" not in session:
        return redirect("/login")
    
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]  # CKEditor content (HTML)
        tags = request.form["tags"].split(",") if request.form["tags"] else []
        
        # Clean up tags (remove extra spaces)
        cleaned_tags = [tag.strip() for tag in tags if tag.strip()]
        
        # Insert new note
        mongo.db.notes.insert_one({
            "user_id": session["user_id"],
            "title": title,
            "content": content,  # Store HTML directly
            "tags": cleaned_tags,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        })
        return redirect("/dashboard")
    
    # GET request - show empty form
    return render_template("note_form.html", note=None)

@app.route("/note/<note_id>")
def view_note(note_id):
    if "user_id" not in session:
        return redirect("/login")
    
    # Find the note by ID and ensure it belongs to the current user
    note = mongo.db.notes.find_one({"_id": ObjectId(note_id), "user_id": session["user_id"]})
    
    if not note:
        return "Note not found or access denied!"
    
    return render_template("note_view.html", note=note)

@app.route("/note/<note_id>/edit", methods=["GET", "POST"])
def edit_note(note_id):
    if "user_id" not in session:
        return redirect("/login")
    
    # Find the note by ID and ensure it belongs to the current user
    note = mongo.db.notes.find_one({"_id": ObjectId(note_id), "user_id": session["user_id"]})
    
    if not note:
        return "Note not found or access denied!"
    
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        tags = request.form["tags"].split(",") if request.form["tags"] else []
        
        # Clean up tags (remove extra spaces)
        cleaned_tags = [tag.strip() for tag in tags if tag.strip()]
        
        # Update the note
        mongo.db.notes.update_one(
            {"_id": ObjectId(note_id)},
            {"$set": {
                "title": title,
                "content": content,
                "tags": cleaned_tags,
                "updated_at": datetime.now()
            }}
        )
        return redirect("/dashboard")
    
    # GET request - show form with existing note data
    return render_template("note_form.html", note=note)

@app.route("/note/<note_id>/delete", methods=["POST"])
def delete_note(note_id):
    if "user_id" not in session:
        return redirect("/login")
    
    # Delete the note (ensure it belongs to the current user)
    result = mongo.db.notes.delete_one({"_id": ObjectId(note_id), "user_id": session["user_id"]})
    
    if result.deleted_count == 0:
        return "Note not found or access denied!"
    
    return redirect("/dashboard")

# ----------------------------
# NEW STATISTICS ROUTE
# ----------------------------
@app.route("/stats")
def stats():
    if "user_id" not in session:
        return redirect("/login")
    
    # Get all notes for the current user
    notes = list(mongo.db.notes.find({"user_id": session["user_id"]}))
    
    if not notes:
        return render_template("stats.html", stats=None, has_notes=False)
    
    # Calculate statistics
    total_notes = len(notes)
    
    # Word count
    total_words = 0
    all_content = ""
    for note in notes:
        # Rough word count (split by spaces) - strip HTML tags for accurate count
        import re
        clean_text = re.sub('<.*?>', '', note['content'])  # Remove HTML tags
        words = clean_text.split()
        total_words += len(words)
        all_content += " " + clean_text
    
    # Average words per note
    avg_words = round(total_words / total_notes, 1) if total_notes > 0 else 0
    
    # Tag analysis
    all_tags = []
    for note in notes:
        if note.get('tags'):
            all_tags.extend(note['tags'])
    
    # Most used tags
    tag_counter = Counter(all_tags)
    most_common_tags = tag_counter.most_common(5)  # Top 5 tags
    
    # Notes by day of week
    days_count = [0, 0, 0, 0, 0, 0, 0]  # Mon=0, Sun=6
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    for note in notes:
        if note.get('created_at'):
            day = note['created_at'].weekday()
            days_count[day] += 1
    
    # Find busiest day
    busiest_day_index = days_count.index(max(days_count)) if max(days_count) > 0 else 0
    busiest_day = day_names[busiest_day_index]
    
    # Notes by month
    months = {}
    for note in notes:
        if note.get('created_at'):
            month_year = note['created_at'].strftime('%B %Y')
            months[month_year] = months.get(month_year, 0) + 1
    
    # Longest note (by word count)
    longest_note = None
    shortest_note = None
    
    if notes:
        # Helper function to get word count without HTML
        def get_word_count(note):
            import re
            clean_text = re.sub('<.*?>', '', note['content'])
            return len(clean_text.split())
        
        longest_note = max(notes, key=get_word_count)
        shortest_note = min(notes, key=get_word_count)
    
    # Calculate writing streak (simplified)
    streak = "No activity yet"
    if notes and notes[-1].get('created_at'):
        from datetime import date, timedelta
        last_note_date = notes[-1]['created_at'].date()
        today = date.today()
        if last_note_date == today:
            streak = "🔥 Active today!"
        elif last_note_date == today - timedelta(days=1):
            streak = "⚡ Active yesterday"
        else:
            streak = f"📅 Last active {last_note_date}"
    
    stats_data = {
        'total_notes': total_notes,
        'total_words': total_words,
        'avg_words': avg_words,
        'most_common_tags': most_common_tags,
        'busiest_day': busiest_day,
        'busiest_day_count': max(days_count) if days_count else 0,
        'months': months,
        'longest_note': longest_note,
        'shortest_note': shortest_note,
        'streak': streak,
        'tag_count': len(all_tags)
    }
    
    return render_template("stats.html", stats=stats_data, has_notes=True)

# Optional: Add a test route to check if MongoDB is connected
@app.route("/test-db")
def test_db():
    try:
        # Try to get collection names
        collections = mongo.db.list_collection_names()
        return f"MongoDB connected successfully! Collections: {collections}"
    except Exception as e:
        return f"MongoDB connection error: {str(e)}"

# ----------------------------
# Main: Run App
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
