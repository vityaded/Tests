from app import db
from app import Vocabulary
from datetime import datetime

# Fetch all vocabulary words
vocab_words = Vocabulary.query.all()

for word in vocab_words:
    if word.next_review is None:
        # Set to default value or handle accordingly
        word.next_review = datetime.utcnow()
        db.session.add(word)  # Add the updated word to the session

db.session.commit()  # Commit all changes at once
