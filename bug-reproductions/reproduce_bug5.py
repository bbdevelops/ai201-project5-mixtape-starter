import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from models import Playlist, playlist_entries
from services.playlist_service import get_playlist_songs

app = create_app()
with app.app_context():
    print("--- Reproducing Bug 5: Last song missing from playlist ---")
    
    playlist = Playlist.query.first()
    if not playlist:
        print("Error: No playlist found in DB.")
        exit(1)
        
    # Get actual count of songs associated with this playlist in the join table
    actual_count = db.session.query(playlist_entries).filter_by(playlist_id=playlist.id).count()
    print(f"Playlist '{playlist.name}' has {actual_count} songs in the database.")
    
    # Get songs via the service function
    returned_songs = get_playlist_songs(playlist.id)
    print(f"Service returned {len(returned_songs)} songs.")
    
    if len(returned_songs) < actual_count:
        print(f"BUG REPRODUCED: The service returned {actual_count - len(returned_songs)} fewer songs than are actually in the playlist (the last song was sliced off)!")
    else:
        print("Bug not reproduced (all songs returned).")
