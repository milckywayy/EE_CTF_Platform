import json
import os
import logging
import threading
import time
from datetime import datetime
from functools import wraps
import hashlib

import requests
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify, send_from_directory
from flask_babel import Babel, gettext as _

from usosapi.usosapi import USOSAPISession, USOSAPIAuthorizationError
from model import db, User, Challenge, Solve, Rating, Comment

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('EE_CTF_SECRET_KEY', os.urandom(24))

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

with open('credentials/container_manager_secret.json') as f:
    secret_data = json.load(f)
    SECRET_KEY = secret_data['secret']

CONTAINER_MANAGER_API = 'http://127.0.0.1:5000'
CONTAINER_MANAGER_DOMAIN = 'localhost'
USOSAPI_SESSION_CHECK = 43_200  # Every 12 hours

CURRENT_EDITION_NUM = 2
FLAG_NOISE_LENGTH = 12
FLAG_NOISE_TAG = '<noise>'
FLAG_DEFAULT_TEMPLATE = 'EE_CTF{<noise>}'

ADMIN_IDS = ['1178835', '1187538']


@babel.localeselector
def get_locale():
    locale = session.get('lang', app.config['BABEL_DEFAULT_LOCALE'])

    if locale not in app.config['BABEL_SUPPORTED_LOCALES']:
        return app.config['BABEL_DEFAULT_LOCALE']

    return locale


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
    if language in app.config['BABEL_SUPPORTED_LOCALES']:
        session['lang'] = language
    else:
        session['lang'] = app.config['BABEL_DEFAULT_LOCALE']
        flash(_("Language not supported."), "danger")

    referrer = request.referrer
    if referrer and referrer != request.url:
        return redirect(referrer)
    else:
        return redirect(url_for('home'))


@app.route('/')
def home():
    user_id = session['user']['id'] if 'user' in session else None
    challenges = Challenge.query.filter_by(edition_number=CURRENT_EDITION_NUM).order_by(Challenge.number).all()

    solved_challenges_ids = []
    if user_id is not None:
        solved_challenges = db.session.query(Solve.challenge_id).filter_by(user_id=user_id).all()
        solved_challenges_ids = [solve.challenge_id for solve in solved_challenges]

    for chg in challenges:
        chg.solved = chg.id in solved_challenges_ids

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
            logging.info(f"User {user_data['id']} logged in")

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

    user_id = session['user']['id']
    solve = Solve.query.filter_by(user_id=user_id, challenge_id=ch_id).first()
    ch_solved = solve is not None

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

    user_rating = Rating.query.filter_by(user_id=user_id, challenge_id=ch_id).first()
    rating = user_rating.rating if user_rating else 0

    user_comment = Comment.query.filter_by(user_id=user_id, challenge_id=ch_id).first()
    comment = user_comment.comment if user_comment else None

    return render_template(
        'challenge.html',
        ch_id=ch_id,
        ch_name=ch_name,
        ch_desc=ch_desc,
        user_rating=rating,
        user_comment=comment,
        top_solvers=top_solvers,
        ch_solved=ch_solved
    )


@app.route('/submit_flag/<challenge_id>', methods=['POST'])
@login_required
def submit_flag(challenge_id):
    flag = generate_flag(challenge_id)

    user_flag = request.form.get('flag')
    if user_flag == flag:
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

        logging.info(f"User {session['user']['id']} submitted correct flag \"{user_flag}\" for challenge {challenge_id}")
        flash(_("Correct flag! Well done!"), "success")
    else:
        logging.info(f"User {session['user']['id']} submitted incorrect flag \"{user_flag}\" for challenge {challenge_id}")
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


@app.route('/container_manager/manager/<image>/<challenge_id>')
@app.route('/container_manager/manager/<image>', defaults={'challenge_id': None})
@login_required
def container_manager(image, challenge_id):
    return render_template(
        'container_manager.html',
        image=image,
        manager_domain=CONTAINER_MANAGER_DOMAIN,
        challenge_id=challenge_id
    )


def get_headers():
    return {
        'X-Secret-Key': SECRET_KEY,
        'Content-Type': 'application/json'
    }


def generate_flag(challenge_id):
    flag_template = FLAG_DEFAULT_TEMPLATE
    if challenge_id is not None:
        flag_template = Challenge.query.filter_by(id=challenge_id).first_or_404().flag

    text_to_encode = f"secret_{session['user']['id']}_{flag_template}"
    noise = hashlib.sha256(text_to_encode.encode()).hexdigest()[:FLAG_NOISE_LENGTH]

    return flag_template.replace(FLAG_NOISE_TAG, noise)


@app.route('/container_manager/container_status/<image>')
@login_required
def container_status(image):
    session_id = session['user']['id']
    response = requests.post(
        f'{CONTAINER_MANAGER_API}/container_status/{image}',
        json={'session_id': session_id},
        headers=get_headers()
    )
    return jsonify(response.json())


@app.route('/container_manager/make_container/<image>/<challenge_id>')
@app.route('/container_manager/make_container/<image>', defaults={'challenge_id': None})
@login_required
def make_container(image, challenge_id):
    session_id = session['user']['id']

    flag = generate_flag(challenge_id)

    response = requests.post(
        f'{CONTAINER_MANAGER_API}/make_container/{image}',
        json={
            'session_id': session_id,
            'flag': flag
        },
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
    logging.info(f"User {session['user']['id']} downloaded file {filename}")
    return send_from_directory('static/ctf_files', filename)


def cleanup_usos_sessions():
    while True:
        logging.info(f"Cleaning up usos sessions")

        usosapi.cleanup_auth_sessions()

        time.sleep(USOSAPI_SESSION_CHECK)


threading.Thread(target=cleanup_usos_sessions, daemon=True).start()
