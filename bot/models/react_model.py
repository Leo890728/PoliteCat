from __future__ import annotations
from enum import Enum

from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy.orm import Mapped, relationship


class KeywordsType(Enum):
    PLAIN = "純文字"
    REGEX = "正規表示式"
    STICKER = "Discord貼圖"


class KeywordsMatch(Enum):
    FULL_MATCH = "完全符合"
    MATCH = "符合"


class ReactType(Enum):
    TEXT = "文字反應"
    VOICE = "語音反應"
    STICKER = "貼圖反應"


class ReactGuildConfig(SQLModel, table=True):
    __tablename__ = "ReactGuildConfig"

    guild_id: int = Field(primary_key=True, sa_column_kwargs={"name": "GuildId"})
    enable_text_react: bool = Field(default=True, sa_column_kwargs={"name": "EnableTextReact"})
    enable_voice_react: bool = Field(default=False, sa_column_kwargs={"name": "EnableVoiceReact"})
    enable_sticker_react: bool = Field(default=False, sa_column_kwargs={"name": "EnableStickerReact"})

    reacts: Mapped[list["GuildReact"]] = Relationship(
        cascade_delete=True,
        sa_relationship=relationship(back_populates="guild_config")
    )


class GuildReact(SQLModel, table=True):
    __tablename__ = "GuildReact"

    guild_id: int = Field(primary_key=True, foreign_key="ReactGuildConfig.GuildId", sa_column_kwargs={"name": "GuildId"})
    keywords_type: KeywordsType = Field(sa_column_kwargs={"name": "KeywordsType"})
    keywords_match: KeywordsMatch = Field(sa_column_kwargs={"name": "KeywordsMatch"})
    keywords: str = Field(primary_key=True, sa_column_kwargs={"name": "Keywords"})
    react_type: ReactType = Field(sa_column_kwargs={"name": "ReactType"})
    react: str = Field(sa_column_kwargs={"name": "React"})

    guild_config: ReactGuildConfig = Relationship(back_populates="reacts")

def setup(bot):
    pass