import json
import os
import logging
import threading
import time
from datetime import datetime
from functools import wraps

import requests
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify, send_from_directory
from flask_babel import Babel, gettext as _
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from usosapi.usosapi import USOSAPISession, USOSAPIAuthorizationError
from model import db, User, Challenge, Solve, Rating, Comment

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('EE-CTF_SECRET_KEY', os.urandom(24))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['BABEL_DEFAULT_LOCALE'] = 'pl'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'pl']

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "200 per hour", "20 per minute"]
)

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

with open('credentials/container_manager_secret.json') as f:
    secret_data = json.load(f)
    SECRET_KEY = secret_data['secret']

CONTAINER_MANAGER_API = 'https://container-manager.francecentral.cloudapp.azure.com:443'
CONTAINER_MANAGER_DOMAIN = 'container-manager.francecentral.cloudapp.azure.com'
USOSAPI_SESSION_CHECK = 43_200  # Every 12 hours

ADMIN_IDS = ['1178835', '1187538']


@babel.localeselector
def get_locale():
    return session.get('lang', app.config['BABEL_DEFAULT_LOCALE'])


@app.context_processor
def inject_conf_var():
    return dict(get_locale=get_locale)


def is_admin():
    if 'logged_in' in session and session['user']['id'] in ADMIN_IDS:
        return True
    return False


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
    return render_template('index.html', challenges=challenges, is_admin=is_admin())


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')


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

            user = User.query.filter_by(id=user_data['id']).first()
            if user is None:
                user = User(
                    id=user_data['id'],
                    first_name=user_data['first_name'],
                    last_name=user_data['last_name'],
                    email=user_data['email'],
                    photo_url=user_data['photo_urls']['200x200']
                )
                db.session.add(user)
                db.session.commit()

            session['logged_in'] = True
            session['user'] = {
                'id': user_data['id'],
                'first_name': user_data['first_name'],
                'last_name': user_data['last_name'],
                'email': user_data['email'],
                'photo_url': user_data['photo_urls']['200x200'],
                'is_admin': True if user_data['id'] in ADMIN_IDS else False
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

    if not challenge.is_available() and not is_admin():
        flash(_("Challenge not available yet."), "danger")
        return redirect(url_for('home'))

    ch_id = challenge.id
    ch_start = challenge.start_date
    ch_name = challenge.name_pl if lang == 'pl' else challenge.name
    ch_desc = challenge.description_pl if lang == 'pl' else challenge.description

    top_solves = (db.session.query(
        User.first_name,
        User.last_name,
        Solve.solve_time
    )
        .join(Solve, Solve.user_id == User.id)
        .filter(Solve.challenge_id == ch_id)
        .order_by(Solve.solve_time.asc())
        .limit(5)
        .all())

    def format_time_difference(start_time, end_time):
        if end_time < start_time:
            start_time, end_time = end_time, start_time

        delta = end_time - start_time
        days = delta.days
        seconds = delta.seconds
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m {seconds}s"

    top_solvers = [
        {'nick': f"{user_name} {user_last_name[0]}.", 'time': format_time_difference(ch_start, solve_time)}
        for user_name, user_last_name, solve_time in top_solves
    ]

    user_rating = Rating.query.filter_by(user_id=session['user']['id'], challenge_id=ch_id).first()
    rating = user_rating.rating if user_rating else 0

    user_comment = Comment.query.filter_by(user_id=session['user']['id'], challenge_id=ch_id).first()
    comment = user_comment.comment if user_comment else None

    return render_template(
        'challenge.html',
        ch_id=ch_id,
        ch_name=ch_name,
        ch_desc=ch_desc,
        user_rating=rating,
        user_comment=comment,
        top_solvers=top_solvers
    )


@app.route('/submit_flag/<challenge_id>', methods=['POST'])
@login_required
def submit_flag(challenge_id):
    challenge = Challenge.query.filter_by(id=challenge_id).first_or_404()

    user_flag = request.form.get('flag')
    if user_flag == challenge.flag:
        is_already_solved = Solve.query.filter_by(user_id=session['user']['id'], challenge_id=challenge_id).first()
        if is_already_solved is None:
            solve = Solve(
                user_id=session['user']['id'],
                challenge_id=challenge_id,
                solve_time=datetime.now()
            )
            db.session.add(solve)
            db.session.commit()
            logging.info(f"User {session['user']['id']} solved challenge {challenge_id}")

        flash(_("Correct flag! Well done!"), "success")
    else:
        flash(_("Incorrect flag. Try again!"), "danger")
    return redirect(request.referrer)


@app.route('/submit_rating/<challenge_id>', methods=['POST'])
@login_required
def submit_rating(challenge_id):
    Challenge.query.filter_by(id=challenge_id).first_or_404()

    data = request.get_json()
    rating_value = data.get('rating')

    if not rating_value:
        return jsonify({'error': 'Missing data'}), 400

    user_id = session['user']['id']
    rating = Rating.query.filter_by(user_id=user_id, challenge_id=challenge_id).first()

    if rating:
        rating.rating = rating_value
    else:
        new_rating = Rating(user_id=user_id, challenge_id=challenge_id, rating=rating_value)
        db.session.add(new_rating)

    db.session.commit()
    logging.info(f"User {user_id} submitted rating for challenge {challenge_id}")

    return jsonify({'success': 'Rating saved'}), 200


@app.route('/submit_comment/<challenge_id>', methods=['POST'])
@login_required
def submit_comment(challenge_id):
    Challenge.query.filter_by(id=challenge_id).first_or_404()

    new_comment = request.form.get('comment')
    user_id = session['user']['id']

    saved_comment = Comment.query.filter_by(user_id=user_id, challenge_id=challenge_id).first()
    if saved_comment is None:
        comment = Comment(
            user_id=user_id,
            challenge_id=challenge_id,
            comment=new_comment
        )
        db.session.add(comment)
    else:
        saved_comment.comment = new_comment

    db.session.commit()
    logging.info(f"User {user_id} submitted comment for challenge {challenge_id}")

    return redirect(request.referrer)


@app.route('/container_manager/manager/<image>')
@login_required
def container_manager(image):
    return render_template('container_manager.html', image=image, manager_domain=CONTAINER_MANAGER_DOMAIN)


def get_headers():
    return {
        'X-Secret-Key': SECRET_KEY,
        'Content-Type': 'application/json'
    }


@app.route('/container_manager/container_status')
@login_required
def container_status():
    session_id = session['user']['id']
    response = requests.post(
        f'{CONTAINER_MANAGER_API}/container_status',
        json={'session_id': session_id},
        headers=get_headers()
    )
    return jsonify(response.json())


@app.route('/container_manager/make_container/<image>')
@login_required
def make_container(image):
    session_id = session['user']['id']
    response = requests.post(
        f'{CONTAINER_MANAGER_API}/make_container/{image}',
        json={'session_id': session_id},
        headers=get_headers()
    )
    return jsonify(response.json())


@app.route('/container_manager/remove_container')
@login_required
def remove_container():
    session_id = session['user']['id']
    response = requests.delete(
        f'{CONTAINER_MANAGER_API}/remove_container',
        json={'session_id': session_id},
        headers=get_headers()
    )
    return jsonify(response.json())


@app.route('/container_manager/extend_container')
@login_required
def extend_container():
    session_id = session['user']['id']
    response = requests.post(
        f'{CONTAINER_MANAGER_API}/extend_container',
        json={'session_id': session_id},
        headers=get_headers()
    )
    return jsonify(response.json())


@app.route('/container_manager/restart_container')
@login_required
def restart_container():
    session_id = session['user']['id']
    response = requests.post(
        f'{CONTAINER_MANAGER_API}/restart_container',
        json={'session_id': session_id},
        headers=get_headers()
    )
    return jsonify(response.json())


@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory('static/ctf_files', filename)


def cleanup_usos_sessions():
    while True:
        logging.info(f"Cleaning up usos sessions")

        usosapi.cleanup_auth_sessions()

        time.sleep(USOSAPI_SESSION_CHECK)


threading.Thread(target=cleanup_usos_sessions, daemon=True).start()
