from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, abort, session
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, login_required, logout_user,
    current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import re
from functools import wraps
from sqlalchemy import MetaData

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure secret key

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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///books.db'  # Using SQLite database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Create the SQLAlchemy db instance with the metadata
db = SQLAlchemy(app, metadata=metadata)

# Initialize Flask-Migrate
from flask_migrate import Migrate
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Define the User model
class User(UserMixin, db.Model):
    __tablename__ = 'user'  # Explicitly specify table name
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    test_results = db.relationship('TestResult', backref='user', lazy=True)
    tests_created = db.relationship('Test', backref='creator', lazy=True)

# User loader callback
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

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

# Uncomment the following lines if not using migrations
# with app.app_context():
#     db.create_all()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.route('/')
def index():
    tests = Test.query.all()
    return render_template('index.html', tests=tests)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('signup'))

        # Hash the password
        hashed_password = generate_password_hash(password, method='sha256')

        # Create new user and add to the database
        new_user = User(username=username, password=hashed_password)
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

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Find user by username
        user = User.query.filter_by(username=username).first()

        # Check if user exists and password is correct
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_test():
    if request.method == 'POST':
        book_title = request.form['book_title']
        test_name = request.form['test_name']
        test_content = request.form['test_content']
        time_limit = request.form.get('time_limit')

        # Convert time_limit to integer if provided
        if time_limit:
            try:
                time_limit = int(time_limit)
                if time_limit <= 0:
                    flash('Time limit must be a positive integer.', 'danger')
                    return redirect(url_for('add_test'))
            except ValueError:
                flash('Invalid time limit. Please enter a valid number.', 'danger')
                return redirect(url_for('add_test'))
        else:
            time_limit = None

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
            creator=current_user
        )
        db.session.add(new_test)
        db.session.commit()

        flash('Test added successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('add.html')

@app.route('/edit_test/<int:test_id>', methods=['GET', 'POST'])
@login_required
def edit_test(test_id):
    test = Test.query.get_or_404(test_id)
    if not current_user.is_admin and test.created_by != current_user.id:
        abort(403)

    if request.method == 'POST':
        test_name = request.form['test_name']
        test_content = request.form['test_content']
        time_limit = request.form.get('time_limit')

        # Validate and update time_limit
        if time_limit:
            try:
                time_limit = int(time_limit)
                if time_limit <= 0:
                    flash('Time limit must be a positive integer.', 'danger')
                    return redirect(url_for('edit_test', test_id=test_id))
            except ValueError:
                flash('Invalid time limit. Please enter a valid number.', 'danger')
                return redirect(url_for('edit_test', test_id=test_id))
        else:
            time_limit = None

        # Update test details
        test.name = test_name
        test.content = test_content
        test.time_limit = time_limit
        db.session.commit()

        flash('Test updated successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('edit_test.html', test=test)

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

@app.route('/test/<int:test_id>', methods=['GET', 'POST'])
@login_required
def take_test(test_id):
    test = Test.query.get_or_404(test_id)
    test_content = test.content
    time_limit = test.time_limit  # Time limit in minutes

    # Initialize variables
    processed_content = []
    correct_answers = {}
    question_counter = 1  # Initialize here

    # Function to replace answers with input fields or dropdowns
    def replace_answers(line):
        nonlocal question_counter
        # Patterns for dropdowns and input fields
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

            # Determine class based on correctness
            if request.method == 'POST':
                user_answer = request.form.get(qid, '')
                select_class = 'custom-select correct' if user_answer.strip().lower() == correct_answer.strip().lower() else 'custom-select incorrect'
                disabled = 'disabled'
            else:
                select_class = 'custom-select'
                disabled = ''

            # Build the select element without 'required'
            select_html = f'<select name="{qid}" class="{select_class}" {disabled} style="display: inline-block; width: auto;">'
            for option in options:
                if request.method == 'POST':
                    selected = 'selected' if user_answer == option else ''
                else:
                    selected = ''
                select_html += f'<option value="{option}" {selected}>{option}</option>'
            select_html += '</select>'

            # Show correct answer if incorrect or unanswered
            if request.method == 'POST' and user_answer.strip().lower() != correct_answer.strip().lower():
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
                input_class = 'form-control correct' if user_answer.strip().lower() == correct_answer.strip().lower() else 'form-control incorrect'
                readonly = 'readonly'
            else:
                input_class = 'form-control d-inline-block'
                readonly = ''

            # Build the input field without 'required'
            input_field = f'<input type="text" name="{qid}" value="{user_answer if request.method == "POST" else ""}" class="{input_class}" style="width: auto;" {readonly}>'

            # Show correct answer if incorrect or unanswered
            if request.method == 'POST' and user_answer.strip().lower() != correct_answer.strip().lower():
                input_field += f' <span class="correct-answer">(Correct answer: {correct_answer})</span>'

            return input_field

        # Process the line
        line = re.sub(dropdown_pattern, dropdown_repl, line)
        line = re.sub(input_pattern, input_repl, line)
        return line

    # Process each line
    for line in test_content.splitlines():
        # Replace answers with input fields or dropdowns
        processed_line = replace_answers(line)
        # Append to processed_content
        processed_content.append(processed_line)

    if request.method == 'POST':
        # Server-side time limit enforcement
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
                # Optionally, adjust the score or handle as needed

        # Calculate score
        score = 0
        total_questions = question_counter - 1
        for qid in correct_answers.keys():
            user_answer = request.form.get(qid, '')
            correct_answer = correct_answers[qid]
            if user_answer.strip() != '':
                if user_answer.strip().lower() == correct_answer.strip().lower():
                    score += 1
            else:
                # User left the answer blank
                pass  # Treat as incorrect or handle as needed

        # Save test result
        test_result = TestResult(
            score=score,
            total_questions=total_questions,
            user_id=current_user.id,
            test_id=test.id
        )
        db.session.add(test_result)
        db.session.commit()

        # Clear the start time from session
        session.pop(f'start_time_{test_id}', None)

        flash(f'You scored {score} out of {total_questions}!', 'info')
        return render_template(
            'take_test.html',
            test_name=test.name,
            processed_content=processed_content,
            score=score,
            total=total_questions,
            time_limit=time_limit
        )

    else:
        # GET request: User is starting the test
        # Store start time in session
        session[f'start_time_{test_id}'] = datetime.now(timezone.utc).isoformat()

        return render_template(
            'take_test.html',
            test_name=test.name,
            processed_content=processed_content,
            score=None,
            total=question_counter - 1,
            time_limit=time_limit
        )

@app.route('/admin')
@admin_required
def admin_panel():
    # Get all test results
    test_results = TestResult.query.order_by(TestResult.timestamp.desc()).all()
    return render_template('admin_panel.html', test_results=test_results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

