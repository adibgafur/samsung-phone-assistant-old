"""Load scraped phones (JSON) into the database. Safe to re-run (upserts by name).

Usage:
    python -m app.ingest data/scraped_phones.json
    python -m app.ingest data/sample_phones.json      # offline demo data
"""
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import parsing
from app.db import SessionLocal, init_db
from app.models import Phone, Price, Specification


def upsert_phone(session: Session, record: dict) -> Phone:
    specs = record["specs"]
    phone = session.scalar(select(Phone).where(Phone.name == record["name"]))
    if phone is None:
        phone = Phone(name=record["name"])
        session.add(phone)
    phone.url = record.get("url")
    phone.image_url = record.get("image_url")
    phone.announced = parsing.announced(specs)
    phone.battery_mah = parsing.battery_mah(specs)
    phone.display_inches = parsing.display_inches(specs)
    phone.ram_gb = parsing.ram_gb(specs)

    phone.specs.clear()
    phone.prices.clear()
    session.flush()
    for category, rows in specs.items():
        for key, value in rows.items():
            phone.specs.append(Specification(category=category, key=key, value=value))
    p = parsing.price(specs)
    if p:
        phone.prices.append(Price(amount=p[0], currency=p[1], raw=p[2]))
    return phone


def ingest_file(path: str) -> int:
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    init_db()
    with SessionLocal() as session:
        for rec in records:
            upsert_phone(session, rec)
        session.commit()
    return len(records)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(f"Ingested {ingest_file(sys.argv[1])} phones")
