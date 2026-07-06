import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from models import User, ListeningEvent, Song
from services.feed_service import get_friends_listening_now
from datetime import datetime, timedelta, timezone

app = create_app()
with app.app_context():
    print("--- Reproducing Bug 2: Friends Listening Now shows old events ---")
    
    nova = User.query.filter_by(username="nova").first()
    darius = User.query.filter_by(username="darius").first()
    song = Song.query.first()
    
    if not nova or not darius:
        print("Error: Required users not found in DB.")
        exit(1)
        
    # Clean up existing recent events for Darius to isolate the test
    ListeningEvent.query.filter_by(user_id=darius.id).delete()
    
    now = datetime.now(timezone.utc)
    
    # Insert an event for Darius exactly 23 hours ago
    old_event = ListeningEvent(
        user_id=darius.id,
        song_id=song.id,
        listened_at=now - timedelta(hours=23)
    )
    db.session.add(old_event)
    db.session.commit()
    
    print(f"Added a listening event for {darius.username} 23 hours ago.")
    print(f"Fetching 'Listening Now' feed for {nova.username}...")
    
    feed = get_friends_listening_now(nova.id)
    
    found_darius = any(item['friend']['username'] == darius.username for item in feed)
    print(f"Is {darius.username} in the 'Listening Now' feed? {found_darius}")
    
    if found_darius:
        print("BUG REPRODUCED: A 23-hour-old event appears in the 'Listening Now' feed because the threshold is exactly 24 hours!")
    else:
        print("Bug not reproduced.")
