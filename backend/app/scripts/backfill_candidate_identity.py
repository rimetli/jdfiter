"""Backfill candidate contact hashes from existing PDF files.

Run without --apply first. The command never overwrites populated candidate data and
skips rows that would collide with an existing active candidate.
"""

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select

from app.api.resumes import _extract_identity, _extract_text_from_pdf, _hash, _normalize_phone
from app.core.config import get_settings
from app.db.models import Candidate, ResumeFile
from app.db.session import SessionLocal


async def _latest_resume(db, candidate_id: int) -> ResumeFile | None:
    return await db.scalar(
        select(ResumeFile)
        .where(ResumeFile.candidate_id == candidate_id, ResumeFile.deleted_at.is_(None))
        .order_by(ResumeFile.created_at.desc(), ResumeFile.id.desc())
        .limit(1)
    )


async def run(apply: bool) -> int:
    settings = get_settings()
    summary = {"scanned": 0, "updated": 0, "skipped": 0, "conflicts": 0, "failed": 0}
    async with SessionLocal() as db:
        candidates = list(
            await db.scalars(select(Candidate).where(Candidate.deleted_at.is_(None)))
        )
        # Keep an in-memory reservation map as well as checking the database.
        # This makes a dry run match an --apply run when multiple historical rows
        # contain the same contact value but none has a hash yet.
        reserved_contacts: dict[tuple[int, str, str], int] = {}
        for row in candidates:
            if row.phone_hash:
                reserved_contacts[(row.organization_id, "phone", row.phone_hash)] = row.id
            if row.email_hash:
                reserved_contacts[(row.organization_id, "email", row.email_hash)] = row.id
        for candidate in candidates:
            if candidate.name_hash and (candidate.phone_hash or candidate.email_hash):
                continue
            summary["scanned"] += 1
            resume = await _latest_resume(db, candidate.id)
            if resume is None:
                summary["skipped"] += 1
                continue
            path = Path(settings.local_storage_path).resolve() / resume.storage_key
            try:
                text = _extract_text_from_pdf(path.read_bytes())
                parsed_name, parsed_email, parsed_phone = _extract_identity(text, resume.original_filename)
            except Exception:  # noqa: BLE001 - report aggregate only; do not leak resume data
                summary["failed"] += 1
                continue

            name = candidate.name_ciphertext or parsed_name
            email = candidate.email_ciphertext or parsed_email
            phone = _normalize_phone(candidate.phone_ciphertext) or parsed_phone
            name_hash = _hash(name)
            email_hash = _hash(email)
            phone_hash = _hash(phone)
            if name_hash is None or (phone_hash is None and email_hash is None):
                summary["skipped"] += 1
                continue

            contact_type, contact_hash = (
                ("phone", phone_hash) if phone_hash else ("email", email_hash)
            )
            contact_key = (candidate.organization_id, contact_type, contact_hash)
            owner_id = reserved_contacts.get(contact_key)
            if owner_id is not None and owner_id != candidate.id:
                summary["conflicts"] += 1
                continue
            reserved_contacts[contact_key] = candidate.id

            summary["updated"] += 1
            if apply:
                candidate.name_ciphertext = name
                candidate.name_hash = name_hash
                candidate.email_ciphertext = email
                candidate.email_hash = email_hash
                candidate.phone_ciphertext = phone
                candidate.phone_hash = phone_hash

        if apply:
            await db.commit()
        else:
            await db.rollback()

    mode = "已写入" if apply else "预演"
    print(f"{mode}完成：" + "，".join(f"{key}={value}" for key, value in summary.items()))
    return 1 if summary["failed"] or summary["conflicts"] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="回填历史候选人身份及去重哈希")
    parser.add_argument("--apply", action="store_true", help="确认写入数据库；默认只预演")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.apply)))


if __name__ == "__main__":
    main()
