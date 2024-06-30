import json
import os
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_babel import Babel, gettext as _
from usosapi.usosapi import USOSAPISession, USOSAPIAuthorizationError

from model import db, User, Challenge, Solve

# Flask app initialization
app = Flask(__name__)
app.secret_key = os.environ.get('EE-CTF_SECRET_KEY', os.urandom(24))

# Configurations
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['BABEL_DEFAULT_LOCALE'] = 'pl'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'pl']

# Initialize Babel and database
babel = Babel(app)
db.init_app(app)

# Create database tables
with app.app_context():
    db.create_all()

# Load USOS API credentials
with open('credentials/usos_api_credentials.json', 'r') as file:
    usosapi_credentials = json.load(file)

# Initialize USOS API session
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

        except USOSAPIAuthorizationError:
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
    ch_start = challenge.start_date
    ch_name = challenge.name_pl if lang == 'pl' else challenge.name
    ch_desc = challenge.description_pl if lang == 'pl' else challenge.description

    top_solutions = (db.session.query(
        User.first_name,
        User.last_name,
        Solve.solve_time
    )
        .join(Solve, User.id == Solve.user_id)
        .order_by(Solve.solve_time.asc())
        .limit(10)
        .all())

    def format_time_difference(start_time, end_time):
        delta = end_time - start_time
        days = delta.days
        seconds = delta.seconds
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m {seconds}s"

    top_solvers = [
        {'nick': f"{user_name} {user_last_name[0]}.", 'time': format_time_difference(ch_start, solve_time)}
        for user_name, user_last_name, solve_time in top_solutions
    ]

    return render_template(
        'challenge.html',
        ch_id=ch_id,
        ch_name=ch_name,
        ch_desc=ch_desc,
        user_rating=0,
        user_comment='',
        top_solvers=top_solvers
    )


@app.route('/submit_flag/<challenge_id>', methods=['POST'])
@login_required
def submit_flag(challenge_id):
    correct_challenge = Challenge.query.filter_by(id=challenge_id).first_or_404()
    if request.method == 'POST':
        user_flag = request.form.get('flag')
        if user_flag == correct_challenge.flag:
            is_already_solved = Solve.query.filter_by(user_id=session['user']['id'], challenge_id=challenge_id).first()
            if is_already_solved is None:
                solve = Solve(
                    user_id=session['user']['id'],
                    challenge_id=challenge_id,
                    solve_time=datetime.now()
                )
                db.session.add(solve)
                db.session.commit()

            flash(_("Correct flag! Well done!"), "success")
        else:
            flash(_("Incorrect flag. Try again!"), "danger")
    return redirect(request.referrer)


# Run the app
if __name__ == '__main__':
    app.run(debug=True)
