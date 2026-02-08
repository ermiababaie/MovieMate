import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text
from PIL import Image  

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

db = SQLAlchemy(app)

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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_admin():
    if "user_id" not in session:
        return False
    user = User.query.get(session["user_id"])
    return user and user.username.lower() == "admin"


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

        hashed = generate_password_hash(password)
        new_user = User(username=username,email=email,firstname=firstname,lastname=lastname,password=hashed)
        db.session.add(new_user)
        db.session.commit()

        session["user_id"] = new_user.id
        return redirect(url_for("home"))

    return render_template("register.html")

@app.route('/login', methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password,password):
            session["user_id"] = user.id
            return redirect(url_for("home"))
        else:
            flash("Username or password incorrect!", "error")
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
    movies = Movie.query.all()
    if is_admin():
        return render_template("admin_dashboard.html", movies=movies)
    else:
        return render_template("index.html")  
    
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
        try:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filename = f"{new_movie.id}.jpg"  
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            img = Image.open(file)
            rgb_img = img.convert('RGB')  
            rgb_img.save(filepath, format='JPEG')

        except Exception as e:
            flash(f"Error saving poster: {e}", "error")
            print(e)
    else:
        flash("No poster uploaded or invalid file type", "warning")

    flash("Movie added successfully!", "success")
    return redirect(url_for("home"))

@app.route('/admin/delete/<int:movie_id>', methods=["POST"])
def delete_movie(movie_id):
    if not is_admin():
        flash("Access denied!", "error")
        return redirect(url_for("home"))

    movie = Movie.query.get(movie_id)
    if movie:
        poster_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{movie.id}.jpg")
        if os.path.exists(poster_path):
            os.remove(poster_path)

        db.session.execute(text("DELETE FROM actor_movies WHERE movie_id=:m"), {"m": movie.id})
        db.session.delete(movie)
        db.session.commit()
        flash("Movie deleted successfully!", "success")

    return redirect(url_for("home"))

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
        JOIN users ON comment.userID = users.id
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
            "SELECT rate FROM user_votes WHERE userID=:u AND movie=:m"
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
    new_comment = Comment(userid=session["user_id"], movie=movie_id, content=content)
    db.session.add(new_comment)
    db.session.commit()
    return redirect(url_for("movie_detail", movie_id=movie_id))

@app.route('/movie/<int:movie_id>/vote', methods=["POST"])
def vote(movie_id):
    if "user_id" not in session:
        flash("Login required!", "error")
        return redirect(url_for("login"))

    rate = int(request.form.get("rate"))
    existing = UserVote.query.filter_by(userid=session["user_id"], movie=movie_id).first()
    if existing:
        existing.rate = rate
    else:
        new_vote = UserVote(userid=session["user_id"], movie=movie_id, rate=rate)
        db.session.add(new_vote)
    db.session.commit()
    return redirect(url_for("movie_detail", movie_id=movie_id))

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

if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
