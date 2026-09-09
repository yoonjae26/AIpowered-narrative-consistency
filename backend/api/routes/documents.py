from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.scene_repository import SceneRepository

router = APIRouter(prefix="/documents", tags=["documents"])

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = _ROOT / "data" / "documents"
FILES_DIR = DATA_DIR / "files"
REGISTRY = DATA_DIR / "registry.json"
SOURCE_TXT = _ROOT / "honggildongjeon.txt"

DATA_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)


def _registry() -> list[dict]:
    if not REGISTRY.exists():
        return []
    try:
        return json.loads(REGISTRY.read_text("utf-8"))
    except Exception:
        return []


def _save(docs: list[dict]) -> None:
    REGISTRY.write_text(json.dumps(docs, ensure_ascii=False, indent=2), "utf-8")


def _size_label(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 ** 2:
        return f"{n/1024:.0f}KB"
    return f"{n/1024**2:.1f}MB"


def _time_label(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        now = datetime.now(UTC) if dt.tzinfo else datetime.now()
        mins = int((now - dt).total_seconds() / 60)
        if mins < 1:
            return "방금 전"
        if mins < 60:
            return f"{mins}분 전"
        if mins < 1440:
            return f"{mins//60}시간 전"
        return f"{mins//1440}일 전"
    except Exception:
        return "최근"


def _auto_char_doc(chars: list) -> dict:
    return {
        "id": "auto_characters_db",
        "name": "등장인물 설정",
        "category": "캐릭터",
        "size_label": f"{len(chars)}명",
        "time_label": "실시간",
        "selected": True,
        "source": "characters_db",
    }


def _auto_scene_doc(scenes: list) -> dict:
    return {
        "id": "auto_scenes_db",
        "name": "홍길동전 원고",
        "category": "원고",
        "size_label": f"{len(scenes)}장면",
        "time_label": "실시간",
        "selected": True,
        "source": "scenes_db",
    }


def _auto_source_doc() -> dict | None:
    if not SOURCE_TXT.exists():
        return None
    lines = SOURCE_TXT.read_text("utf-8", errors="replace").splitlines()
    return {
        "id": "auto_source_text",
        "name": "홍길동전 원문",
        "category": "기준문서",
        "size_label": f"{len(lines)}줄",
        "time_label": "원본",
        "selected": False,
        "source": "source_file",
    }


@router.get("")
def list_documents(db: Session = Depends(get_db)) -> list[dict]:
    reg = _registry()
    chars = CharacterRepository(db, commit_on_write=False).list()
    scenes = SceneRepository(db, commit_on_write=False).list()
    result: list[dict] = []
    if chars:
        result.append(_auto_char_doc(chars))
    if scenes:
        result.append(_auto_scene_doc(scenes))
    src = _auto_source_doc()
    if src:
        result.append(src)
    _auto_ids = {"auto_characters_db", "auto_scenes_db", "auto_source_text"}
    result.extend(d for d in reg if d.get("id") not in _auto_ids)
    return result


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(default="메모"),
) -> dict:
    raw = await file.read()
    doc_id = str(uuid.uuid4())[:8]
    safe = (file.filename or "document.txt").replace("/", "_")
    stored = f"{doc_id}_{safe}"
    (FILES_DIR / stored).write_bytes(raw)

    now = datetime.now(UTC).isoformat()
    record: dict = {
        "id": doc_id,
        "name": safe,
        "category": category,
        "size_label": _size_label(len(raw)),
        "time_label": "방금 전",
        "selected": True,
        "source": "upload",
        "file_path": stored,
        "created_at": now,
    }
    reg = _registry()
    reg.insert(0, record)
    _save(reg)
    return record


@router.get("/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db)) -> dict:
    if doc_id == "auto_scenes_db":
        scenes = SceneRepository(db, commit_on_write=False).list()
        sections = []
        for i, s in enumerate(scenes):
            fields: list[dict] = [
                {"label": "등장인물", "value": ", ".join(s.characters) if s.characters else "—"},
            ]
            if s.summary:
                fields.append({"label": "요약", "value": s.summary, "highlight": True})
            for j, beat in enumerate(s.beats or []):
                fields.append({"label": f"비트 {j + 1}", "value": beat})
            sections.append({"title": f"{i + 1}. {s.title}", "fields": fields})
        return {"id": doc_id, "name": "홍길동전 원고", "category": "원고",
                "sections": sections, "total_sections": len(sections)}

    if doc_id == "auto_source_text":
        text = SOURCE_TXT.read_text("utf-8", errors="replace") if SOURCE_TXT.exists() else ""
        sections = []
        for i, chunk in enumerate(p.strip() for p in text.split("\n\n") if p.strip()):
            head = chunk.split("\n")[0]
            sections.append({"title": head[:80], "content": chunk, "highlight": i % 3 == 1})
        return {"id": doc_id, "name": "홍길동전 원문", "category": "기준문서",
                "sections": sections, "total_sections": len(sections)}

    if doc_id == "auto_characters_db":
        chars = CharacterRepository(db, commit_on_write=False).list()
        sections = []
        for c in chars:
            pbkd = getattr(c, "pbkd", None)
            role_v = c.role.value if hasattr(c.role, "value") else str(c.role)
            status_v = c.status.value if hasattr(c.status, "value") else str(c.status)
            fields = [
                {"label": "이름", "value": c.name},
                {"label": "역할", "value": role_v},
                {"label": "상태", "value": status_v},
            ]
            if c.background:
                fields.append({"label": "배경", "value": c.background, "highlight": True})
            if pbkd:
                if pbkd.personality:
                    fields.append({"label": "성격 (P)", "value": "·".join(pbkd.personality[:3])})
                if pbkd.beliefs:
                    fields.append({"label": "신념 (B)", "value": "·".join(pbkd.beliefs[:2]), "highlight": True})
                if pbkd.desires:
                    fields.append({"label": "목표 (D)", "value": "·".join(pbkd.desires[:2])})
            sections.append({"title": f"{c.name}", "fields": fields})
        return {"id": doc_id, "name": "등장인물 설정", "category": "캐릭터",
                "sections": sections, "total_sections": len(sections)}

    reg = _registry()
    rec = next((d for d in reg if d["id"] == doc_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found")

    sections: list[dict] = []
    if rec.get("source") == "upload" and rec.get("file_path"):
        fp = FILES_DIR / rec["file_path"]
        if fp.exists():
            text = fp.read_text("utf-8", errors="replace")
            for i, chunk in enumerate(p.strip() for p in text.split("\n\n") if p.strip()):
                head = chunk.split("\n")[0]
                sections.append({"title": head[:80], "content": chunk, "highlight": i % 3 == 1})

    return {**rec, "sections": sections, "total_sections": len(sections)}


@router.delete("/{doc_id}")
def delete_document(doc_id: str) -> dict:
    reg = _registry()
    rec = next((d for d in reg if d["id"] == doc_id), None)
    if rec and rec.get("source") == "upload" and rec.get("file_path"):
        fp = FILES_DIR / rec["file_path"]
        if fp.exists():
            fp.unlink()
    _save([d for d in reg if d["id"] != doc_id])
    return {"ok": True}


@router.patch("/{doc_id}/select")
def toggle_select(doc_id: str, selected: bool = True) -> dict:
    reg = _registry()
    for d in reg:
        if d["id"] == doc_id:
            d["selected"] = selected
            break
    _save(reg)
    return {"ok": True}


@router.patch("/{doc_id}/category")
def update_category(doc_id: str, category: str) -> dict:
    reg = _registry()
    for d in reg:
        if d["id"] == doc_id:
            d["category"] = category
            break
    _save(reg)
    return {"ok": True}
