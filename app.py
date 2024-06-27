import json
import os
from flask import Flask, render_template, redirect, url_for, request, session, flash
from functools import wraps
from flask_babel import Babel, gettext as _
from usosapi.usosapi import USOSAPISession, USOSAPIAuthorizationError
from model import db, User

app = Flask(__name__)
app.secret_key = os.environ.get('EE-CTF_SECRET_KEY', os.urandom(24))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['BABEL_DEFAULT_LOCALE'] = 'pl'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'pl']

babel = Babel(app)
db.init_app(app)
with app.app_context():
    db.create_all()

with open('credentials/usos_api_credentials.json', 'r') as file:
    usosapi_credentials = json.load(file)

usosapi = USOSAPISession(
    usosapi_credentials['api_base_address'],
    usosapi_credentials['consumer_key'],
    usosapi_credentials['consumer_secret'],
    'email'
)


@babel.localeselector
def get_locale():
    return session.get('lang', app.config['BABEL_DEFAULT_LOCALE'])


@app.context_processor
def inject_conf_var():
    return dict(get_locale=get_locale)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash(_("Please log in to access this page."), "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/change_language/<language>')
def change_language(language):
    session['lang'] = language
    return redirect(request.referrer)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')


@app.route('/login', methods=['GET'])
def login():
    oauth_token = request.args.get('oauth_token')
    oauth_verifier = request.args.get('oauth_verifier')
    if oauth_token and oauth_verifier:
        try:
            usosapi.authorize(oauth_token, oauth_verifier)
            user_data = usosapi.fetch_from_service(
                'services/users/user',
                fields='id|first_name|last_name|email|photo_urls[200x200]'
            )

            usos_id = user_data['id']
            first_name = user_data['first_name']
            last_name = user_data['last_name']
            email = user_data['email']
            photo_url = user_data['photo_urls']['200x200']

            user = User.query.filter_by(id=usos_id).first()
            if user is None:
                user = User(
                    id=usos_id,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    photo_url=photo_url
                )
                db.session.add(user)
                db.session.commit()

            session['logged_in'] = True
            session['user'] = {
                'id': usos_id,
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'photo_url': photo_url
            }

            return redirect(url_for('home'))

        except USOSAPIAuthorizationError as e:
            flash(_("Error during USOS authentication. Please try again."), "danger")

    return render_template('login.html')


@app.route('/usos_auth')
def usos_auth():
    _, request_url = usosapi.get_auth_url(callback=url_for('login', _external=True))
    return redirect(request_url)


@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash(_("You have been logged out."), "success")
    return redirect(url_for('home'))


@app.route('/challenge/<edition_id>/<challenge_id>')
@login_required
def challenge(edition_id, challenge_id):
    if edition_id == 1:
        if challenge_id == 1:
            return render_template('index.html')

    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)
