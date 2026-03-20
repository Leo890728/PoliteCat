from sqlmodel import Field, SQLModel


class BotConfig(SQLModel, extend_existing=True, table=True):
    __tablename__ = "BotConfig"

    key: str = Field(primary_key=True, unique=True)
    value: str = Field(default="")

    def __hash__(self):
        return hash(self.key)
    
    def __eq__(self, other):
        if isinstance(other, BotConfig):
            return self.key == other.key
        elif isinstance(other, str):
            return self.key == other
        return False

    def __repr__(self):
        return f"{self.key}: {self.value}"

class TrackedDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.changed_keys = set()
        self.deleted_keys = set()

    def __setitem__(self, key, value):
        if self.get(key) != value:
            self.changed_keys.add(key)
            self.deleted_keys.discard(key)
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self.deleted_keys.add(key)
        self.changed_keys.discard(key)
        super().__delitem__(key)

    def update(self, *args, **kwargs):
        for k, v in dict(*args, **kwargs).items():
            self[k] = v

    def pop(self, *args, **kwargs):
        raise NotImplementedError("TrackedDict does not support pop(). Use 'del' instead.")

    def clear(self):
        raise NotImplementedError("TrackedDict does not support clear().")

def setup(bot):
    pass