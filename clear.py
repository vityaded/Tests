from app import db, Vocabulary, app
from flask import current_app
from datetime import datetime

# Setup app context
with app.app_context():
    # Drop all the tables (including Vocabulary) - optional if only Vocabulary needs reset
    db.drop_all()  

    # Recreate all the tables (including Vocabulary)
    db.create_all()

    # Insert default values into the newly created table
    default_vocabulary = [
        Vocabulary(word="example1", translation="приклад1", user_id=1, next_review=datetime.utcnow(), review_stage=1),
        Vocabulary(word="example2", translation="приклад2", user_id=1, next_review=datetime.utcnow(), review_stage=1)
    ]

    # Add the default entries
    db.session.bulk_save_objects(default_vocabulary)
    
    # Commit the changes to the database
    db.session.commit()

    print("Vocabulary table recreated with default values.")


