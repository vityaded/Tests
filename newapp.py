# app.py

import os
import uuid
import re
import random
import requests
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, abort, session, jsonify, Response
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, login_required, logout_user,
    current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError, generate_csrf
from sqlalchemy import MetaData
import bleach
from forms import SignupForm, LoginForm, AddTestForm, EditTestForm, TestForm, EditWordForm

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secure_secret_key'  # Replace with a strong, unpredictable secret key

# CSRF Protection
csrf = CSRFProtect(app)

# Configuration for file uploads
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Define naming conventions for constraints
naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

# Create a MetaData instance with the naming convention
metadata = MetaData(naming_convention=naming_convention)

# Configure the SQLAlchemy part of the app instance
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///books.db'  # Update as needed

# Create the SQLAlchemy db instance with the metadata
db = SQLAlchemy(app, metadata=metadata)

# Initialize Flask-Migrate
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User loader callback
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Define the User model
class User(UserMixin, db.Model):
    __tablename__ = 'user'  # Explicitly specify table name
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    test_results = db.relationship('TestResult', backref='user', lazy=True)
    tests_created = db.relationship('Test', backref='creator', lazy=True)
    vocabulary = db.relationship('Vocabulary', backref='user', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

from datetime import datetime

class Vocabulary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(150), nullable=False)
    translation = db.Column(db.String(150), nullable=False)
    pronunciation_url = db.Column(db.String(200), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    next_review = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    interval = db.Column(db.Float, nullable=False, default=0)  # Interval in days
    ease_factor = db.Column(db.Float, nullable=False, default=2.5)  # Default ease factor
    learning_stage = db.Column(db.Integer, nullable=False, default=0)  # 0: New, 1: First Step, 2: Second Step, 3: Learned

# Define the Book model
class Book(db.Model):
    __tablename__ = 'book'  # Explicitly specify table name
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    tests = db.relationship('Test', backref='book', lazy=True)

# Define the Test model
class Test(db.Model):
    __tablename__ = 'test'  # Explicitly specify table name
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    time_limit = db.Column(db.Integer, nullable=True)  # Time limit in minutes
    shuffle_sentences = db.Column(db.Boolean, default=False)
    shuffle_paragraphs = db.Column(db.Boolean, default=False)
    test_results = db.relationship('TestResult', backref='test', lazy=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Define the TestResult model
class TestResult(db.Model):
    __tablename__ = 'test_result'  # Explicitly specify table name
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)

# Error handler for 403 Forbidden
@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# Error handler for CSRF errors
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template('csrf_error.html', reason=e.description), 400

# Context processor to inject csrf_token into all templates
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf())

# Decorator to require admin access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# Route: Home Page
@app.route('/')
def index():
    books = Book.query.all()  # Fetch all books
    return render_template('index.html', books=books)

# Route: Sign Up
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = SignupForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()

        # Check if username is taken
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('signup'))

        # Create new user
        new_user = User(username=username)
        new_user.set_password(password)

        # Check if any users exist
        if User.query.count() == 0:
            # This is the first user, make them admin
            new_user.is_admin = True
        db.session.add(new_user)
        db.session.commit()

        # Log the user in and redirect to home page
        login_user(new_user)
        flash('Account created successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('signup.html', form=form)

# Route: Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()

        # Authenticate user
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html', form=form)

# Route: Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# Route: Add Test
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_test():
    form = AddTestForm()
    if form.validate_on_submit():
        book_title = form.book_title.data.strip()
        test_name = form.name.data.strip()
        test_content = form.content.data.strip()
        time_limit = form.time_limit.data
        shuffle_sentences = form.shuffle_sentences.data
        shuffle_paragraphs = form.shuffle_paragraphs.data

        # Check if the book exists
        book = Book.query.filter_by(title=book_title).first()
        if not book:
            # If the book doesn't exist, create it
            book = Book(title=book_title)
            db.session.add(book)
            db.session.commit()

        # Create the new test
        new_test = Test(
            name=test_name,
            content=test_content,
            book=book,
            time_limit=time_limit,
            shuffle_sentences=shuffle_sentences,
            shuffle_paragraphs=shuffle_paragraphs,
            created_by=current_user.id
        )
        db.session.add(new_test)
        db.session.commit()

        flash('Test added successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('add.html', form=form)

# Route: Edit Test
@app.route('/edit_test/<int:test_id>', methods=['GET', 'POST'])
@login_required
def edit_test(test_id):
    test = Test.query.get_or_404(test_id)

    form = EditTestForm(obj=test)

    if form.validate_on_submit():
        test.name = form.name.data
        test.time_limit = form.time_limit.data
        test.content = form.content.data
        test.shuffle_sentences = form.shuffle_sentences.data
        test.shuffle_paragraphs = form.shuffle_paragraphs.data
        db.session.commit()
        flash('Test updated successfully.', 'success')
        return redirect(url_for('index'))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger')

    return render_template('edit_test.html', form=form, test=test)

# Route: Take and Submit Test
@app.route('/test/<int:test_id>', methods=['GET', 'POST'])
@login_required
def take_test(test_id):
    test = Test.query.get_or_404(test_id)
    test_content = test.content
    time_limit = test.time_limit  # Time limit in minutes

    # Initialize variables
    processed_content = []
    correct_answers = {}
    question_counter = 1

    # Function to process the test content
    def process_content(content):
        nonlocal question_counter
        lines = content.splitlines()
        items = []

        if test.shuffle_sentences:
            # Split content into sentences
            sentences = []
            for line in lines:
                sentences.extend(re.split(r'(?<=[.!?]) +', line.strip()))
            # Shuffle sentences
            random.shuffle(sentences)
            items = sentences
        elif test.shuffle_paragraphs:
            # Split content into paragraphs
            paragraphs = [line.strip() for line in content.split('\n\n') if line.strip()]
            # Shuffle paragraphs
            random.shuffle(paragraphs)
            items = paragraphs
        else:
            # Default behavior
            items = lines

        # Generate HTML for drag-and-drop
        for item in items:
            item_id = f'item{question_counter}'
            correct_answers[item_id] = item.strip()
            processed_content.append({'id': item_id, 'content': item.strip()})
            question_counter += 1

    process_content(test_content)
    total_questions = question_counter - 1

    if request.method == 'POST':
        # Time limit enforcement
        start_time_str = session.get(f'start_time_{test_id}')
        if not start_time_str:
            flash('Test session expired. Please start the test again.', 'danger')
            return redirect(url_for('take_test', test_id=test_id))
        else:
            start_time = datetime.fromisoformat(start_time_str)
            elapsed_time = datetime.now(timezone.utc) - start_time
            elapsed_minutes = elapsed_time.total_seconds() / 60

            if time_limit and elapsed_minutes > time_limit:
                flash('Time limit exceeded. Test submitted automatically.', 'warning')

        # Get user responses
        user_order = request.form.getlist('item_order')

        # Calculate score
        score = 0
        for idx, item_id in enumerate(user_order):
            correct_item = list(correct_answers.values())[idx]
            user_item = correct_answers[item_id]
            if user_item == correct_item:
                score += 1

        # Save test result
        test_result = TestResult(
            score=score,
            total_questions=total_questions,
            user_id=current_user.id,
            test_id=test.id
        )
        db.session.add(test_result)
        db.session.commit()

        # Clear session
        session.pop(f'start_time_{test_id}', None)

        flash(f'You scored {score} out of {total_questions}!', 'info')
        return render_template(
            'take_test.html',
            test=test,
            processed_content=processed_content,
            score=score,
            total=total_questions,
            time_limit=time_limit,
            test_type='drag_and_drop'
        )

    else:
        # GET request: Start test, store start time in session
        session[f'start_time_{test_id}'] = datetime.now(timezone.utc).isoformat()

        return render_template(
            'take_test.html',
            test=test,
            processed_content=processed_content,
            score=None,
            total=total_questions,
            time_limit=time_limit,
            test_type='drag_and_drop'
        )

# ... [Rest of your app.py code remains unchanged]

# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
