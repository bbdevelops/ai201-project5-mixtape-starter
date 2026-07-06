import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from models import User, Song, Notification
from services.notification_service import rate_song

app = create_app()
with app.app_context():
    print("--- Reproducing Bug 4: Missing Rating Notification ---")
    
    nova = User.query.filter_by(username="nova").first()
    darius = User.query.filter_by(username="darius").first()
    
    # Find a song shared by Nova
    song = Song.query.filter_by(shared_by=nova.id).first()
    
    if not nova or not darius or not song:
        print("Error: Required entities not found in DB.")
        exit(1)
        
    initial_notif_count = Notification.query.filter_by(user_id=nova.id).count()
    print(f"{nova.username}'s initial notification count: {initial_notif_count}")
    
    print(f"{darius.username} is rating {nova.username}'s song '{song.title}' with 5 stars...")
    rate_song(darius.id, song.id, 5)
    
    new_notif_count = Notification.query.filter_by(user_id=nova.id).count()
    print(f"{nova.username}'s new notification count: {new_notif_count}")
    
    if new_notif_count == initial_notif_count:
        print("BUG REPRODUCED: The notification count didn't increase. No notification was created for the song rating!")
    else:
        print("Bug not reproduced (notification count increased).")
