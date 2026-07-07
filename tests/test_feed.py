"""
tests/test_feed.py — Mixtape

Tests for feed service logic, particularly get_friends_listening_now.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app import create_app, db
from models import User, Song, ListeningEvent
from services.feed_service import get_friends_listening_now

@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def test_data(app):
    with app.app_context():
        u1 = User(username="user1", email="user1@example.com")
        u2 = User(username="friend1", email="friend1@example.com")
        u3 = User(username="friend2", email="friend2@example.com")
        u4 = User(username="nonfriend", email="nonfriend@example.com")
        
        db.session.add_all([u1, u2, u3, u4])
        db.session.flush()
        
        s1 = Song(title="Song 1", artist="Artist 1", shared_by=u1.id)
        s2 = Song(title="Song 2", artist="Artist 2", shared_by=u1.id)
        
        db.session.add_all([s1, s2])
        u1.friends.append(u2)
        u1.friends.append(u3)
        db.session.commit()
        
        yield {
            "u1": u1, "u2": u2, "u3": u3, "u4": u4,
            "s1": s1, "s2": s2
        }

def test_feed_shows_recent_events(app, test_data):
    """Friends with events within the 1-hour threshold should appear."""
    with app.app_context():
        u1 = test_data["u1"]
        u2 = test_data["u2"]
        s1 = test_data["s1"]
        
        now = datetime.now(timezone.utc)
        event = ListeningEvent(user_id=u2.id, song_id=s1.id, listened_at=now - timedelta(minutes=30))
        db.session.add(event)
        db.session.commit()
        
        feed = get_friends_listening_now(u1.id)
        assert len(feed) == 1
        assert feed[0]["friend"]["username"] == "friend1"
        assert feed[0]["song"]["title"] == "Song 1"

def test_feed_ignores_old_events(app, test_data):
    """Events older than 1 hour should not appear (Regression Test for Bug #2)."""
    with app.app_context():
        u1 = test_data["u1"]
        u2 = test_data["u2"]
        s1 = test_data["s1"]
        
        now = datetime.now(timezone.utc)
        # Event from 23 hours ago should NOT be included
        event = ListeningEvent(user_id=u2.id, song_id=s1.id, listened_at=now - timedelta(hours=23))
        db.session.add(event)
        db.session.commit()
        
        feed = get_friends_listening_now(u1.id)
        assert len(feed) == 0

def test_feed_ignores_non_friends(app, test_data):
    """Events from non-friends should not appear."""
    with app.app_context():
        u1 = test_data["u1"]
        u4 = test_data["u4"]
        s1 = test_data["s1"]
        
        now = datetime.now(timezone.utc)
        event = ListeningEvent(user_id=u4.id, song_id=s1.id, listened_at=now - timedelta(minutes=10))
        db.session.add(event)
        db.session.commit()
        
        feed = get_friends_listening_now(u1.id)
        assert len(feed) == 0

def test_feed_deduplicates_multiple_listens(app, test_data):
    """If a friend listens to multiple songs, only the most recent one appears."""
    with app.app_context():
        u1 = test_data["u1"]
        u2 = test_data["u2"]
        s1 = test_data["s1"]
        s2 = test_data["s2"]
        
        now = datetime.now(timezone.utc)
        
        # Older listen in the window
        event1 = ListeningEvent(user_id=u2.id, song_id=s1.id, listened_at=now - timedelta(minutes=45))
        # Newer listen in the window
        event2 = ListeningEvent(user_id=u2.id, song_id=s2.id, listened_at=now - timedelta(minutes=15))
        
        db.session.add_all([event1, event2])
        db.session.commit()
        
        feed = get_friends_listening_now(u1.id)
        assert len(feed) == 1
        assert feed[0]["song"]["title"] == "Song 2"
