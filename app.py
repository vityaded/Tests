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
from forms import SignupForm, LoginForm, AddTestForm, EditTestForm

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
@app.route('/review/first')
@login_required
def first_review():
    # Get the user's vocabulary
    vocab_words = Vocabulary.query.filter_by(user_id=current_user.id).all()

    if not vocab_words:
        return jsonify({'error': 'No vocabulary words found'}), 404

    # Randomly select one word
    selected_word = random.choice(vocab_words)

    # Get the correct translation
    correct_translation = selected_word.translation

    # Fetch 3 incorrect translations from other words
    other_words = [word.translation for word in vocab_words if word.id != selected_word.id]
    if len(other_words) < 3:
        return jsonify({'error': 'Not enough vocabulary words to generate options'}), 400
    incorrect_options = random.sample(other_words, 3)

    # Combine correct and incorrect options and shuffle them
    options = incorrect_options + [correct_translation]
    random.shuffle(options)

    return render_template('first_review.html', word=selected_word.word, options=options, correct_translation=correct_translation)

@app.route('/review/second')
@login_required
def second_review():
    # Get the user's vocabulary
    vocab_words = Vocabulary.query.filter_by(user_id=current_user.id).all()

    if not vocab_words:
        return jsonify({'error': 'No vocabulary words found'}), 404

    # Randomly select one word
    selected_word = random.choice(vocab_words)

    # Get the correct English word
    correct_word = selected_word.word

    # Fetch 3 incorrect English words from other words
    other_words = [word.word for word in vocab_words if word.id != selected_word.id]
    if len(other_words) < 3:
        return jsonify({'error': 'Not enough vocabulary words to generate options'}), 400
    incorrect_options = random.sample(other_words, 3)

    # Combine correct and incorrect options and shuffle them
    options = incorrect_options + [correct_word]
    random.shuffle(options)

    return render_template('second_review.html', word=selected_word.translation, options=options, correct_word=correct_word)


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
    
    # Add the vocabulary relationship
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
    review_stage = db.Column(db.Integer, nullable=False, default=1)



from datetime import datetime, timedelta

from flask import request, render_template, redirect, url_for, flash, session
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import random
import unicodedata

def normalize_text(text):
    # Normalize the text to decompose combined letters (e.g., é to e + ́)
    text = unicodedata.normalize('NFKD', text)
    # Filter out non-letter characters
    text = ''.join([c for c in text if c.isalpha()])
    # Convert to lowercase
    return text.lower()

@app.route('/review', methods=['GET', 'POST'])
@login_required
def review():
    # Fetch all words due for review
    now = datetime.utcnow()
    vocab_due = Vocabulary.query.filter_by(user_id=current_user.id)\
        .filter(Vocabulary.next_review <= now)\
        .order_by(Vocabulary.next_review).all()
    
    # Fetch all vocabulary words (needed for generating incorrect options)
    vocab_words = Vocabulary.query.filter_by(user_id=current_user.id).all()
    
    # Determine if we are in practice mode
    practice_mode = False
    if not vocab_due:
        # No words due for review, switch to practice mode
        if not vocab_words:
            flash('Your vocabulary is empty. Please add some words first.', 'info')
            return redirect(url_for('my_vocabulary'))
        practice_mode = True
        vocab_list = vocab_words  # Use all words for practice
    else:
        vocab_list = vocab_due  # Use words due for review
    
    # Use session to keep track of current word index
    word_index = session.get('word_index', 0)
    total_words = len(vocab_list)
    current_word_number = word_index + 1  # Since index starts at 0

    if word_index >= total_words:
        # Reset session and redirect when done
        session.pop('word_index', None)
        if practice_mode:
            flash('Practice session completed!', 'success')
        else:
            flash('Review session completed!', 'success')
        return redirect(url_for('my_vocabulary'))

    vocab_word = vocab_list[word_index]

    if request.method == 'POST':
        # Retrieve review_stage from form data
        review_stage = int(request.form.get('review_stage'))
        user_answer = request.form.get('answer', '')
        user_answer = normalize_text(user_answer)
        success = False

        # Determine the correct answer and process based on review stage
        if review_stage == 1:
            correct_answer = normalize_text(vocab_word.translation)
            if user_answer == correct_answer:
                success = True

        elif review_stage == 2:
            correct_answer = normalize_text(vocab_word.word)
            if user_answer == correct_answer:
                success = True

        elif review_stage == 3:
            correct_answer = normalize_text(vocab_word.word)
            if user_answer == correct_answer:
                success = True

        else:
            correct_answer = normalize_text(vocab_word.word)
            if user_answer == correct_answer:
                success = True

        if not practice_mode:
            # Update review_stage and next_review based on whether the answer was correct
            if success:
                flash('Correct!', 'success')
                # Increase review_stage or reset if maximum stage reached
                if vocab_word.review_stage < 4:
                    vocab_word.review_stage += 1
                else:
                    vocab_word.review_stage = 1  # Reset to stage 1 after completion
                # Set next review date based on stage (use spaced repetition intervals)
                intervals = {1: 1, 2: 2, 3: 4, 4: 7}  # Days until next review
                next_interval = intervals.get(vocab_word.review_stage, 1)
                vocab_word.next_review = datetime.utcnow() + timedelta(days=next_interval)
                db.session.commit()
            else:
                flash(f'Incorrect! The correct answer was: {vocab_word.translation if review_stage == 1 else vocab_word.word}', 'danger')
                # Reset to stage 1 on failure
                vocab_word.review_stage = 1
                vocab_word.next_review = datetime.utcnow() + timedelta(days=1)
                db.session.commit()
        else:
            # In practice mode, just provide feedback without updating the database
            if success:
                flash('Correct!', 'success')
            else:
                flash(f'Incorrect! The correct answer was: {vocab_word.translation if review_stage == 1 else vocab_word.word}', 'danger')

        # Move to next word
        session['word_index'] = word_index + 1
        return redirect(url_for('review'))

    else:
        # In practice mode, randomly select a review stage
        if practice_mode:
            review_stage = random.randint(1, 4)
        else:
            review_stage = vocab_word.review_stage

        # Prepare the question and select the template based on review stage
        if review_stage == 1:
            # First review: Multiple-choice translation
            template = 'first_review.html'
            question = vocab_word.word

            # Generate options from all vocabulary words
            other_translations = [word.translation for word in vocab_words if word.id != vocab_word.id]
            if len(other_translations) >= 3:
                incorrect_options = random.sample(other_translations, 3)
            elif len(other_translations) > 0:
                # Not enough options, repeat existing ones
                times = 3 // len(other_translations)
                remainder = 3 % len(other_translations)
                incorrect_options = other_translations * times + other_translations[:remainder]
                incorrect_options = incorrect_options[:3]  # Ensure we have exactly 3 options
            else:
                # Not enough words to generate incorrect options
                flash('Not enough vocabulary words to generate options. Please add more words.', 'warning')
                # Move to next word
                session['word_index'] = word_index + 1
                return redirect(url_for('review'))

            options = incorrect_options + [vocab_word.translation]
            random.shuffle(options)

            return render_template(
                template,
                vocab_word=vocab_word,
                question=question,
                options=options,
                total_words=total_words,
                current_word_number=current_word_number,
                practice_mode=practice_mode,
                review_stage=review_stage  # Pass review_stage to the template
            )

        elif review_stage == 2:
            # Second review: Multiple-choice word selection
            template = 'second_review.html'
            question = vocab_word.translation

            # Generate options from all vocabulary words
            other_words = [word.word for word in vocab_words if word.id != vocab_word.id]
            if len(other_words) >= 3:
                incorrect_options = random.sample(other_words, 3)
            elif len(other_words) > 0:
                times = 3 // len(other_words)
                remainder = 3 % len(other_words)
                incorrect_options = other_words * times + other_words[:remainder]
                incorrect_options = incorrect_options[:3]  # Ensure we have exactly 3 options
            else:
                # Not enough words to generate incorrect options
                flash('Not enough vocabulary words to generate options. Please add more words.', 'warning')
                # Move to next word
                session['word_index'] = word_index + 1
                return redirect(url_for('review'))

            options = incorrect_options + [vocab_word.word]
            random.shuffle(options)

            return render_template(
                template,
                vocab_word=vocab_word,
                question=question,
                options=options,
                total_words=total_words,
                current_word_number=current_word_number,
                practice_mode=practice_mode,
                review_stage=review_stage  # Pass review_stage to the template
            )

        elif review_stage == 3:
            # Third review: Scrambled word exercise
            template = 'third_review.html'
            question = vocab_word.translation
            correct_word = vocab_word.word
            scrambled_word = ''.join(random.sample(correct_word, len(correct_word)))
            # Ensure the scrambled word is not the same as the correct word
            while scrambled_word == correct_word:
                scrambled_word = ''.join(random.sample(correct_word, len(correct_word)))


            return render_template(
                template,
                vocab_word=vocab_word,
                question=question,
                scrambled_word=scrambled_word,
                total_words=total_words,
                current_word_number=current_word_number,
                practice_mode=practice_mode,
                review_stage=review_stage  # Include this line
            )

        else:
            # Fourth review: Typing the word exercise
            template = 'fourth_review.html'
            question = vocab_word.translation

            return render_template(
                template,
                vocab_word=vocab_word,
                question=question,
                total_words=total_words,
                current_word_number=current_word_number,
                practice_mode=practice_mode,
                review_stage=review_stage  # Include this line
            )

class LearnTestResult(db.Model):
    __tablename__ = 'learn_test_result'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='learn_test_results')
    test = db.relationship('Test', backref='learn_test_results')


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

@app.route('/tts')
def tts():
    text = request.args.get('text')
    language = request.args.get('lang', 'en')

    # Make the request to Google TTS API
    tts_url = f'https://translate.google.com/translate_tts?ie=UTF-8&tl={language}&client=gtx&q={text}'
    headers = {'User-Agent': 'Mozilla/5.0'}  # Required to mimic browser request
    response = requests.get(tts_url, headers=headers)

    # Return the audio response
    return Response(response.content, mimetype='audio/mpeg')

@app.route('/translate')
def translate_word():
    word = request.args.get('word')
    source_lang = 'en'
    target_lang = 'uk'

    if not word:
        return jsonify({'error': 'No word provided for translation'}), 400

    # Construct the translation URL for Google Translate
    translate_url = (
        f'https://translate.googleapis.com/translate_a/single?client=gtx&sl={source_lang}&tl={target_lang}&dt=t&q={word}'
    )

    try:
        # Make the request to the Google Translate API
        response = requests.get(translate_url)
        response.raise_for_status()

        translation_data = response.json()

        if translation_data and isinstance(translation_data, list) and len(translation_data) > 0:
            translation = translation_data[0][0][0]
            pronunciation_url = f'https://translate.google.com/translate_tts?ie=UTF-8&tl={source_lang}&client=gtx&q={word}'

            return jsonify({
                'translation': translation,
                'pronunciation_url': pronunciation_url
            })
        else:
            return jsonify({'error': 'Unexpected translation response format'}), 500

    except requests.RequestException as e:
        return jsonify({'error': f'Translation API request failed: {str(e)}'}), 500


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


@app.route('/autocomplete/book', methods=['GET'])
def autocomplete_book():
    query = request.args.get('q', '')
    matching_books = Book.query.filter(Book.title.ilike(f'%{query}%')).all()  # Search for books with similar names
    book_titles = [book.title for book in matching_books]
    return jsonify(book_titles)

@app.route('/autocomplete/test', methods=['GET'])
def autocomplete_test():
    query = request.args.get('q', '')
    matching_tests = Test.query.filter(Test.name.ilike(f'%{query}%')).all()  # Search for tests with similar names
    test_names = [test.name for test in matching_tests]
    return jsonify(test_names)

# Decorator to require admin access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# Helper Function: Check Allowed File Extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Route: Home Page
@app.route('/')
def index():
    books = Book.query.all()  # Fetch all books
    return render_template('index.html', books=books)

@app.route('/book/<int:book_id>')
def book_tests(book_id):
    book = Book.query.get_or_404(book_id)
    tests = Test.query.filter_by(book_id=book.id).all()  # Fetch all tests for the specific book
    return render_template('book_tests.html', book=book, tests=tests)

@app.route('/review/third')
@login_required
def third_review():
    # Get the user's vocabulary
    vocab_words = Vocabulary.query.filter_by(user_id=current_user.id).all()

    if not vocab_words:
        return jsonify({'error': 'No vocabulary words found'}), 404

    # Randomly select one word
    selected_word = random.choice(vocab_words)

    # Get the correct English word and scramble it
    correct_word = selected_word.word
    scrambled_word = ''.join(random.sample(correct_word, len(correct_word)))

    return render_template('third_review.html', word=selected_word.translation, scrambled_word=scrambled_word, correct_word=correct_word)

@app.route('/review/fourth', methods=['POST'])
@login_required
def process_fourth_review():
    word_id = request.form.get('word_id')
    user_answer = request.form.get('translation').strip().lower()

    vocab_word = Vocabulary.query.filter_by(id=word_id, user_id=current_user.id).first()
    if not vocab_word:
        return jsonify({'error': 'Word not found'}), 404

    correct_answer = vocab_word.word.lower()
    if user_answer == correct_answer:
        # Correct answer: Increase the interval
        vocab_word.review_interval = min(vocab_word.review_interval * 2, 30)  # Double the interval, max 30 days
        vocab_word.next_review = datetime.utcnow() + timedelta(days=vocab_word.review_interval)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Correct! Your next review is in {} days.'.format(vocab_word.review_interval)})
    else:
        # Incorrect answer: Reset interval to 1 day
        vocab_word.review_interval = 1
        vocab_word.next_review = datetime.utcnow() + timedelta(days=vocab_word.review_interval)
        db.session.commit()
        return jsonify({'success': False, 'message': 'Incorrect. You will review this word again tomorrow.'})


@app.route('/review/due')
@login_required
def due_reviews():
    # Get all vocabulary words that are due for review today
    today = datetime.utcnow().date()
    due_words = Vocabulary.query.filter_by(user_id=current_user.id).filter(Vocabulary.next_review <= today).all()

    return render_template('due_reviews.html', due_words=due_words)

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
        test_name = form.test_name.data.strip()
        test_content = form.test_content.data.strip()
        time_limit = form.time_limit.data

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
    if not current_user.is_admin and test.created_by != current_user.id:
        abort(403)

    form = EditTestForm(obj=test)
    if form.validate_on_submit():
        test_name = form.test_name.data.strip()
        test_content = form.test_content.data.strip()
        time_limit = form.time_limit.data

        # Update test details
        test.name = test_name
        test.content = test_content
        test.time_limit = time_limit
        db.session.commit()
        # Continue from where the previous file ends

        flash('Test updated successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('edit_test.html', form=form, test=test)

# Route: Delete Test
@app.route('/delete_test/<int:test_id>', methods=['POST'])
@login_required
def delete_test(test_id):
    test = Test.query.get_or_404(test_id)
    if not current_user.is_admin and test.created_by != current_user.id:
        abort(403)

    db.session.delete(test)
    db.session.commit()
    flash('Test deleted successfully!', 'success')
    return redirect(url_for('index'))

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

    # Function to replace answers with input fields or dropdowns
    def replace_answers(line):
        nonlocal question_counter
        dropdown_pattern = r'#\s*\[([^\]]+)\]\s*([^\#]+)\s*#'
        input_pattern = r'\[([^\]]+)\]'

        def dropdown_repl(match):
            nonlocal question_counter
            options_str = match.group(1)
            correct_answer = match.group(2).strip()
            options = [opt.strip() for opt in options_str.split(',')]
            qid = f'q{question_counter}'
            correct_answers[qid] = correct_answer
            question_counter += 1

            if request.method == 'POST':
                user_answer = request.form.get(qid, '').strip().lower()
                select_class = 'custom-select correct' if user_answer == correct_answer.lower() else 'custom-select incorrect'
                disabled = 'disabled'
            else:
                select_class = 'custom-select'
                disabled = ''

            select_html = f'<select name="{qid}" class="{select_class}" {disabled} style="display: inline-block; width: auto;">'
            for option in options:
                selected = 'selected' if request.method == 'POST' and user_answer == option.strip().lower() else ''
                select_html += f'<option value="{option}" {selected}>{option}</option>'
            select_html += '</select>'

            if request.method == 'POST' and user_answer != correct_answer.lower():
                select_html += f' <span class="correct-answer">(Correct answer: {correct_answer})</span>'

            return select_html

        def input_repl(match):
            nonlocal question_counter
            correct_answer = match.group(1).strip()
            qid = f'q{question_counter}'
            correct_answers[qid] = correct_answer
            question_counter += 1

            if request.method == 'POST':
                user_answer = request.form.get(qid, '')
                input_class = 'form-control correct' if user_answer.strip().lower() == correct_answer.lower() else 'form-control incorrect'
                readonly = 'readonly'
            else:
                input_class = 'form-control'
                readonly = ''

            input_html = f'<input type="text" name="{qid}" value="{user_answer if request.method == "POST" else ""}" class="{input_class}" style="width: auto;" {readonly}>'

            if request.method == 'POST' and user_answer.strip().lower() != correct_answer.lower():
                input_html += f' <span class="correct-answer">(Correct answer: {correct_answer})</span>'

            return input_html

        # Process the line
        line = re.sub(dropdown_pattern, dropdown_repl, line)
        line = re.sub(input_pattern, input_repl, line)
        return line

    # Process each line in test content
    for line in test_content.splitlines():
        processed_line = replace_answers(line)
        processed_content.append(processed_line)

    score = 0
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

        # Calculate score
        for qid, correct_answer in correct_answers.items():
            user_answer = request.form.get(qid, '')
            if user_answer.strip().lower() == correct_answer.lower():
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
            time_limit=time_limit
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
            time_limit=time_limit
        )


@app.route('/search')
def search():
    query = request.args.get('query', '').strip()
    search_option = request.args.get('search_option', 'books')

    if not query:
        flash('Please enter a search term.', 'warning')
        return redirect(url_for('index'))

    if search_option == 'books':
        # Search for books by title
        books = Book.query.filter(Book.title.ilike(f'%{query}%')).all()
        return render_template('search_results.html', books=books, query=query, search_option=search_option)
    else:
        # Search for tests by name
        tests = Test.query.filter(Test.name.ilike(f'%{query}%')).all()
        return render_template('search_results.html', tests=tests, query=query, search_option=search_option)


@app.route('/learn/<int:test_id>', methods=['GET', 'POST'])
@login_required
def learn_test(test_id):
    test = Test.query.get_or_404(test_id)
    test_content = test.content

    # Initialize variables
    processed_content = []
    correct_answers = {}
    question_counter = 1
    user_correct = {}

    # Function to replace answers with input fields or dropdowns
    def replace_answers(line):
        nonlocal question_counter
        dropdown_pattern = r'#\s*\[([^\]]+)\]\s*([^\#]+)\s*#'
        input_pattern = r'\[([^\]]+)\]'

        def dropdown_repl(match):
            nonlocal question_counter
            options_str = match.group(1)
            correct_answer = match.group(2).strip()
            options = [opt.strip() for opt in options_str.split(',')]
            qid = f'q{question_counter}'
            correct_answers[qid] = correct_answer
            question_counter += 1

            select_class = 'custom-select'
            user_answer = request.form.get(qid, '').strip().lower() if request.method == 'POST' else ''
            
            # Check if user's answer is correct
            if user_answer == correct_answer.lower():
                user_correct[qid] = True
                select_class += ' correct'
            else:
                user_correct[qid] = False

            select_html = f'<select name="{qid}" class="{select_class}">'
            for option in options:
                selected = 'selected' if request.method == 'POST' and user_answer == option.strip().lower() else ''
                select_html += f'<option value="{option}" {selected}>{option}</option>'
            select_html += '</select>'

            return select_html

        def input_repl(match):
            nonlocal question_counter
            correct_answer = match.group(1).strip()
            qid = f'q{question_counter}'
            correct_answers[qid] = correct_answer
            question_counter += 1

            user_answer = request.form.get(qid, '').strip().lower() if request.method == 'POST' else ''
            input_class = 'form-control'

            # Check if user's answer is correct
            if user_answer == correct_answer.lower():
                user_correct[qid] = True
                input_class += ' correct'
            else:
                user_correct[qid] = False

            input_html = f'<input type="text" name="{qid}" value="{user_answer}" class="{input_class}">'

            return input_html

        # Process the line
        line = re.sub(dropdown_pattern, dropdown_repl, line)
        line = re.sub(input_pattern, input_repl, line)
        return line

    # Process each line in test content
    for line in test_content.splitlines():
        processed_line = replace_answers(line)
        processed_content.append(processed_line)

    if request.method == 'POST':
        # Check if all answers are correct
        all_correct = all(user_correct.values())
        if all_correct:
            flash('You have answered everything correctly! You can now proceed.', 'success')
        else:
            flash('Some answers are incorrect or missing. Please try again.', 'danger')

    return render_template(
        'learn_test.html',
        test_name=test.name,
        processed_content=processed_content
    )


@app.route('/my_vocabulary')
@login_required
def my_vocabulary():
    vocab_words = Vocabulary.query.filter_by(user_id=current_user.id).all()
    return render_template('vocabulary.html', vocab_words=vocab_words)


@app.route('/add_to_vocabulary', methods=['POST'])
@login_required
def add_to_vocabulary():
    data = request.get_json()
    word = data.get('word')
    translation = data.get('translation')

    # Ensure that word and translation are not None or empty
    if not word or not translation:
        return jsonify({'success': False, 'error': 'Invalid data: word or translation is missing'}), 400

    try:
        # Add word to user's vocabulary
        new_vocab = Vocabulary(word=word, translation=translation, user_id=current_user.id)
        db.session.add(new_vocab)
        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/autocomplete_search')
def autocomplete_search():
    query = request.args.get('query', '').strip()
    search_option = request.args.get('search_option', 'books')

    results = []

    if query:
        if search_option == 'books':
            # Search for matching books by title
            books = Book.query.filter(Book.title.ilike(f'%{query}%')).all()
            results = [{'label': book.title, 'value': book.title} for book in books]
        elif search_option == 'tests':
            # Search for matching tests by name
            tests = Test.query.filter(Test.name.ilike(f'%{query}%')).all()
            results = [{'label': test.name, 'value': test.name} for test in tests]

    return jsonify(results)


# Route: Admin Panel
@app.route('/admin')
@app.route('/admin')
@admin_required
def admin_panel():
    test_results = TestResult.query.order_by(TestResult.timestamp.desc()).all()
    learn_test_results = LearnTestResult.query.order_by(LearnTestResult.completed_at.desc()).all()
    return render_template(
        'admin_panel.html', 
        test_results=test_results,
        learn_test_results=learn_test_results
    )

# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)

