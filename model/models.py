from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.String, primary_key=True)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    email = db.Column(db.String(120))
    photo_url = db.Column(db.String(200))

    def __repr__(self):
        return f'<User {self.first_name} {self.last_name}>'


class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False)
    edition_number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    name_pl = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    description_pl = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    difficulty = db.Column(Enum('Easy', 'Medium', 'Hard', name='difficulty_levels'), nullable=False)
    icon = db.Column(db.String(50), nullable=False)

    def is_available(self):
        return datetime.now() >= self.start_date
