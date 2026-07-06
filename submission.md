# Mixtape Bug Hunt — Submission Doc

## AI Usage

*(To be completed in Milestone 4)*

---

## Codebase Map

### File Summaries

#### `app.py` — Flask App Factory and Database Setup
This module is the entry point for the application. Its single public function, `create_app()`, constructs a Flask application instance, configures a SQLite database via SQLAlchemy, and registers four blueprints — one each for songs, playlists, users, and the feed. Each blueprint is mounted at a distinct URL prefix (`/songs`, `/playlists`, `/users`, `/feed`). The factory also calls `db.create_all()` inside an app context so that tables exist at startup. There is no root route (`/`), which is why `GET /` returns a 404 — this is expected for an API-only backend.

#### `models.py` — SQLAlchemy Models for All Entities
Defines 6 ORM models and 3 association tables:

| Model             | Purpose |
|-------------------|---------|
| `User`            | Stores username, email, listening streak count, and `last_listened_at` timestamp. Has a self-referential many-to-many friendship relationship via the `friendships` join table. |
| `Tag`             | A simple label (e.g., "rap", "lo-fi") that can be attached to songs. |
| `Song`            | A shared song with title, artist, album, genre, and a `shared_by` FK pointing to the user who shared it. Has a many-to-many with `Tag` through the `song_tags` join table. |
| `ListeningEvent`  | Records that a specific user listened to a specific song at a specific time. Used by both the streak system and the feed. |
| `Rating`          | A 1–5 score a user gives a song. Enforces a unique constraint on `(user_id, song_id)` so each user rates each song at most once. |
| `Playlist`        | Has a name, creator, and a collaborative flag. Songs are linked through the `playlist_entries` join table, which adds a `position` column for explicit ordering and an `added_by` FK. |
| `Notification`    | A user-facing notification with a type string (e.g., `"song_added_to_playlist"`, `"song_rated"`), a body message, and a read/unread flag. |

Every model has a `to_dict()` method that returns a JSON-serializable dictionary — this is what the routes return to the client.

#### `routes/` — HTTP Endpoint Layer
Each route file defines a Flask Blueprint with endpoints for one feature area. The routes do input parsing (reading JSON bodies, query params) and response formatting (returning `jsonify()`). **All business logic is delegated to the corresponding service.** The routes themselves contain no database queries or domain logic.

- **`routes/songs.py`** — Handles `GET /songs/search?q=...` (search by title/artist), `GET /songs/<id>` (song detail), `POST /songs/<id>/rate` (rate a song), and `POST /songs/<id>/listen` (record a listening event).
- **`routes/playlists.py`** — Handles `POST /playlists/` (create playlist), `GET /playlists/<id>` (playlist metadata), `GET /playlists/<id>/songs` (ordered song list), and `POST /playlists/<id>/songs` (add a song to a playlist).
- **`routes/users.py`** — Handles `GET /users/<id>` (user profile), `GET /users/<id>/streak` (current streak), `GET /users/<id>/notifications` (notifications with optional `?unread_only=true` filter), and `POST /users/notifications/<id>/read` (mark notification read).
- **`routes/feed.py`** — Handles `GET /feed/<id>/listening-now` (friends currently listening) and `GET /feed/<id>/activity` (general activity feed).

#### `services/` — Business Logic Layer
Each service file contains the actual logic for one feature. All database access and domain rules live here.

- **`services/streak_service.py`** — Manages listening streaks. `record_listening_event()` creates a `ListeningEvent` and then calls `update_listening_streak()` to adjust the user's streak count based on how many calendar days have passed since their last listen. `get_streak()` is a simple lookup.
- **`services/feed_service.py`** — Builds the "Friends Listening Now" feed. `get_friends_listening_now()` finds listening events from a user's friends within a 24-hour window (`RECENT_THRESHOLD`), deduplicates to show only the most recent song per friend, and returns them sorted by recency. `get_activity_feed()` is a simpler variant that returns the last N events from friends with no time filter.
- **`services/search_service.py`** — Provides song search. `search_songs()` performs a case-insensitive `ILIKE` query on both `title` and `artist` fields, with an `outerjoin` on `song_tags`. `get_song()` retrieves a single song by ID.
- **`services/notification_service.py`** — Handles notification creation and retrieval. `create_notification()` is a generic helper. `add_to_playlist()` adds a song to a playlist and notifies the original sharer. `rate_song()` saves or updates a rating (but does not send a notification). `get_notifications()` and `mark_as_read()` handle the read side.
- **`services/playlist_service.py`** — Manages playlist CRUD. `create_playlist()` creates a new playlist. `get_playlist_songs()` queries the `playlist_entries` join table ordered by `position` to return songs in their explicit order. `get_playlist()` and `get_user_playlists()` handle metadata retrieval.

#### `seed_data.py` — Test Data Population
Creates 5 users (nova, darius, simone, kenji, aaliya) with established friendships, 13 songs with varying tag counts (0, 1, and 3+ tags), 3 playlists with 5–7 songs each, listening events spanning the past 2 weeks (including very recent ones within 30 minutes), pre-set streak values and `last_listened_at` timestamps, and one existing `"song_added_to_playlist"` notification. The seed data is intentionally structured to expose each of the 5 bugs under the right conditions.

#### `tests/` — Test Suite
Contains `test_streaks.py`, `test_search.py`, and `test_playlists.py`. Each test file uses a fresh in-memory SQLite database via `create_app()` with an overridden config, ensuring tests don't depend on seed data.

---

### Data Flow Traces

#### Data Flow 1 — User rates a song (triggers notification path)

1. Client sends `POST /songs/<song_id>/rate` with JSON body `{"user_id": "...", "score": 4}`.
2. `routes/songs.py` → `rate()` extracts `user_id` and `score` from the request body and calls `notification_service.rate_song(user_id, song_id, int(score))`.
3. `services/notification_service.py` → `rate_song()`:
   - Validates the score is between 1–5.
   - Looks up the `Song` and `User` by ID.
   - Checks for an existing `Rating` for this `(user_id, song_id)` pair: if found, updates the score; otherwise, creates a new `Rating`.
   - Commits to the database.
   - Returns the `Rating` instance.
   - **Notably absent**: there is no call to `create_notification()` here. Compare this with `add_to_playlist()` in the same file, which *does* call `create_notification()` after adding a song. This means the song's original sharer is never notified when someone rates their song.
4. `routes/songs.py` → `rate()` serializes the returned rating via `rating.to_dict()` and returns 201.

#### Data Flow 2 — User searches for songs

1. Client sends `GET /songs/search?q=crown`.
2. `routes/songs.py` → `search()` reads the `q` query parameter and calls `search_service.search_songs(query)`.
3. `services/search_service.py` → `search_songs()`:
   - Builds a query on the `Song` model.
   - Performs an `outerjoin` on the `song_tags` association table (joining `Song.id == song_tags.c.song_id`).
   - Filters with `OR(title.ilike('%query%'), artist.ilike('%query%'))`.
   - Calls `.all()` to execute.
   - Converts each result to a dict via `song.to_dict()`.
   - **Key detail**: because the query joins against `song_tags`, a song with 3 tags will appear as 3 rows in the SQL result set. SQLAlchemy's `.all()` returns all rows, so the same `Song` object can appear multiple times in the result list.
4. `routes/songs.py` → `search()` wraps the results in `{"results": [...], "count": N}` and returns them.

---

### Function Explanations

#### `update_listening_streak()` — Bug #1 (Streak keeps resetting)

**Location**: [streak_service.py](file:///c:/Users/bzkl1/Documents/CodePath/AI201/ai201-project5-mixtape-starter/services/streak_service.py), lines 42–78.

**Purpose**: Determines whether a user's listening streak should increment, stay the same, or reset, based on when they last listened.

**Step-by-step walkthrough**:

1. **Extract today's date** (line 56): `today = now.date()` — converts the full UTC datetime to just a calendar date for day-level comparison.

2. **Handle first-ever listen** (lines 58–61): If `user.last_listened_at is None`, the user has never listened before. Set their streak to 1 and record `now` as their last listen time. Return early.

3. **Normalize timezone** (lines 63–65): If the stored `last_listened_at` has no timezone info (naive datetime), assume UTC by attaching `timezone.utc`. This guards against inconsistent datetime storage.

4. **Calculate days since last listen** (lines 67–68): `last_date = last_listened.date()` extracts the calendar date, then `days_since_last = (today - last_date).days` gives the integer number of days between then and now.

5. **Branch on the gap** (lines 70–78):
   - **Same day** (`days_since_last == 0`): No change — the user already listened today.
   - **Next day AND not Sunday** (`days_since_last == 1 and today.weekday() != 6`): Increment the streak by 1.
   - **Everything else**: Reset streak to 1.

6. **Update timestamp** (line 78): Set `user.last_listened_at = now`.

**What it returns**: `None` — it mutates the `user` object in place (the caller commits the transaction).

**What could cause unexpected values**:
- The condition `today.weekday() != 6` on line 73 is a guard that fires when `today` is a Sunday (Python's `weekday()` returns 6 for Sunday). This means that even if a user listened yesterday (Saturday) and listens again today (Sunday) — a consecutive-day listen that *should* increment the streak — the `weekday() != 6` check causes the code to fall through to the `else` branch and **reset the streak to 1**. The Sunday guard breaks normal consecutive-day streak logic.
- If `last_listened_at` were stored without timezone info AND in a non-UTC timezone, the `.date()` comparison could be off by a day at timezone boundaries.

---

#### `get_playlist_songs()` — Bug #5 (Last song in playlist missing)

**Location**: [playlist_service.py](file:///c:/Users/bzkl1/Documents/CodePath/AI201/ai201-project5-mixtape-starter/services/playlist_service.py), lines 38–66.

**Purpose**: Retrieves all songs belonging to a playlist, returned in explicit position order (ascending). This is the function called when a user views a playlist's track listing.

**Step-by-step walkthrough**:

1. **Look up the playlist** (lines 53–55): `db.session.get(Playlist, playlist_id)` fetches the playlist by primary key. If it doesn't exist, raises a `ValueError`.

2. **Query songs via the join table** (lines 58–64): Builds a SQLAlchemy query that:
   - Queries the `Song` model.
   - Joins against the `playlist_entries` association table on `Song.id == playlist_entries.c.song_id`.
   - Filters to only entries matching this specific `playlist_id`.
   - Orders by `playlist_entries.c.position` ascending — so songs come back in the order they were arranged in the playlist.
   - Calls `.all()` to return all matching `Song` objects as a list.

3. **Serialize and return** (line 66): Converts each song to a dict via `song.to_dict()` — but applies `songs[:-1]`, a Python slice that **removes the last element** of the list before returning.

**What it returns**: A list of song dicts, one for each song in the playlist — except the last one.

**What could cause unexpected values**:
- The `songs[:-1]` slice on line 66 unconditionally removes the last song from the result. If a playlist has 7 songs, only 6 are returned. If a playlist has 1 song, `songs[:-1]` returns an empty list — the user sees no songs at all even though one exists.
- This is a silent data loss — no error is raised, the response just has fewer songs than expected. The `count` field in the route response will also be wrong because it counts the already-truncated list.

---

#### `search_songs()` — Bug #3 (Duplicate songs in search)

**Location**: [search_service.py](file:///c:/Users/bzkl1/Documents/CodePath/AI201/ai201-project5-mixtape-starter/services/search_service.py), lines 11–37.

**Purpose**: Searches for songs whose title or artist matches a query string (case-insensitive). Returns all matching songs along with their tags.

**Step-by-step walkthrough**:

1. **Build the query with an outerjoin** (lines 25–34):
   - Starts with `db.session.query(Song)` — the query is selecting `Song` objects.
   - Performs `.outerjoin(song_tags, Song.id == song_tags.c.song_id)` — this left-joins the `song_tags` association table. The intent is to include tag information, but since `Song` already has a `tags` relationship defined in the model (via `db.relationship("Tag", secondary=song_tags, lazy="subquery")`), this join is redundant for loading tags.
   - Filters with `db.or_(Song.title.ilike(...), Song.artist.ilike(...))` — case-insensitive substring match on either field.
   - Calls `.all()` to execute and return the results.

2. **Serialize results** (line 37): Maps each `Song` in the result list through `song.to_dict()`, which includes `"tags": [tag.name for tag in self.tags]` — the tags are loaded via the ORM relationship, not from the join.

**What it returns**: A list of song dicts. Each dict includes all song fields plus a `tags` list of tag name strings.

**What could cause unexpected values**:
- The `outerjoin` on `song_tags` causes the SQL query to produce **one row per tag** for each matching song. A song with 3 tags (e.g., "Crown Heights Anthem" tagged with "rap", "hip-hop", "boom bap") generates 3 rows in the SQL result. SQLAlchemy's `.all()` returns all 3 rows as 3 separate (but identical) `Song` object references, so the final list contains 3 copies of that song.
- Songs with 0 tags produce exactly 1 row (because it's a LEFT outer join — the song row is preserved even with no matching tag rows). Songs with 1 tag produce 1 row. Only songs with **2+ tags** are duplicated.
- The duplicates are identical (same song object serialized multiple times), so the API response contains repeated entries that confuse users.
- The `outerjoin` is unnecessary here — removing it (or adding `.distinct()`) would eliminate the duplicates while still correctly loading tags via the ORM relationship.

---

### Architectural Patterns

- **Route → Service delegation**: Every route immediately delegates to a service function. Routes handle HTTP concerns (parsing input, formatting responses, status codes); services handle domain logic and database access. This separation is consistent across all four route files.
- **UUID-based primary keys**: All models use `uuid4()` string primary keys generated via a shared `generate_uuid()` helper, rather than auto-incrementing integers.
- **Association tables with metadata**: The `playlist_entries` table isn't just a join table — it carries `position`, `added_by`, and `added_at` columns. This makes playlist ordering explicit rather than relying on insertion order.
- **`to_dict()` serialization**: Every model has a `to_dict()` method that the routes use for JSON serialization. There's no separate serialization layer.

---

## Initial Bug Triage Plan

After reading all five issue descriptions and the affected service files, I plan to tackle these three bugs first:

### 1. Bug #5 — The last song in a playlist never shows up
**Affected file**: `services/playlist_service.py`
**Why tackle first**: This appears to be the most isolated and straightforward bug. The `get_playlist_songs()` function returns `songs[:-1]` (line 66), which slices off the last element of the list. This is a quick-win fix that will build familiarity with the codebase's query and serialization patterns. It also has a corresponding test file (`test_playlists.py`) that can verify the fix.

### 2. Bug #1 — My listening streak keeps resetting
**Affected file**: `services/streak_service.py`
**Why tackle second**: This is a classic boundary-condition bug. The streak increment condition on line 73 includes `today.weekday() != 6`, which prevents the streak from incrementing on Sundays — even for legitimate consecutive-day listening. This requires understanding Python's `datetime.weekday()` conventions and reasoning about edge cases, which is a high-value learning exercise. The test file `test_streaks.py` can help validate the fix.

### 3. Bug #3 — The same song keeps showing up twice in search
**Affected file**: `services/search_service.py`
**Why tackle third**: This is the most conceptually interesting of the three. The `outerjoin` on `song_tags` in `search_songs()` produces one row per tag match, so songs with multiple tags appear as duplicates in the result. This requires understanding how SQL joins interact with ORM query results. The fix is targeted (deduplicate the results), but the root cause analysis involves explaining why the join produces duplicates and under what conditions (only multi-tagged songs). The test file `test_search.py` can validate.

### Bugs #2 and #4 — Deferred for stretch
- **#2 (Friends Listening Now shows old events)**: The `feed_service.py` uses a 24-hour `RECENT_THRESHOLD` but the seed data's "old" events from the comment "1-14 days ago" are actually created with `timedelta(hours=2 + i*8)` — some fall within 24 hours. This needs careful analysis of the seed data timing to reproduce.
- **#4 (Missing rating notification)**: The `rate_song()` function in `notification_service.py` creates/updates the rating but never calls `create_notification()`, unlike `add_to_playlist()` which does. This is an architectural omission rather than a logic error. Straightforward to fix but requires understanding the notification pattern.

---

## Root Cause Analysis Entries

### Bug #5 — The last song in a playlist never shows up

**How I reproduced it:**

1. Confirmed the seed database has 7 songs in the "Late Night Vibes" playlist by directly querying the `playlist_entries` table:
   ```
   .venv\Scripts\python.exe -c "from app import create_app, db; from models import playlist_entries; app = create_app(); ctx = app.app_context(); ctx.push(); entries = db.session.execute(db.select(playlist_entries).where(playlist_entries.c.playlist_id == '19a4c6c9-5457-4d1b-8104-77551cb28d6b').order_by(playlist_entries.c.position)).fetchall(); print(f'{len(entries)} entries'); [print(f'  Position {e.position}: song_id={e.song_id}') for e in entries]"
   ```
   Result: **7 entries** at positions 1–7. The 7th song (position 7) is "Free Throws" by Hoop Dreams.

2. Hit the API endpoint to retrieve the playlist's songs:
   ```
   GET http://127.0.0.1:5000/playlists/19a4c6c9-5457-4d1b-8104-77551cb28d6b/songs
   ```
   Result: `"count": 6` — only 6 songs returned. The last song ("Free Throws" at position 7) is **missing** from the response. No error is raised; the response looks normal but has fewer songs than expected.

3. The bug is **unconditional** — it affects every playlist, every time. Any `GET /playlists/<id>/songs` request will silently drop the last song.

4. **Automated Reproduction:** I codified this reproduction into a standalone script. Run `python bug-reproductions/reproduce_bug5.py` to see the actual database count compared directly against the service's returned list size.

**How I found the root cause:** *(To be completed in Milestone 3)*

**The root cause:** *(To be completed in Milestone 3)*

**My fix and side-effect check:** *(To be completed in Milestone 3)*

---

### Bug #1 — My listening streak keeps resetting

**How I reproduced it:**

1. The bug is highly dependent on the current day of the week. Because the API uses the real-time `datetime.now(timezone.utc)`, hitting the `/listen` endpoint only reproduces the bug if the current UTC time is a Sunday. If tested on a Monday UTC (as is currently the case, `2026-07-06`), the streak will successfully increment, which masks the bug.
2. To reliably reproduce it regardless of the real-world time, I codified a script that simulates a Saturday-to-Sunday transition by explicitly passing a Sunday `datetime` into the service function. Run `python bug-reproductions/reproduce_bug1.py` to execute this.
3. **Result:** The script outputs `New streak: 1`. The streak was erroneously reset from 3 to 1 instead of incrementing to 4.
4. **Conclusion:** The bug specifically fires on Sundays. The condition on line 73 of `streak_service.py` (`today.weekday() != 6`) prevents the streak from incrementing when `today` is Sunday (which evaluates to `6` in Python). Because of this logic, legitimate consecutive-day listens on Sundays fall through to the `else` block, which resets the streak.

**How I found the root cause:** *(To be completed in Milestone 3)*

**The root cause:** *(To be completed in Milestone 3)*

**My fix and side-effect check:** *(To be completed in Milestone 3)*

---

### Bug #3 — The same song keeps showing up twice in search

**How I reproduced it:**

1. Identified the conditions needed: the bug only affects songs with **2+ tags**, because the `outerjoin` on `song_tags` in `search_service.py` produces one SQL row per tag match. Songs with 0 or 1 tag produce exactly 1 row and are never duplicated.

2. Tested with "Crown Heights Anthem" (3 tags: rap, hip-hop, boom bap) by examining the raw SQL output:
   ```sql
   SELECT s.id, s.title, st.tag_id
   FROM song s
   LEFT OUTER JOIN song_tags st ON s.id = st.song_id
   WHERE s.title LIKE '%Crown%' OR s.artist LIKE '%Crown%'
   ```
   Result: **3 rows** — the same song appears once per tag, producing 3 identical rows in the join result.

3. Verified the duplication manifests in SQLAlchemy 2.0's `select()` query style:
   ```python
   stmt = select(Song).outerjoin(song_tags, Song.id == song_tags.c.song_id).filter(...)
   results = db.session.execute(stmt).scalars().all()
   # Returns 3 Song objects — all "Crown Heights Anthem"
   ```

4. Noted that the current code uses the legacy `session.query(Song).all()` pattern, which **masks** the duplicates via SQLAlchemy 2.0's identity map (returning 1 object instead of 3). However, the underlying SQL is still producing 3 rows, and:
   - The bug would fully manifest if the code were migrated to SA 2.0's recommended `select()` style
   - The `outerjoin` is **unnecessary** — tags are already loaded via the ORM `relationship("Tag", secondary=song_tags, lazy="subquery")` defined in `models.py`
   - The redundant join causes unnecessary database work (row multiplication) even when the ORM deduplicates

5. Contrasted with "Midnight Drive" (0 tags) — search returns exactly 1 row, no duplication. And with "Block Party" (1 tag) — also 1 row. Only multi-tagged songs are affected.

6. **Automated Reproduction:** I codified this into a script. Run `python bug-reproductions/reproduce_bug3.py` to see the masked Python results side-by-side with the raw duplicated SQL rows.

**How I found the root cause:** *(To be completed in Milestone 3)*

**The root cause:** *(To be completed in Milestone 3)*

**My fix and side-effect check:** *(To be completed in Milestone 3)*

---

### Bug #2 — Friends Listening Now shows people from yesterday

**How I reproduced it:**

1. Examined `feed_service.py` and saw `RECENT_THRESHOLD` is set to `timedelta(hours=24)`. This confirms that anyone who listened within the last 24 hours will show up in the "Listening Now" feed.
2. Looked at `seed_data.py` and saw it creates "older events" spaced by 8 hours. For instance, it generates a listening event for `simone` 18 hours ago, and `kenji` 26 hours ago.
3. If we query `darius`'s feed (whose friends are `nova` and `simone`):
   ```
   GET http://127.0.0.1:5000/feed/7fe13470-0e58-49ad-9d52-b88c55e41a0f/listening-now
   ```
   Result: The API will return `nova` (listened 2 hours ago) and `simone` (listened 15 minutes ago, but if we remove her recent listen, it would return her 18-hour-old listen). The 24-hour threshold directly allows events from "yesterday" (e.g. 18-23 hours ago) to appear as "Listening Now".

4. **Automated Reproduction:** I wrote a script that isolates this test by creating a 23-hour-old listening event and confirming it still appears in the feed. Run `python bug-reproductions/reproduce_bug2.py`.

**How I found the root cause:** *(To be completed in Milestone 3)*

**The root cause:** *(To be completed in Milestone 3)*

**My fix and side-effect check:** *(To be completed in Milestone 3)*

---

### Bug #4 — I got notified when a friend added my song to a playlist but not when they rated it

**How I reproduced it:**

1. Identified the requirement: a user must rate a song that was originally shared by someone else.
2. Hit the rate endpoint to rate a song shared by Nova (`users[0]`), using Darius's account (`users[1]`):
   ```
   POST http://127.0.0.1:5000/songs/77b7fc9d-375c-4737-83af-0f78708f201b/rate
   Body: {"user_id": "7fe13470-0e58-49ad-9d52-b88c55e41a0f", "score": 5}
   ```
   Result: 201 Created — the rating was recorded successfully.
3. Checked Nova's notifications to see if she was alerted:
   ```
   GET http://127.0.0.1:5000/users/4e553a2e-8f4d-4112-9ee4-d8c3d0d27c99/notifications
   ```
   Result: No new rating notification was returned. The API only returned the pre-existing seed data notification (for a song added to a playlist). The rating notification was completely missing.

4. **Automated Reproduction:** To verify this programmatically without manual API calls, I wrote a reproduction script that rates a song and asserts that the notification count fails to increase. Run `python bug-reproductions/reproduce_bug4.py`.

**How I found the root cause:** *(To be completed in Milestone 3)*

**The root cause:** *(To be completed in Milestone 3)*

**My fix and side-effect check:** *(To be completed in Milestone 3)*

---

## Commit History Screenshot

*(To be completed in Milestone 4)*

