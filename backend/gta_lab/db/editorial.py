"""Editor notes and briefs (ownership class ``editor_note``).

* Text is independently authored. Writing a note or brief whose text contains the current
  title or channel title of a referenced video is refused (``CopiedApiDataError``).
* Source references may only point at available, unexpired videos when written. When they
  later expire, the retention purge removes them and redacts copied fragments.
* Views and exports show only eligible references; expired ones are counted, not shown.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Literal

from ..clock import to_db_ts
from .connection import Database
from .retention import BRIEF_TEXT_COLUMNS, MIN_REDACT_LEN
from .sources import SourceRepository

NoteKind = Literal["watched_observation", "own_gameplay", "idea", "packaging_note"]
RefState = Literal["available", "inaccessible"]
WATCH_URL = "https://www.youtube.com/watch?v={}"


class IneligibleSourceError(ValueError):
    pass


class CopiedApiDataError(ValueError):
    pass


@dataclass(frozen=True)
class SourceRef:
    video_id: str
    state: RefState
    role: str | None = None

    @property
    def link(self) -> str | None:
        return WATCH_URL.format(self.video_id) if self.state == "available" else None


@dataclass(frozen=True)
class NoteView:
    note_id: int
    kind: str
    body: str
    author: str
    watched_at_utc: str | None
    created_at_utc: str
    updated_at_utc: str
    redacted_at_utc: str | None
    refs: list[SourceRef]
    refs_no_longer_available: int


@dataclass
class BriefDraft:
    working_title: str
    pillar: Literal["systems_myth_tests", "map_world_hidden_details", "missions_useful_discoveries"]
    format: Literal["long_form", "short", "reel"]
    alternate_title: str | None = None
    viewer_question: str | None = None
    original_angle: str | None = None
    first_frame: str | None = None
    cold_open: str | None = None
    shot_checklist: str | None = None
    verification_plan: str | None = None
    thumbnail_hypothesis_a: str | None = None
    thumbnail_hypothesis_b: str | None = None
    cover_design: str | None = None
    payoff_beat: str | None = None
    rough_duration_seconds: int | None = None
    spoiler_level: Literal["none", "light", "heavy"] | None = None
    time_cost_hours: float | None = None
    fallback_plan: str | None = None
    reel_adaptation: str | None = None
    success_measure: str | None = None
    capture_id: str | None = None
    gta_vi_status: Literal["unknown", "verified_in_own_gameplay"] = "unknown"

    def text_values(self) -> list[str]:
        return [v for c in BRIEF_TEXT_COLUMNS if (v := getattr(self, c, None))]


@dataclass(frozen=True)
class BriefView:
    brief_id: int
    draft: BriefDraft
    created_at_utc: str
    updated_at_utc: str
    redacted_at_utc: str | None
    refs: list[SourceRef] = field(default_factory=list)
    refs_no_longer_available: int = 0


_DRAFT_COLUMNS = [f.name for f in fields(BriefDraft)]


class EditorialRepository:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.sources = SourceRepository(db)

    # ---------- guards ----------
    def _eligible_fragments(self, video_ids: Sequence[str]) -> list[str]:
        """Return the copyable API fragments of the referenced videos; refuse ineligible ones."""
        frags: list[str] = []
        for vid in dict.fromkeys(video_ids):
            view = self.sources.get_video(vid)
            if view.state != "available":
                raise IneligibleSourceError(f"source {vid!r} is {view.state}; cannot reference it")
            frags += [f for f in (view.title, view.channel_title) if f]
        return frags

    @staticmethod
    def _guard_copy(texts: Sequence[str], fragments: Sequence[str]) -> None:
        for text in texts:
            low = text.casefold()
            for frag in fragments:
                if len(frag) >= MIN_REDACT_LEN and frag.casefold() in low:
                    raise CopiedApiDataError(
                        "text contains copied YouTube metadata from a referenced video; "
                        "write it in your own words or drop the reference"
                    )

    def _refs(self, table: str, key: str, owner_id: int) -> tuple[list[SourceRef], int]:
        has_role = table == "brief_source_refs"
        cols = "video_id, role" if has_role else "video_id, NULL AS role"
        rows = self.db.conn.execute(
            f"SELECT {cols} FROM {table} WHERE {key} = ? ORDER BY video_id",  # noqa: S608
            (owner_id,),
        ).fetchall()
        refs: list[SourceRef] = []
        hidden = 0
        for r in rows:
            state = self.sources.get_video(r["video_id"]).state
            if state in ("available", "inaccessible"):
                refs.append(SourceRef(r["video_id"], state, r["role"]))
            else:
                hidden += 1  # expired, awaiting purge: never shown
        return refs, hidden

    # ---------- notes ----------
    def add_note(
        self,
        kind: NoteKind,
        body: str,
        author: str,
        watched_at: datetime | None = None,
        source_video_ids: Sequence[str] = (),
    ) -> int:
        if kind == "watched_observation" and watched_at is None:
            raise ValueError("a watched observation needs the time a human watched it")
        if kind != "watched_observation" and watched_at is not None:
            raise ValueError("watched_at is only for watched observations")
        self._guard_copy([body], self._eligible_fragments(source_video_ids))
        now = to_db_ts(self.db.clock.now())
        with self.db.transaction() as conn:
            note_id = conn.execute(
                "INSERT INTO editor_notes (kind, body, watched_at_utc, author, created_at_utc, "
                "updated_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
                (kind, body, to_db_ts(watched_at) if watched_at else None, author, now, now),
            ).lastrowid
            conn.executemany(
                "INSERT INTO note_source_refs (note_id, video_id) VALUES (?, ?)",
                [(note_id, v) for v in dict.fromkeys(source_video_ids)],
            )
        if note_id is None:
            raise RuntimeError("insert returned no row id")
        return int(note_id)

    def update_note_body(self, note_id: int, body: str) -> None:
        vids = [
            r[0]
            for r in self.db.conn.execute(
                "SELECT video_id FROM note_source_refs WHERE note_id = ?", (note_id,)
            )
        ]
        live_vids = [v for v in vids if self.sources.get_video(v).state == "available"]
        self._guard_copy([body], self._eligible_fragments(live_vids))
        now = to_db_ts(self.db.clock.now())
        with self.db.transaction() as conn:
            if not conn.execute(
                "UPDATE editor_notes SET body = ?, updated_at_utc = ? WHERE note_id = ?",
                (body, now, note_id),
            ).rowcount:
                raise KeyError(note_id)

    def get_note(self, note_id: int) -> NoteView:
        row = self.db.conn.execute(
            "SELECT * FROM editor_notes WHERE note_id = ?", (note_id,)
        ).fetchone()
        if row is None:
            raise KeyError(note_id)
        refs, hidden = self._refs("note_source_refs", "note_id", note_id)
        return NoteView(
            note_id=row["note_id"],
            kind=row["kind"],
            body=row["body"],
            author=row["author"],
            watched_at_utc=row["watched_at_utc"],
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
            redacted_at_utc=row["redacted_at_utc"],
            refs=refs,
            refs_no_longer_available=hidden,
        )

    def delete_note(self, note_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM editor_notes WHERE note_id = ?", (note_id,))

    # ---------- briefs ----------
    def create_brief(
        self, draft: BriefDraft, source_video_ids: Sequence[str] = (), role: str = "example"
    ) -> int:
        self._guard_copy(draft.text_values(), self._eligible_fragments(source_video_ids))
        now = to_db_ts(self.db.clock.now())
        cols = ", ".join(_DRAFT_COLUMNS)
        marks = ", ".join("?" * len(_DRAFT_COLUMNS))
        with self.db.transaction() as conn:
            brief_id = conn.execute(
                f"INSERT INTO briefs ({cols}, created_at_utc, updated_at_utc) "  # noqa: S608
                f"VALUES ({marks}, ?, ?)",
                (*(getattr(draft, c) for c in _DRAFT_COLUMNS), now, now),
            ).lastrowid
            conn.executemany(
                "INSERT INTO brief_source_refs (brief_id, video_id, role) VALUES (?, ?, ?)",
                [(brief_id, v, role) for v in dict.fromkeys(source_video_ids)],
            )
        if brief_id is None:
            raise RuntimeError("insert returned no row id")
        return int(brief_id)

    def get_brief(self, brief_id: int) -> BriefView:
        row = self.db.conn.execute(
            "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
        ).fetchone()
        if row is None:
            raise KeyError(brief_id)
        draft = BriefDraft(**{c: row[c] for c in _DRAFT_COLUMNS})
        refs, hidden = self._refs("brief_source_refs", "brief_id", brief_id)
        return BriefView(
            brief_id=brief_id,
            draft=draft,
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
            redacted_at_utc=row["redacted_at_utc"],
            refs=refs,
            refs_no_longer_available=hidden,
        )

    def export_brief_text(self, brief_id: int) -> str:
        """Original brief text only, plus watch links for references that are still eligible.

        No YouTube titles, thumbnails or metrics are exported.
        """
        view = self.get_brief(brief_id)
        d = view.draft
        lines = [f"# {d.working_title}"]
        labels = {
            "alternate_title": "Alternate title",
            "viewer_question": "Viewer question",
            "original_angle": "Original angle",
            "first_frame": "First frame",
            "cold_open": "Cold open",
            "shot_checklist": "Shot checklist",
            "verification_plan": "Test/control or verification",
            "thumbnail_hypothesis_a": "Thumbnail hypothesis A",
            "thumbnail_hypothesis_b": "Thumbnail hypothesis B",
            "cover_design": "Cover / first-frame design",
            "payoff_beat": "Payoff beat",
            "fallback_plan": "Fallback if unverified",
            "reel_adaptation": "Reel adaptation",
            "success_measure": "Own-channel success measure",
        }
        lines.append(f"Pillar: {d.pillar} | Format: {d.format} | GTA VI status: {d.gta_vi_status}")
        for col, label in labels.items():
            value = getattr(d, col)
            lines.append(f"{label}: {value if value else 'Not yet written'}")
        for ref in view.refs:
            if ref.link:
                lines.append(f"Reference ({ref.role}): {ref.link}")
        unavailable = view.refs_no_longer_available + sum(1 for r in view.refs if not r.link)
        if unavailable:
            lines.append(f"{unavailable} source reference(s) no longer available")
        return "\n".join(lines) + "\n"
