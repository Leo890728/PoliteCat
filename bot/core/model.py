from types import TracebackType
from typing import Any, List, Union, overload, Optional, Type

import discord

from sqlmodel import SQLModel, create_engine, Session as SQLModelSession


class Database:
    database_engine = None

    def __init__(self, auto_commit=True):
        self.auto_commit = auto_commit

    @staticmethod
    def init_engine(bot):
        bot.load_extension("bot.models", recursive=True)
        engine = create_engine("sqlite:///bot.db", echo=False)
        SQLModel.metadata.create_all(engine)
        Database.database_engine = engine
    
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