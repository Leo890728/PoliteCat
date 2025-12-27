from datetime import datetime
from typing import Optional, Union

import discord

from sqlmodel import Field, SQLModel, Relationship


class Drawbox(SQLModel, table=True):
    __tablename__ = "Drawbox"

    guild_id: int = Field(primary_key=True, sa_column_kwargs={"name": "GuildId"})
    box_name: str = Field(primary_key=True, sa_column_kwargs={"name": "BoxName"})
    creator_id: int = Field(sa_column_kwargs={"name": "CreatorId"})
    is_private: bool = Field(default=True, sa_column_kwargs={"name": "IsPrivate"})


class DrawboxItem(SQLModel, table=True):
    __tablename__ = "DrawboxItem"

    guild_id: int = Field(foreign_key="Drawbox.GuildId", sa_column_kwargs={"name": "GuildId"})
    box_name: str = Field(foreign_key="Drawbox.BoxName", sa_column_kwargs={"name": "BoxName"})
    value: str = Field(primary_key=True, sa_column_kwargs={"name": "Value"})


def setup(bot):
    pass