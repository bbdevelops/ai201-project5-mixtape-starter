"""
tests/test_notifications.py — Mixtape

Tests for notification logic, particularly for rating songs.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app import create_app, db
from models import User, Song, Notification, Rating
from services.notification_service import rate_song, get_notifications

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
        nova = User(username="nova", email="nova@example.com")
        darius = User(username="darius", email="darius@example.com")
        db.session.add_all([nova, darius])
        db.session.flush()

        song = Song(title="Nova's Song", artist="Nova", shared_by=nova.id)
        db.session.add(song)
        db.session.commit()
        
        yield {"nova": nova, "darius": darius, "song": song}

def test_rate_song_creates_notification(app, test_data):
    """Rating a friend's song creates a notification."""
    with app.app_context():
        darius = test_data["darius"]
        nova = test_data["nova"]
        song = test_data["song"]
        
        rate_song(darius.id, song.id, 5)
        
        notifications = get_notifications(nova.id)
        assert len(notifications) == 1
        assert notifications[0]["type"] == "song_rated"
        assert notifications[0]["body"] == "darius rated your song 'Nova's Song' 5 stars."

def test_rate_song_self_no_notification(app, test_data):
    """Rating your own song does not create a notification."""
    with app.app_context():
        nova = test_data["nova"]
        song = test_data["song"]
        
        rate_song(nova.id, song.id, 5)
        
        notifications = get_notifications(nova.id)
        assert len(notifications) == 0

def test_rate_song_updates_recent_notification(app, test_data):
    """Rapid rating updates overwrite the previous notification instead of duplicating."""
    with app.app_context():
        darius = test_data["darius"]
        nova = test_data["nova"]
        song = test_data["song"]
        
        rate_song(darius.id, song.id, 4)
        notifications = get_notifications(nova.id)
        assert len(notifications) == 1
        assert notifications[0]["body"] == "darius rated your song 'Nova's Song' 4 stars."
        
        # Change rating to 5 stars
        rate_song(darius.id, song.id, 5)
        
        notifications = get_notifications(nova.id)
        # Should still be 1 notification
        assert len(notifications) == 1
        assert notifications[0]["body"] == "darius rated your song 'Nova's Song' 5 stars."
        assert notifications[0]["read"] == False

def test_rate_song_creates_new_after_delay(app, test_data):
    """Rating updates after 1 hour create a new notification."""
    with app.app_context():
        darius = test_data["darius"]
        nova = test_data["nova"]
        song = test_data["song"]
        
        rate_song(darius.id, song.id, 4)
        
        # Manually backdate the notification by 2 hours
        notif = Notification.query.first()
        notif.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.session.commit()
        
        # Change rating to 5 stars
        rate_song(darius.id, song.id, 5)
        
        notifications = get_notifications(nova.id)
        assert len(notifications) == 2
        assert notifications[0]["body"] == "darius rated your song 'Nova's Song' 5 stars."

def test_rate_song_same_score_no_notification(app, test_data):
    """Submitting the exact same rating twice does not trigger duplicate logic or notifications."""
    with app.app_context():
        darius = test_data["darius"]
        nova = test_data["nova"]
        song = test_data["song"]
        
        rate_song(darius.id, song.id, 5)
        
        # Clear out notifications to test isolation
        Notification.query.delete()
        db.session.commit()
        
        # Submit the identical rating again
        rate_song(darius.id, song.id, 5)
        
        notifications = get_notifications(nova.id)
        assert len(notifications) == 0
