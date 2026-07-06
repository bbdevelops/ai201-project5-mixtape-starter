import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from models import Song, song_tags
from services.search_service import search_songs

app = create_app()
with app.app_context():
    print("--- Reproducing Bug 3: Duplicates in search ---")
    
    # "Crown Heights Anthem" has 3 tags
    query = "Crown"
    print(f"Searching for '{query}' using search_service.search_songs()...")
    results = search_songs(query)
    
    print(f"Found {len(results)} results returned by the Python function.")
    for i, r in enumerate(results):
        print(f"  Result {i+1}: {r['title']} (Tags: {r['tags']})")
        
    if len(results) > 1:
        print("BUG REPRODUCED: The same song appears multiple times in the serialized results!")
    else:
        print("Note: The Python results do NOT show duplicates here because SQLAlchemy's identity map masks them by deduplicating identical primary keys in this version.")
        
    print("\nHowever, let's look at the underlying SQL query that generates the results:")
    stmt = db.session.query(Song).outerjoin(song_tags, Song.id == song_tags.c.song_id).filter(Song.title.ilike(f"%{query}%"))
    print(stmt)
    
    # Let's execute it and count the raw rows returned from the database
    raw_rows = db.session.execute(stmt.statement).fetchall()
    print(f"\nRaw SQL rows returned: {len(raw_rows)}")
    if len(raw_rows) > 1:
        print("BUG REPRODUCED (SQL Level): The outerjoin causes the database to return 1 row per tag, doing unnecessary work and producing duplicates before the ORM filters them!")
