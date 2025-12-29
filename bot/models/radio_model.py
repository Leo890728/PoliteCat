import datetime
import os

from datetime import timedelta
from typing import Optional

import discord

from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy.orm import relationship, Mapped


class RadioPlace(SQLModel, table=True):
    __tablename__ = "RadioPlace"

    id: str = Field(primary_key=True)
    size: int = Field(default=None)
    latitude: float = Field(default=None)
    longitude: float = Field(default=None)
    url: str = Field(default=None)
    boost: bool = Field(default=None)
    title: str = Field(default=None)
    country: str = Field(default="")
    utc_offset: timedelta = Field(default=timedelta(hours=0))

    stations: Mapped[list["RadioStation"]] = Relationship(
        cascade_delete=True,
        sa_relationship=relationship(lazy='joined', back_populates="place")
    )

    def create_embed(self) -> discord.Embed:
        utc_now: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
        place_local_time: datetime.datetime = utc_now + self.utc_offset

        map_style: str = "toner-grey" if place_local_time.hour in range(
            6, 19) else "dark-matter-brown"

        embed: discord.Embed = discord.Embed()
        embed.set_author(
            name="選擇站點",
            icon_url="https://radio.garden/icons/favicon.png"
        )
        embed.set_footer(text="Powered by RadioGarden")
        embed.timestamp = datetime.datetime.now()

        embed.set_image(
            url="https://maps.geoapify.com/v1/staticmap?style={2}&width=600&height=400&center=lonlat:{0},{1}&zoom=10&apiKey={3}".format(self.latitude, self.longitude, map_style, os.getenv("GEOAPIFY_API_KEY")))

        embed.add_field(name="國家", value=self.country)
        embed.add_field(name="區域", value=self.title)
        embed.add_field(
            name="當地時間", value=f"{place_local_time.strftime('%Y-%m-%d %H:%M:%S')} (UTC {int(self.utc_offset.seconds/3600):+})")
        return embed


class RadioStation(SQLModel, table=True):
    __tablename__ = "RadioStation"

    id: str = Field(primary_key=True)
    url: str = Field(default=None)
    place_id: str = Field(foreign_key="RadioPlace.id")
    type: str = Field(default=None)
    title: str = Field(default=None)
    secure: bool = Field(default=None)
    country: str = Field(default="")
    stream: Optional[str] = Field(default=None)
    utc_offset: timedelta = Field(default=timedelta(hours=0))

    place: "RadioPlace" = Relationship(back_populates="stations")

    def create_embed(self) -> discord.Embed:
        embed: discord.Embed = self.place.create_embed()
        embed.set_author(
            name=self.title,
            url="https://radio.garden" + self.url,
            icon_url="https://radio.garden/icons/favicon.png"
        )
        return embed
    

def setup(bot):
    pass