import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from models import User
from services.streak_service import update_listening_streak
from datetime import datetime, timezone

app = create_app()
with app.app_context():
    print("--- Reproducing Bug 1: Listening Streak Resets ---")
    
    # 1. Get Darius and set his last listen to a Saturday with a streak of 3
    user = User.query.filter_by(username="darius").first()
    if not user:
        print("Error: User 'darius' not found in DB.")
        exit(1)
        
    user.last_listened_at = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
    user.listening_streak = 3
    db.session.commit()
    
    print(f"Initial state: streak={user.listening_streak}, last_listened={user.last_listened_at.strftime('%A')}")
    
    # 2. Trigger the streak update, explicitly passing a Sunday as 'now'
    mock_sunday = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    print("Simulating a listening event on Sunday...")
    
    update_listening_streak(user, mock_sunday)

    print(f"New streak: {user.listening_streak}")
    if user.listening_streak == 1:
        print("BUG REPRODUCED: The streak was erroneously reset from 3 to 1 instead of incrementing to 4!")
    else:
        print("Bug not reproduced (streak did not reset).")
