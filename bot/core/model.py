import contextlib
import os

from types import TracebackType
from typing import Any, Optional, Type, Generator, TypeVar

from sqlmodel import SQLModel, select, create_engine, Session as SQLModelSession

T = TypeVar("T", bound=SQLModel)


class Database:
    database_engine = None

    def __init__(self, auto_commit=True):
        self.auto_commit = auto_commit

    @staticmethod
    def init_engine(bot):
        bot.load_extension("bot.models", recursive=True)
        engine = create_engine(os.getenv("DATABASE_URL"), echo=False)
        SQLModel.metadata.create_all(engine)
        Database.database_engine = engine

    @contextlib.contextmanager
    def guild_config(self, guild_id: int, config_model: Type[T], ensure: bool = False, init_kwargs: Optional[dict[str, Any]] = None) -> Generator[T, None, None]:
        session = self.session or SQLModelSession(Database.database_engine)
        statement = select(config_model).where(config_model.guild_id == guild_id)

        if (config := session.exec(statement).first()) is None and ensure:
            config = config_model(guild_id=guild_id, **(init_kwargs or {}))
            session.add(config)

        yield config

        if self.auto_commit:
            session.commit()

    
    def __enter__(self):
        self.session = SQLModelSession(Database.database_engine)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[TracebackType]) -> bool:
        try: 
            if self.auto_commit:
                self.session.commit()
        except Exception as e:
            print("Error while committing transaction: ", e)
            self.session.rollback()
        finally:
            self.session.close()

        if exc_type or exc_value or traceback:
            return False

def setup(bot):
    Database.init_engine(bot)