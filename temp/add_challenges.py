import os
os.chdir("./..")

from datetime import datetime, timedelta
from model import Challenge
from app import app, db

with app.app_context():
    challenges = [
        Challenge(
            number=1,
            edition_number=1,
            name="SQL Injection",
            name_pl="pl_SQL Injection",
            description="Learn how to perform SQL Injection attacks.",
            description_pl="pl_Learn how to perform SQL Injection attacks.",
            start_date=datetime.now() - timedelta(days=1),  # dostępny od wczoraj
            difficulty="Easy",
            flag="EE_CTF(fl4g)",
            icon="fas fa-database"
        ),
        Challenge(
            number=2,
            edition_number=1,
            name="XSS Attack",
            name_pl="pl_XSS Attack",
            description="Learn how to perform XSS attacks.",
            description_pl="pl_Learn how to perform XSS attacks.",
            start_date=datetime.now() + timedelta(days=1),  # dostępny od jutra
            difficulty="Medium",
            flag="EE_CTF(fl4g)",
            icon="fas fa-code"
        ),
        Challenge(
            number=3,
            edition_number=1,
            name="Buffer Overflow",
            name_pl="pl_Buffer Overflow",
            description="Learn how to perform Buffer Overflow attacks.",
            description_pl="pl_Learn how to perform Buffer Overflow attacks.",
            start_date=datetime.now() + timedelta(days=2),  # dostępny za dwa dni
            difficulty="Hard",
            flag="EE_CTF(fl4g)",
            icon="fas fa-memory"
        ),
        Challenge(
            number=4,
            edition_number=1,
            name="Cryptography",
            name_pl="pl_Cryptography",
            description="Learn the basics of cryptography.",
            description_pl="pl_Learn the basics of cryptography.",
            start_date=datetime.now() + timedelta(days=3),  # dostępny za trzy dni
            difficulty="Medium",
            flag="EE_CTF(fl4g)",
            icon="fas fa-lock"
        ),
        Challenge(
            number=5,
            edition_number=1,
            name="Reverse Engineering",
            name_pl="pl_Reverse Engineering",
            description="Learn the basics of reverse engineering.",
            description_pl="pl_Learn the basics of reverse engineering.",
            start_date=datetime.now() + timedelta(days=4),  # dostępny za cztery dni
            difficulty="Hard",
            flag="EE_CTF(fl4g)",
            icon="fas fa-tools"
        )
    ]

    for challenge in challenges:
        db.session.add(challenge)

    db.session.commit()

    print("Challenges added to the database.")
