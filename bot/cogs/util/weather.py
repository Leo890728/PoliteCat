import contextlib
import os

from datetime import datetime, timedelta, timezone
from typing import Union

import discord
import httpx

from discord.ext import tasks
from sqlmodel import select

from bot import ApplicationContext, BaseCog, Bot, Translator, cog_i18n
from bot.models import weather_model as model 
from bot.core.model import Database

_ = Translator(__name__)


@cog_i18n
class WeatherCog(BaseCog, name="Weather"):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.earthquake_report.start()
        self.database = Database
    
    @contextlib.contextmanager
    def earthquake_report_config(self, guild_id, *, ensure: bool = False) -> Union[model.EarthquakeReportGuildConfig, None]:
        with self.database(auto_commit=True) as database:
            statment = select(model.EarthquakeReportGuildConfig).where(model.EarthquakeReportGuildConfig.guild_id == guild_id)
            if (report_conf := database.session.exec(statment).first()) is None:
                report_conf = model.EarthquakeReportGuildConfig(guild_id=guild_id)
                database.session.add(report_conf)
            elif ensure:
                report_conf = model.EarthquakeReportGuildConfig(guild_id=guild_id)
            yield report_conf

    @tasks.loop(minutes=15)
    async def earthquake_report(self):
        await self.bot.wait_until_ready()
        with self.database() as database:
            get_reports_statement = select(model.EarthquakeReport).order_by(model.EarthquakeReport.earthquake_no.desc())
            last_report: model.EarthquakeReport = database.session.exec(get_reports_statement).first()

            async with httpx.AsyncClient(verify=False) as client:
                if (authorization := os.getenv("CWA_AUTHORIZATION", None)) is None:
                    return
                response = await client.get(
                    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={authorization}&limit={limit}&format=JSON&StationName={station_name}"
                    .format(
                        authorization=authorization,
                        limit=60,
                        station_name="-"
                    )              
                )
                response.raise_for_status()
                reports_data = response.json()
                push_report = []
                for report_data in reports_data["records"]["Earthquake"]:
                    report = model.EarthquakeReport(
                        earthquake_no=report_data["EarthquakeNo"],
                        report_type=report_data["ReportType"],
                        report_color=report_data["ReportColor"],
                        report_content=report_data["ReportContent"],
                        report_image_uri=report_data["ReportImageURI"],
                        report_remark=report_data["ReportRemark"],
                        web=report_data["Web"],
                        shakemap_image_uri=report_data["ShakemapImageURI"],
                        origin_time=datetime.strptime(report_data["EarthquakeInfo"]["OriginTime"], "%Y-%m-%d %H:%M:%S"),
                        source=report_data["EarthquakeInfo"]["Source"],
                        focal_depth=report_data["EarthquakeInfo"]["FocalDepth"],
                        location=report_data["EarthquakeInfo"]["Epicenter"]["Location"],
                        epicenter_latitude=report_data["EarthquakeInfo"]["Epicenter"]["EpicenterLatitude"],
                        epicenter_longitude=report_data["EarthquakeInfo"]["Epicenter"]["EpicenterLongitude"],
                        magnitude_type=report_data["EarthquakeInfo"]["EarthquakeMagnitude"]["MagnitudeType"],
                        magnitude_value=report_data["EarthquakeInfo"]["EarthquakeMagnitude"]["MagnitudeValue"],
                        reported=False
                    )
                    if last_report and last_report.origin_time >= report.origin_time:
                        continue
                    push_report.append(report)
                    for shaking_area in report_data["Intensity"]["ShakingArea"]:
                        if "最大震度" in shaking_area["AreaDesc"]:
                            shaking_area = model.EarthquakeShakingArea(
                                earthquake_no=report_data["EarthquakeNo"],
                                area_desc=shaking_area["AreaDesc"],
                                county_name=shaking_area["CountyName"],
                                area_intensity=shaking_area["AreaIntensity"]
                            )
                            database.session.add(shaking_area)
                    database.session.add(report)
                    database.session.commit()

            statement = select(model.EarthquakeReportGuildConfig)
            guilds_report_conf = database.session.exec(statement).all()

            embeds_push_queue = []
            for report in push_report[::-1]:
                embeds_push_queue.append(report.create_earthquake_report_embed())
                report.reported = True
            database.session.commit()
                        
            for guild in self.bot.guilds:
                guild_filter = filter(lambda report_conf: report_conf.guild_id == guild.id, guilds_report_conf)
                if (report_conf := next(guild_filter, None)) is not None:
                    if push_report and report_conf.push_channel_id and (channel := guild.get_channel(report_conf.push_channel_id)):
                        for embed in embeds_push_queue:
                            silent = True
                            if report.magnitude_value > report_conf.silent_threshold:
                                silent = False
                            if embed.timestamp < datetime.now(tz=timezone(offset=timedelta())) - timedelta(minutes=60):
                                silent = True
                            
                            await channel.send(embed=embed, silent=silent)
                else:
                    new_report_conf = model.EarthquakeReportGuildConfig(guild_id=guild.id, channel_id=None)
                    database.session.add(new_report_conf)
                    database.session.commit()
    
    @discord.slash_command(
        i18n_name=_("地震報告頻道"),
        i18n_description=_("設定接收地震報告的頻道"),
    )
    @discord.option(
        "channel",
        discord.TextChannel,
        name_localizations=_("頻道"),
        description_localizations=_(
            "接收報告的頻道")
    )
    async def set_report_receive_channel(self, ctx: ApplicationContext, channel: discord.TextChannel) -> None:
        with self.earthquake_report_config(ctx.guild_id, ensure=True) as report_conf:
            report_conf.push_channel_id = channel.id
        
        await ctx.response.send_message(f"> 設定地震報告頻道為 {channel.mention}")

    @discord.slash_command(
        i18n_name=_("地震通知級數"),
        i18n_description=_("設定地震通知級數"),
    )
    @discord.option(
        "threshold",
        float,
        name_localizations=_("級數"),
        description_localizations=_(
            "當大於報告級數開啟訊息通知(1.0 ~ 9.0)")
    )
    async def set_report_receive_channel(self, ctx: ApplicationContext, threshold: float) -> None:
        if 0 <= threshold <= 9.0:
            with self.earthquake_report_config(ctx.guild_id, ensure=True) as report_conf:
                report_conf.silent_threshold = threshold
        else:
            await ctx.response.send_message(f"> 不正確的數值：{threshold}")
        await ctx.response.send_message(f"> 設定地震通知級數為 {threshold}")
    

def setup(bot: Bot):
    bot.add_cog(WeatherCog(bot))