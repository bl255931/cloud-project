"""CloudLearn - a simple cloud based Learning Management System (Flask)."""
import os
import sqlite3
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
DATABASE = os.path.join(os.path.dirname(__file__), "lms.db")

SEED_COURSES = [
    ("Python for Beginners", "Programming", "Dr. Anita Rao",
     "Learn Python from scratch: variables, loops, functions and projects.", 8),
    ("Web Development with HTML & CSS", "Web", "Karthik Menon",
     "Build responsive websites with modern HTML5 and CSS3.", 6),
    ("Cloud Computing Fundamentals", "Cloud", "Priya Nair",
     "Understand IaaS, PaaS, SaaS, storage, networking and deployment.", 10),
    ("Data Science with Pandas", "Data", "Dr. Suresh Kumar",
     "Analyse and visualise data using Python, Pandas and Matplotlib.", 9),
    ("Database Design & SQL", "Database", "Meera Iyer",
     "Design relational databases and write powerful SQL queries.", 7),
    ("Cyber Security Essentials", "Security", "Arjun Das",
     "Protect systems and data: threats, encryption and best practices.", 8),
]


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS courses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, category TEXT NOT NULL,
            instructor TEXT NOT NULL, description TEXT NOT NULL,
            lessons INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS enrollments(
            user_id INTEGER, course_id INTEGER,
            completed INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, course_id));
    """)
    if db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO courses(title,category,instructor,description,lessons)"
            " VALUES(?,?,?,?,?)", SEED_COURSES)
    db.commit()
    db.close()


# -------------------------------------------------------------------- auth
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if not (name and email and len(password) >= 6):
            flash("Fill all fields; password needs 6+ characters.", "error")
        else:
            try:
                db = get_db()
                db.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                           (name, email, generate_password_hash(password)))
                db.commit()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email=?",
                                (email,)).fetchone()
        if user and check_password_hash(user["password"], request.form["password"]):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


# ------------------------------------------------------------------ routes
@app.route("/")
def home():
    db = get_db()
    featured = db.execute("SELECT * FROM courses LIMIT 3").fetchall()
    stats = {
        "courses": db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "students": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
    }
    return render_template("index.html", featured=featured, stats=stats)


@app.route("/courses")
def courses():
    q = request.args.get("q", "").strip()
    db = get_db()
    if q:
        like = f"%{q}%"
        rows = db.execute(
            "SELECT * FROM courses WHERE title LIKE ? OR category LIKE ? "
            "OR instructor LIKE ?", (like, like, like)).fetchall()
    else:
        rows = db.execute("SELECT * FROM courses").fetchall()
    return render_template("courses.html", courses=rows, q=q)


@app.route("/course/<int:course_id>")
def course_detail(course_id):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE id=?",
                        (course_id,)).fetchone()
    if course is None:
        return render_template("404.html"), 404
    enrolled = None
    if "user_id" in session:
        enrolled = db.execute(
            "SELECT * FROM enrollments WHERE user_id=? AND course_id=?",
            (session["user_id"], course_id)).fetchone()
    return render_template("course_detail.html", course=course, enrolled=enrolled)


@app.route("/enroll/<int:course_id>", methods=["POST"])
@login_required
def enroll(course_id):
    db = get_db()
    db.execute("INSERT OR IGNORE INTO enrollments(user_id,course_id) VALUES(?,?)",
               (session["user_id"], course_id))
    db.commit()
    flash("You are enrolled. Happy learning!", "success")
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/progress/<int:course_id>", methods=["POST"])
@login_required
def progress(course_id):
    db = get_db()
    course = db.execute("SELECT lessons FROM courses WHERE id=?",
                        (course_id,)).fetchone()
    row = db.execute(
        "SELECT completed FROM enrollments WHERE user_id=? AND course_id=?",
        (session["user_id"], course_id)).fetchone()
    if course and row and row["completed"] < course["lessons"]:
        db.execute("UPDATE enrollments SET completed=completed+1 "
                   "WHERE user_id=? AND course_id=?",
                   (session["user_id"], course_id))
        db.commit()
        flash("Lesson marked as complete!", "success")
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/dashboard")
@login_required
def dashboard():
    rows = get_db().execute("""
        SELECT c.id, c.title, c.category, c.instructor, c.lessons, e.completed
        FROM enrollments e JOIN courses c ON c.id = e.course_id
        WHERE e.user_id=?""", (session["user_id"],)).fetchall()
    return render_template("dashboard.html", my_courses=rows)


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
