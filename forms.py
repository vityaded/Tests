# forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=150)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Sign Up')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=150)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class AddTestForm(FlaskForm):
    book_title = StringField('Book Title', validators=[DataRequired(), Length(min=1, max=150)])
    test_name = StringField('Test Name', validators=[DataRequired(), Length(min=1, max=150)])
    time_limit = IntegerField('Time Limit (minutes)', validators=[Optional(), NumberRange(min=1)])
    test_content = TextAreaField('Test Content', validators=[DataRequired()])
    submit = SubmitField('Add Test')

class EditTestForm(FlaskForm):
    test_name = StringField('Test Name', validators=[DataRequired(), Length(min=1, max=150)])
    time_limit = IntegerField('Time Limit (minutes)', validators=[Optional(), NumberRange(min=1)])
    test_content = TextAreaField('Test Content', validators=[DataRequired()])
    submit = SubmitField('Update Test')

class TestAnswerForm(FlaskForm):
    answer = TextAreaField('Your Answer', validators=[DataRequired()])
    submit = SubmitField('Submit Answer')

class TestForm(FlaskForm):
    name = StringField('Test Name', validators=[DataRequired()])  # Ensure this field is required
    name = StringField('Test Name', validators=[DataRequired()])
    time_limit = IntegerField('Time Limit (minutes)', validators=[Optional(), NumberRange(min=1)])
    content = TextAreaField('Test Content', validators=[DataRequired()])
    submit = SubmitField('Save Changes')
