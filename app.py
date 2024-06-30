import json
import os
from flask import Flask, render_template, redirect, url_for, request, session, flash
from functools import wraps
from flask_babel import Babel, gettext as _
from usosapi.usosapi import USOSAPISession, USOSAPIAuthorizationError
from model import db, User, Challenge

app = Flask(__name__)
app.secret_key = os.environ.get('EE-CTF_SECRET_KEY', os.urandom(24))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
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
    challenges = Challenge.query.filter_by(edition_number=1).order_by(Challenge.number).all()
    return render_template('index.html', challenges=challenges)


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


@app.route('/challenge/<edition_number>/<challenge_number>')
@login_required
def challenge(edition_number, challenge_number):
    lang = get_locale()
    challenge = Challenge.query.filter_by(edition_number=edition_number, number=challenge_number).first_or_404()

    ch_id = challenge.id
    ch_name = challenge.name if lang == 'en' else challenge.name_pl
    ch_desc = challenge.description if lang == 'en' else challenge.description_pl

    top_solvers = [
        {"rank": 1, "nick": "User1", "time": "2m 30s"},
        {"rank": 2, "nick": "User2", "time": "3m 15s"},
        {"rank": 3, "nick": "User3", "time": "4m 20s"},
        {"rank": 4, "nick": "User4", "time": "5m 05s"},
        {"rank": 5, "nick": "User5", "time": "6m 10s"},
    ]

    return render_template(
        'challenge.html',
        ch_id=ch_id,
        ch_name=ch_name,
        ch_desc=ch_desc,
        user_rating=0,
        user_comment='ttesttt',
        top_solvers=top_solvers
    )


@app.route('/submit_flag/<challenge_id>', methods=['POST'])
@login_required
def submit_flag(challenge_id):
    correct_challenge = Challenge.query.filter_by(id=challenge_id).first_or_404()
    if request.method == 'POST':
        user_flag = request.form.get('flag')
        if user_flag == correct_challenge.flag:
            flash(_("Correct flag! Well done!"), "success")
        else:
            flash(_("Incorrect flag. Try again!"), "danger")
    return redirect(request.referrer)


if __name__ == '__main__':
    app.run(debug=True)
