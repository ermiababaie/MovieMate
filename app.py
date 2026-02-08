import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from PIL import Image

# === Flask App ===
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "devsecret123")  # default for testing
app.debug = True

# === Database Config ===
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///test.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# === Upload Config ===
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# === Initialize DB ===
db = SQLAlchemy(app)

# === Models ===
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), nullable=False, unique=True)
    email = db.Column(db.Text, nullable=False, unique=True)
    firstname = db.Column(db.String(30))
    lastname = db.Column(db.String(30))
    password = db.Column(db.String(255), nullable=False)

class Movie(db.Model):
    __tablename__ = 'movie'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)   
    release = db.Column(db.Integer, nullable=False)
    story = db.Column(db.Text, nullable=False)         
    director = db.Column(db.Integer, nullable=False)

class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.Integer, nullable=False)
    movie = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text)

class UserVote(db.Model):
    __tablename__ = 'user_votes'
    userid = db.Column(db.Integer, primary_key=True)
    movie = db.Column(db.Integer, primary_key=True)
    rate = db.Column(db.Integer, nullable=False)

class Actor(db.Model):
    __tablename__ = 'actor'
    id = db.Column(db.Integer, primary_key=True)
    firstname = db.Column(db.String(30), nullable=False)
    lastname = db.Column(db.String(30), nullable=False)

class ActorMovies(db.Model):
    __tablename__ = 'actor_movies'
    movie_id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, nullable=False)

#test
@app.route('/test_movies')
def test_movies():
    movies = Movie.query.all()
    return f"Found {len(movies)} movies"

# === Helper Functions ===
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_admin():
    try:
        user_id = session.get("user_id")
        if not user_id:
            return False
        user = User.query.get(user_id)
        if not user:
            return False
        return user.username.lower() == "admin"
    except SQLAlchemyError as e:
        print(f"[is_admin] Exception: {e}")
        return False

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Ensure tables exist
with app.app_context():
    db.create_all()

# === Routes ===
@app.route('/register', methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        firstname = request.form.get("firstname")
        lastname = request.form.get("lastname")
        password = request.form.get("password")

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "error")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered!", "error")
            return redirect(url_for("register"))

        try:
            hashed = generate_password_hash(password)
            new_user = User(username=username, email=email, firstname=firstname, lastname=lastname, password=hashed)
            db.session.add(new_user)
            db.session.commit()

            session["user_id"] = new_user.id
            return redirect(url_for("home"))

        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"[register] Exception: {e}")
            flash("Error creating account. Try again.", "error")
            return redirect(url_for("register"))

    return render_template("register.html")

@app.route('/login', methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        try:
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                session["user_id"] = user.id
                return redirect(url_for("home"))
            else:
                flash("Username or password incorrect!", "error")
                return redirect(url_for("login"))
        except SQLAlchemyError as e:
            print(f"[login] Exception: {e}")
            flash("Login error. Try again.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route('/logout')
def logout():
    session.pop("user_id",None)
    return redirect(url_for("login"))

@app.route('/')
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    try:
        movies = Movie.query.all()
    except SQLAlchemyError as e:
        print(f"[home] DB Error fetching movies: {e}")
        movies = []

    admin = is_admin()
    return render_template("index.html" if not admin else "admin_dashboard.html", movies=movies)

# === Admin Routes ===
@app.route('/admin/add', methods=["POST"])
def add_movie():
    if not is_admin():
        flash("Access denied!", "error")
        return redirect(url_for("home"))

    name = request.form.get("name")
    release = request.form.get("release")
    story = request.form.get("story")
    director = request.form.get("director")
    actor_ids = request.form.get("actors", "").split(",")

    try:
        new_movie = Movie(name=name, release=release, story=story, director=director)
        db.session.add(new_movie)
        db.session.commit()

        for aid in actor_ids:
            aid = aid.strip()
            if aid.isdigit():
                db.session.execute(text(
                    "INSERT INTO actor_movies(movie_id, actor_id) VALUES (:movie_id,:actor_id)"
                ), {"movie_id": new_movie.id, "actor_id": int(aid)})
        db.session.commit()

        file = request.files.get("poster")
        if file and allowed_file(file.filename):
            filename = f"{new_movie.id}.jpg"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            img = Image.open(file)
            rgb_img = img.convert('RGB')
            rgb_img.save(filepath, format='JPEG')

        flash("Movie added successfully!", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"[add_movie] Exception: {e}")
        flash("Error adding movie.", "error")
    except Exception as e:
        print(f"[add_movie] Poster error: {e}")
        flash(f"Error saving poster: {e}", "error")

    return redirect(url_for("home"))

@app.route('/admin/delete/<int:movie_id>', methods=["POST"])
def delete_movie(movie_id):
    if not is_admin():
        flash("Access denied!", "error")
        return redirect(url_for("home"))

    try:
        movie = Movie.query.get(movie_id)
        if movie:
            poster_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{movie.id}.jpg")
            if os.path.exists(poster_path):
                os.remove(poster_path)

            db.session.execute(text("DELETE FROM actor_movies WHERE movie_id=:m"), {"m": movie.id})
            db.session.delete(movie)
            db.session.commit()
            flash("Movie deleted successfully!", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"[delete_movie] Exception: {e}")
        flash("Error deleting movie.", "error")

    return redirect(url_for("home"))

# === Movie Routes ===
@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    movie = Movie.query.get(movie_id)
    if not movie:
        flash("Movie not found!", "error")
        return redirect(url_for("home"))

    actors = db.session.execute(text("""
        SELECT actor.id, actor.firstname, actor.lastname
        FROM actor
        WHERE actor.id IN (
            SELECT actor_id FROM actor_movies WHERE movie_id=:m
        )
    """), {"m": movie.id}).fetchall()

    comments = db.session.execute(text("""
        SELECT comment.*, users.username
        FROM comment
        JOIN users ON comment.userid = users.id
        WHERE comment.movie=:m
        ORDER BY comment.id DESC
    """), {"m": movie.id}).fetchall()

    avg_rate_res = db.session.execute(text(
        "SELECT AVG(rate) as avg_rate FROM user_votes WHERE movie=:m"
    ), {"m": movie.id}).fetchone()
    avg_rate = round(avg_rate_res.avg_rate,1) if avg_rate_res.avg_rate else "N/A"

    user_rate = None
    if "user_id" in session:
        user_vote_res = db.session.execute(text(
            "SELECT rate FROM user_votes WHERE userid=:u AND movie=:m"
        ), {"u": session["user_id"], "m": movie.id}).fetchone()
        user_rate = user_vote_res.rate if user_vote_res else None

    return render_template("movie_details.html",
                           movie=movie, actors=actors, comments=comments,
                           avg_rate=avg_rate, user_rate=user_rate)

@app.route('/movie/<int:movie_id>/comment', methods=["POST"])
def add_comment(movie_id):
    if "user_id" not in session:
        flash("Login required!", "error")
        return redirect(url_for("login"))

    content = request.form.get("content")
    try:
        new_comment = Comment(userid=session["user_id"], movie=movie_id, content=content)
        db.session.add(new_comment)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"[add_comment] Exception: {e}")
        flash("Error adding comment.", "error")
    return redirect(url_for("movie_detail", movie_id=movie_id))

@app.route('/movie/<int:movie_id>/vote', methods=["POST"])
def vote(movie_id):
    if "user_id" not in session:
        flash("Login required!", "error")
        return redirect(url_for("login"))

    try:
        rate = int(request.form.get("rate"))
        existing = UserVote.query.filter_by(userid=session["user_id"], movie=movie_id).first()
        if existing:
            existing.rate = rate
        else:
            new_vote = UserVote(userid=session["user_id"], movie=movie_id, rate=rate)
            db.session.add(new_vote)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"[vote] Exception: {e}")
        flash("Error saving vote.", "error")
    return redirect(url_for("movie_detail", movie_id=movie_id))

# === API ===
@app.route('/api/movies')
def api_movies():
    movies = Movie.query.all()
    data = []
    for m in movies:
        avg_rate_res = db.session.execute(text(
            "SELECT AVG(rate) as avg_rate FROM user_votes WHERE movie=:m"
        ), {"m": m.id}).fetchone()
        avg_rate = round(avg_rate_res.avg_rate,1) if avg_rate_res.avg_rate else 0
        data.append({
            "id": m.id,
            "name": m.name,
            "release": m.release,
            "story": m.story,
            "avg_rate": avg_rate
        })
    return jsonify(data)

# === Run App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
