from typing import Optional, Union

from sqlmodel import Field, SQLModel, Relationship


class oEmbedProvider(SQLModel, table=True):
    __tablename__ = "oEmbedProvider"

    provider_name: Optional[str] = Field(default=None, primary_key=True, sa_column_kwargs={"name": "ProviderName"})
    provider_url: Optional[str] = Field(default=None, sa_column_kwargs={"name": "ProviderUrl"})

    endpoints: list["oEmbedEndpoint"] = Relationship(back_populates="provider", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    schemas: list["oEmbedProviderSchema"] = Relationship(back_populates="provider", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    formatters: list["oEmbedProviderFormatter"] = Relationship(back_populates="provider", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class oEmbedEndpoint(SQLModel, table=True):
    __tablename__ = "oEmbedEndpoint"

    provider_name: str = Field(primary_key=True, foreign_key="oEmbedProvider.ProviderName", sa_column_kwargs={"name": "ProviderName"})
    endpoint_url: str = Field(primary_key=True, sa_column_kwargs={"name": "EndpointUrl"})
    discovery: Optional[bool] = Field(default=None, sa_column_kwargs={"name": "Discovery"})

    provider: oEmbedProvider = Relationship(back_populates="endpoints")


class oEmbedProviderSchema(SQLModel, table=True):
    __tablename__ = "oEmbedProviderSchema"

    provider_name: str = Field(primary_key=True, foreign_key="oEmbedProvider.ProviderName", sa_column_kwargs={"name": "ProviderName"})
    schema: str = Field(primary_key=True, sa_column_kwargs={"name": "Schema"})

    provider: oEmbedProvider = Relationship(back_populates="schemas")


class oEmbedProviderFormatter(SQLModel, table=True):
    __tablename__ = "oEmbedProviderFormatter"

    provider_name: str = Field(primary_key=True, foreign_key="oEmbedProvider.ProviderName", sa_column_kwargs={"name": "ProviderName"})
    formatter: str = Field(primary_key=True, sa_column_kwargs={"name": "Formatter"})

    provider: oEmbedProvider = Relationship(back_populates="formatters")


def setup(bot):
    pass