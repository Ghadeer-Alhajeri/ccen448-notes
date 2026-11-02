import os
import re
from datetime import datetime, timezone
from functools import wraps

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()
csrf = CSRFProtect()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'false').lower() == 'true',
        MAX_CONTENT_LENGTH=64 * 1024,
        WTF_CSRF_SSL_STRICT=True,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config['SECRET_KEY'] or not app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError('Set SECRET_KEY and DATABASE_URL before starting the application.')
    # Relative links and same-origin forms work with both the IP URL and a
    # temporary tunnel URL. No forwarded-header trust is needed for this app.
    db.init_app(app)
    csrf.init_app(app)

    @app.before_request
    def load_user():
        g.user = db.session.get(User, session['user_id']) if session.get('user_id') else None

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return wrapped

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if g.user:
            return redirect(url_for('index'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            if not re.fullmatch(r'[a-z0-9_]{3,32}', username):
                flash('Use 3–32 letters, numbers, or underscores for your username.', 'error')
            elif not 10 <= len(password) <= 128:
                flash('Use a password between 10 and 128 characters.', 'error')
            else:
                user = User(username=username, password_hash=generate_password_hash(password))
                db.session.add(user)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash('That username is already taken.', 'error')
                else:
                    session.clear()
                    session['user_id'] = user.id
                    flash('Your account is ready. Create your first note.', 'success')
                    return redirect(url_for('index'))
        return render_template('auth.html', registering=True)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if g.user:
            return redirect(url_for('index'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            user = db.session.scalar(db.select(User).where(User.username == username))
            if user and check_password_hash(user.password_hash, password):
                session.clear()
                session['user_id'] = user.id
                return redirect(url_for('index'))
            flash('Incorrect username or password.', 'error')
        return render_template('auth.html', registering=False)

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    @login_required
    def index():
        notes = db.session.scalars(db.select(Note).where(Note.user_id == g.user.id).order_by(Note.created_at.desc(), Note.id.desc())).all()
        return render_template('index.html', notes=notes)

    @app.post('/notes')
    @login_required
    def add_note():
        title = request.form.get('title', '').strip()
        body = request.form.get('body', '').strip()
        if not title or len(title) > 120 or not body or len(body) > 10000:
            flash('Add a title (up to 120 characters) and a note (up to 10,000 characters).', 'error')
        else:
            db.session.add(Note(user_id=g.user.id, title=title, body=body))
            db.session.commit()
            flash('Note saved.', 'success')
        return redirect(url_for('index'))

    @app.post('/notes/<int:note_id>/delete')
    @login_required
    def delete_note(note_id):
        note = db.session.scalar(db.select(Note).where(Note.id == note_id, Note.user_id == g.user.id))
        if note is None:
            abort(404)
        db.session.delete(note)
        db.session.commit()
        flash('Note deleted.', 'success')
        return redirect(url_for('index'))

    @app.get('/health')
    def health():
        try:
            db.session.execute(db.select(1))
        except Exception:
            db.session.rollback()
            return {'status': 'unavailable'}, 503
        return {'status': 'ok'}

    @app.cli.command('init-db')
    def init_db():
        db.create_all()
        click.echo('Database tables are ready.')

    return app
