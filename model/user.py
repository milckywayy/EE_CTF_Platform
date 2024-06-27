from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.String, primary_key=True)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    email = db.Column(db.String(120))
    photo_url = db.Column(db.String(200))

    def __repr__(self):
        return f'<User {self.first_name} {self.last_name}>'
