"""Seed concurrency-safe identity claims from historical candidate hashes."""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Candidate, CandidateIdentityClaim
from app.db.session import SessionLocal


async def run(apply: bool) -> int:
    summary = {"scanned": 0, "created": 0, "conflicts": 0, "skipped": 0}
    async with SessionLocal() as db:
        candidates = list(
            await db.scalars(
                select(Candidate)
                .where(Candidate.deleted_at.is_(None))
                .order_by(Candidate.id)
            )
        )
        existing_claims = {
            (claim.organization_id, claim.identity_type, claim.identity_hash)
            for claim in await db.scalars(select(CandidateIdentityClaim))
        }
        reserved = set(existing_claims)
        for candidate in candidates:
            summary["scanned"] += 1
            identity_type, identity_hash = (
                ("phone", candidate.phone_hash)
                if candidate.phone_hash
                else ("email", candidate.email_hash)
            )
            if identity_hash is None:
                summary["skipped"] += 1
                continue
            identity_key = (candidate.organization_id, identity_type, identity_hash)
            if identity_key in reserved:
                summary["conflicts"] += 1
                continue
            reserved.add(identity_key)
            summary["created"] += 1
            if apply:
                db.add(
                    CandidateIdentityClaim(
                        organization_id=candidate.organization_id,
                        identity_type=identity_type,
                        identity_hash=identity_hash,
                        candidate_id=candidate.id,
                    )
                )
        if apply:
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise
        else:
            await db.rollback()
    mode = "已写入" if apply else "预演"
    print(f"{mode}完成：" + "，".join(f"{key}={value}" for key, value in summary.items()))
    return 1 if summary["conflicts"] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="回填候选人并发去重占位记录")
    parser.add_argument("--apply", action="store_true", help="确认写入数据库；默认只预演")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.apply)))


if __name__ == "__main__":
    main()
