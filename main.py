import os
from datetime import date
from functools import wraps
from typing import List

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from forms import CommentForm, CreatePostForm, LoginForm, RegisterForm
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DB_URI")
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(1000))
    posts: Mapped[List["BlogPost"]] = relationship(back_populates="author")
    comments: Mapped[List["BlogComment"]] = relationship(back_populates="author")


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    author: Mapped["User"] = relationship(back_populates="posts")
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments: Mapped[List["BlogComment"]] = relationship(back_populates="post")


class BlogComment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    author: Mapped["User"] = relationship(back_populates="comments")
    post_id: Mapped[int] = mapped_column(ForeignKey("blog_posts.id"), nullable=False)
    post: Mapped["BlogPost"] = relationship(back_populates="comments")
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


with app.app_context():
    db.create_all()


def admin_only(func):

    @wraps(func)
    def decorated_view(*args, **kwargs):
        if current_user.id == 1:
            return func(*args, **kwargs)
        else:
            return abort(403)

    return decorated_view


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        new_user = User(
            name=request.form["name"],
            email=request.form["email"],
            password=generate_password_hash(
                password=request.form["password"], method="pbkdf2:sha256", salt_length=8
            ),
        )
        db.session.add(new_user)
        try:
            db.session.commit()
            login_user(new_user)
            return redirect(url_for("get_all_posts"))
        except:
            flash("You have already registered.")
            return redirect(url_for("login"))
    form = RegisterForm()
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = db.session.execute(
            db.select(User).where(User.email == request.form["email"])
        ).scalar()
        if user:
            if check_password_hash(user.password, request.form["password"]):
                login_user(user)
                flash("Logged in successfully.")
                return redirect(url_for("get_all_posts"))
            else:
                flash("Password incorrect.")
        else:
            flash("Email not recognized.")
    form = LoginForm()
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("get_all_posts"))


@app.route("/")
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    form = CommentForm()
    if form.validate_on_submit():
        new_comment = BlogComment(
            author=current_user,
            post=requested_post,
            body=form.body.data,
            date=date.today().strftime("%B %d, %Y"),
        )
        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for("show_post", post_id=post_id))
    comments = requested_post.comments
    return render_template(
        "post.html", post=requested_post, form=form, comments=comments
    )


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y"),
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body,
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for("get_all_posts"))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    app.run(debug=False)
