import contextlib
import os

from types import TracebackType
from typing import Any, Optional, Type, Generator, TypeVar, List

from sqlmodel import SQLModel, select, create_engine, Session as SQLModelSession
from sqlalchemy import ScalarResult

from bot.models.botConfig_model import BotConfig, TrackedDict


T = TypeVar("T", bound=SQLModel)


class Database:
    database_engine = None

    def __init__(self, auto_commit=True):
        self.auto_commit: bool = auto_commit
        self.session: Optional[SQLModelSession] = None

    @staticmethod
    def init_engine(bot):
        bot.load_extension("bot.models", recursive=True)
        engine = create_engine(os.getenv("DATABASE_URL"), echo=False)
        SQLModel.metadata.create_all(engine)
        Database.database_engine = engine

    def _get_config_context(self, filters: Optional[dict[str, str]], config_model: Type[T], first=True, ensure: bool = False, init_kwargs: Optional[dict[str, Any]] = None) -> Optional[Type[T] | List[Type[T]]]:
        statement = select(config_model).filter_by(**filters) if filters else select(config_model)

        if not self.session:
            raise RuntimeError("Session missing; please use 'with Database() as db:'.")

        result: ScalarResult = self.session.exec(statement)
        if first:
            config = result.first()
        else:
            config = result.all()

        if not config and ensure:
            new_config = config_model(**(init_kwargs or {}))
            self.session.add(new_config)
            config = new_config if first else [new_config]

        return config

    @contextlib.contextmanager
    def user_config(self, user_id: int, config_model: Type[T], ensure: bool = False, init_kwargs: Optional[dict[str, Any]] = None) -> Generator[Optional[T], None, None]:
        yield self._get_config_context(filters={"user_id": user_id}, config_model=config_model, ensure=ensure, init_kwargs={"user_id": user_id, **(init_kwargs or {})})

    @contextlib.contextmanager
    def guild_config(self, guild_id: int, config_model: Type[T], ensure: bool = False, init_kwargs: Optional[dict[str, Any]] = None) -> Generator[Optional[T], None, None]:
        yield self._get_config_context(filters={"guild_id": guild_id}, config_model=config_model, ensure=ensure, init_kwargs={"guild_id": guild_id, **(init_kwargs or {})})

    @contextlib.contextmanager
    def bot_config(self) -> Generator[dict[str, str], None, None]:

        result: Optional[List[BotConfig]] = self._get_config_context(filters=None, config_model=BotConfig, first=False)
    
        config_list = result or []
        config_dict = TrackedDict({c.key: c.value for c in config_list})

        yield config_dict

        for key in config_dict.changed_keys:
            value = config_dict[key]
            self.session.merge(BotConfig(key=key, value=value))

        for key in config_dict.deleted_keys:
            statement = select(BotConfig).where(BotConfig.key == key)
            if target := self.session.exec(statement).first():
                self.session.delete(target)

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