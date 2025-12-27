from typing import Optional
from sqlmodel import Field, SQLModel


class GitHubWebhookConfig(SQLModel, table=True):
    """GitHub Webhook 設定"""
    __tablename__ = "github_webhook_config"

    id: Optional[int] = Field(default=None, primary_key=True)
    guild_id: int = Field(index=True, description="Discord 伺服器 ID")
    channel_id: Optional[int] = Field(default=None, description="接收 webhook 的頻道 ID")
    repo_name: Optional[str] = Field(default=None, description="GitHub 倉庫名稱 (owner/repo)")
    enabled: bool = Field(default=True, description="是否啟用")

def setup(bot):
    pass