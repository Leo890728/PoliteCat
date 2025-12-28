from sqlmodel import Field, SQLModel


class BotConfig(SQLModel, extend_existing=True, table=True):
    __tablename__ = "bot_config"

    key: str = Field(primary_key=True, unique=True)
    value: str = Field(default="")

    def __hash__(self):
        return hash(self.key)
    
    def __eq__(self, other):
        if isinstance(other, Config):
            return self.key == other.key
        elif isinstance(other, str):
            return self.key == other
        return False

    def __repr__(self):
        return f"{self.key}: {self.value}"


def setup(bot):
    pass