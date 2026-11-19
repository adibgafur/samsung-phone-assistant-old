"""Relational schema: phones -> specifications (long format) and prices.

`specifications` stores every scraped row as (category, key, value) so nothing
from GSMArena is lost. A few frequently-ranked values (battery, display, RAM)
are also parsed into numeric columns on `phones` for fast "best X" queries.
"""
from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Phone(Base):
    __tablename__ = "phones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(300))
    image_url: Mapped[str | None] = mapped_column(String(300))
    announced: Mapped[str | None] = mapped_column(String(120))
    battery_mah: Mapped[int | None] = mapped_column(Integer)
    display_inches: Mapped[float | None] = mapped_column(Float)
    ram_gb: Mapped[int | None] = mapped_column(Integer)  # largest RAM variant

    specs: Mapped[list["Specification"]] = relationship(
        back_populates="phone", cascade="all, delete-orphan"
    )
    prices: Mapped[list["Price"]] = relationship(
        back_populates="phone", cascade="all, delete-orphan"
    )


class Specification(Base):
    __tablename__ = "specifications"
    __table_args__ = (UniqueConstraint("phone_id", "category", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phones.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(Text)

    phone: Mapped[Phone] = relationship(back_populates="specs")


class Price(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phones.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    raw: Mapped[str | None] = mapped_column(String(200))

    phone: Mapped[Phone] = relationship(back_populates="prices")
