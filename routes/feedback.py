"""
Feedback system — Supabase primary, SQLite fallback.
Endpoints:
  POST /feedback/submit   – submit feedback
  GET  /feedback/summary  – aggregate stats
  GET  /feedback/list     – recent entries
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from supabase_client import get_supabase_client

router = APIRouter()

DB_PATH = Path(__file__).parent.parent / "data" / "users.db"


# ── SQLite fallback ───────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_sqlite() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id          TEXT PRIMARY KEY,
                type        TEXT NOT NULL DEFAULT 'app',
                rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                category    TEXT,
                comment     TEXT,
                tags        TEXT,
                user_name   TEXT,
                user_email  TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        try:
            conn.execute("ALTER TABLE feedback ADD COLUMN user_name TEXT")
        except Exception:
            pass
        conn.commit()


_init_sqlite()


# ── Schemas ───────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    type:       str           = Field("app", description="app | itinerary | fare_calculator")
    rating:     int           = Field(..., ge=1, le=5)
    category:   Optional[str] = None
    comment:    Optional[str] = Field(None, max_length=1000)
    tags:       Optional[List[str]] = None
    user_name:  Optional[str] = None
    user_email: Optional[str] = None


class FeedbackEntry(BaseModel):
    id:         str
    type:       str
    rating:     int
    category:   Optional[str]
    comment:    Optional[str]
    tags:       Optional[List[str]]
    user_name:  Optional[str]
    user_email: Optional[str]
    created_at: str


class FeedbackSubmitResponse(BaseModel):
    success:     bool
    feedback_id: str
    message:     str


class FeedbackSummary(BaseModel):
    total:           int
    average_rating:  float
    rating_dist:     dict
    by_type:         dict
    by_category:     dict
    recent_comments: List[str]


# ── Submit ────────────────────────────────────────────────────────────────────

@router.post("/submit", response_model=FeedbackSubmitResponse, summary="Submit feedback")
async def submit_feedback(req: FeedbackRequest):
    fid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # ── Try Supabase ──
    supabase = get_supabase_client()
    if supabase:
        try:
            supabase.table("feedback").insert({
                "id":         fid,
                "type":       req.type,
                "rating":     req.rating,
                "category":   req.category,
                "comment":    req.comment,
                "tags":       req.tags,        # Supabase accepts list → JSONB
                "user_name":  req.user_name,
                "user_email": req.user_email,
                "created_at": now,
            }).execute()
            return FeedbackSubmitResponse(
                success=True, feedback_id=fid,
                message="Thank you! Your feedback helps us improve SafarSmart.",
            )
        except Exception as e:
            print(f"[Feedback] Supabase insert failed: {e} — falling back to SQLite")

    # ── SQLite fallback ──
    with _conn() as conn:
        conn.execute(
            """INSERT INTO feedback
               (id, type, rating, category, comment, tags, user_name, user_email, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fid, req.type, req.rating, req.category, req.comment,
             json.dumps(req.tags) if req.tags else None,
             req.user_name, req.user_email, now),
        )
        conn.commit()

    return FeedbackSubmitResponse(
        success=True, feedback_id=fid,
        message="Thank you! Your feedback helps us improve SafarSmart.",
    )


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=FeedbackSummary, summary="Aggregate feedback stats")
async def feedback_summary():
    rows = []

    # ── Try Supabase ──
    supabase = get_supabase_client()
    if supabase:
        try:
            result = supabase.table("feedback") \
                .select("rating, category, type, comment") \
                .order("created_at", desc=True) \
                .execute()
            rows = result.data or []
        except Exception as e:
            print(f"[Feedback] Supabase query failed: {e} — falling back to SQLite")

    # ── SQLite fallback ──
    if not rows:
        with _conn() as conn:
            db_rows = conn.execute(
                "SELECT rating, category, type, comment FROM feedback ORDER BY created_at DESC"
            ).fetchall()
            rows = [dict(r) for r in db_rows]

    if not rows:
        return FeedbackSummary(
            total=0, average_rating=0.0,
            rating_dist={str(i): 0 for i in range(1, 6)},
            by_type={}, by_category={}, recent_comments=[],
        )

    ratings     = [r["rating"] for r in rows]
    avg_rating  = round(sum(ratings) / len(ratings), 1)
    rating_dist = {str(i): ratings.count(i) for i in range(1, 6)}
    by_type:         dict = {}
    by_category:     dict = {}
    recent_comments: list = []

    for r in rows:
        t = r.get("type")     or "app"
        c = r.get("category") or "general"
        by_type[t]     = by_type.get(t, 0) + 1
        by_category[c] = by_category.get(c, 0) + 1
        if r.get("comment") and len(recent_comments) < 5:
            recent_comments.append(r["comment"])

    return FeedbackSummary(
        total=len(rows), average_rating=avg_rating,
        rating_dist=rating_dist, by_type=by_type,
        by_category=by_category, recent_comments=recent_comments,
    )


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/list", response_model=List[FeedbackEntry], summary="List recent feedback entries")
async def list_feedback(limit: int = 50):
    rows = []

    # ── Try Supabase ──
    supabase = get_supabase_client()
    if supabase:
        try:
            result = supabase.table("feedback") \
                .select("*") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            rows = result.data or []
        except Exception as e:
            print(f"[Feedback] Supabase list failed: {e} — falling back to SQLite")

    # ── SQLite fallback ──
    if not rows:
        with _conn() as conn:
            db_rows = conn.execute(
                "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            for r in db_rows:
                row = dict(r)
                if row.get("tags") and isinstance(row["tags"], str):
                    try:
                        row["tags"] = json.loads(row["tags"])
                    except Exception:
                        row["tags"] = [row["tags"]]
                rows.append(row)

    result = []
    for r in rows:
        tags = r.get("tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = [tags]
        result.append(FeedbackEntry(
            id=r["id"], type=r["type"], rating=r["rating"],
            category=r.get("category"), comment=r.get("comment"),
            tags=tags, user_name=r.get("user_name"),
            user_email=r.get("user_email"),
            created_at=str(r.get("created_at", "")),
        ))
    return result
