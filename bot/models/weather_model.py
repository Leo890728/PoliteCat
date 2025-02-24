from datetime import datetime
from typing import Optional, Union

import discord

from sqlmodel import Field, SQLModel, Relationship


class EarthquakeReportGuildConfig(SQLModel, table=True):
    __tablename__ = "EarthquakeReportGuildConfig"

    guild_id: int = Field(primary_key=True, sa_column_kwargs={"name": "GuildId"})
    push_channel_id: Optional[int] = Field(default=None, sa_column_kwargs={"name": "PushChannelId"})
    silent_threshold: int = Field(default=5.5, sa_column_kwargs={"name": "SilentThreshold"})
    last_reported_time: Optional[datetime] = Field(default=None, sa_column_kwargs={"name": "LastReportedTime"})


class EarthquakeReport(SQLModel, table=True):
    __tablename__ = "EarthquakeReport"

    earthquake_no: int = Field(primary_key=True, sa_column_kwargs={"name": "EarthquakeNo"})
    report_type: str = Field(sa_column_kwargs={"name": "ReportType"})
    report_color: str = Field(sa_column_kwargs={"name": "ReportColor"})
    report_content: str = Field(sa_column_kwargs={"name": "ReportContent"})
    report_image_uri: str = Field(sa_column_kwargs={"name": "ReportImageUri"})
    report_remark: str = Field(sa_column_kwargs={"name": "ReportRemark"})
    web: str = Field(sa_column_kwargs={"name": "Web"})
    shakemap_image_uri: str = Field(sa_column_kwargs={"name": "ShakemapImageUri"})
    origin_time: datetime = Field(sa_column_kwargs={"name": "OriginTime"})
    source: str = Field(sa_column_kwargs={"name": "Source"})
    focal_depth: float = Field(sa_column_kwargs={"name": "FocalDepth"})
    location: str = Field(sa_column_kwargs={"name": "Location"})
    epicenter_latitude: float = Field(sa_column_kwargs={"name": "EpicenterLatitude"})
    epicenter_longitude: float = Field(sa_column_kwargs={"name": "EpicenterLongitude"})
    magnitude_type: str = Field(sa_column_kwargs={"name": "MagnitudeType"})
    magnitude_value: float = Field(sa_column_kwargs={"name": "MagnitudeValue"})

    shaking_area: list["EarthquakeShakingArea"] = Relationship(
        cascade_delete=True,
        back_populates="earthquake_report",
    )

    reported: bool = Field(default=False, sa_column_kwargs={"name": "Reported"})

    def create_earthquake_report_embed(self) -> discord.Embed:
        # 表格最大震度顏色
        #   🟢 未達下列標準之地震。
        #   🟡 芮氏規模5.5以上，最大震度4級以上。
        #   🟠 芮氏規模6.0以上，最大震度5弱以上。
        #   🔴 芮氏規模6.5以上，最大震度6弱以上。
        color_map = {
            "綠色": discord.Colour.green(),
            "黃色": discord.Colour.yellow(),
            "橘色": discord.Colour.orange(),
            "紅色": discord.Colour.red(),
        }
        embed = discord.Embed(
            title=f"地震報告 {self.earthquake_no}",
            description=self.report_content,
            color=color_map.get(self.report_color, discord.Colour.default()),
            url=self.web
        )
        # embed.set_thumbnail(url=self.shakemap_image_uri)
        embed.set_image(url=self.report_image_uri)
        embed.add_field(name=self.magnitude_type, value=self.magnitude_value, inline=True)
        embed.add_field(name="深度", value=self.focal_depth, inline=True)
        embed.add_field(name="地點", value=f"[{self.location}](https://www.google.com/maps/search/?api=1&query={self.epicenter_latitude}%2C{self.epicenter_longitude})", inline=False)
        embed.set_footer(text=self.report_remark.removesuffix("。"))
        embed.timestamp = self.origin_time
        return embed


class EarthquakeShakingArea(SQLModel, table=True):
    __tablename__ = "EarthquakeShakingArea"

    earthquake_report: EarthquakeReport = Relationship(back_populates="shaking_area")
    earthquake_no: int = Field(primary_key=True, foreign_key='EarthquakeReport.EarthquakeNo', sa_column_kwargs={"name": "EarthquakeNo"})
    area_desc: str = Field(primary_key=True, sa_column_kwargs={"name": "AreaDesc"})
    county_name: str = Field(sa_column_kwargs={"name": "CountyName"})
    area_intensity: str = Field(sa_column_kwargs={"name": "AreaIntensity"})


def setup(bot):
    pass