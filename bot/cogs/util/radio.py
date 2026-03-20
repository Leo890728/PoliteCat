import asyncio
import typing
import itertools
import math

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import discord
import httpx
import wavelink

from discord.ext import tasks
from sqlalchemy import select, delete
from sqlalchemy.orm import joinedload

from bot import ApplicationContext, Bot, BaseCog, Translator, cog_i18n
from bot.models.radio_model import RadioStation, RadioPlace
from bot.cogs.util.player import PlayerCog
from bot.core.model import Database


_ = Translator(__name__)

type CountryID = str
type ConntryName = str


@cog_i18n
@discord.guild_only()
class RadioCog(BaseCog, name="收音機"):

    def __init__(self, bot: discord.Bot):
        super().__init__(bot)
        self.update_places_data_source.start()

    @discord.Cog.listener()
    async def on_ready(self) -> None:
        self.bot.add_view(RadioView())

    @tasks.loop(hours=24)
    async def update_places_data_source(self) -> None:
        self.bot.log.info("開始更新收音機站點資料")

        api: str = "https://radio.garden/api/ara/content/places"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp: httpx.Response = await client.get(api)
            if resp.status_code == httpx.codes.OK:
                self.bot.log.info("取得收音機站點資料成功")
                data: dict[str, any] = resp.json()

                with Database(auto_commit=False) as db, db.bot_config() as config:
                    if config.get("radio_data_version") == data["version"]:
                        self.bot.log.info(f"收音機站點資料版本未更新 版本: {data['version']}")
                        return
                    
                    else:
                        self.bot.log.info(f"發現收音機站點資料更新 版本: {config.get('radio_data_version', "Unknown")} -> {data['version']}")
                        config.update({"radio_data_version": data["version"]})
                        
                        db.session.execute(delete(RadioStation))
                        db.session.execute(delete(RadioPlace))
                        db.session.commit()
                        
                        for place_data in data["data"]["list"]:
                            latitude, longitude = place_data["geo"]
                            place = RadioPlace(latitude=latitude, longitude=longitude, **place_data)
                            db.session.add(place)
            else:
                resp.raise_for_status()        
    
    @update_places_data_source.error
    async def update_places_data_source_error(self, error: Exception) -> None:
        if isinstance(error, httpx.HTTPStatusError):
            self.bot.log.exception(f"取得收音機站點資料失敗: {repr(error)}")
        else:
            self.bot.log.exception(f"更新收音機站點資料失敗: {repr(error)}")

    @update_places_data_source.before_loop
    async def before_update_places_data_source(self) -> None:
        await self.bot.wait_until_ready()
    
    @staticmethod
    async def update_place_stations(place_id: str) -> None:
        api: str = f"https://radio.garden/api/ara/content/page/{place_id}/channels"
        with Database() as db:
            stem = select(RadioPlace).where(RadioPlace.id == place_id)

            if (place := db.session.execute(stem).scalars().first()) and not place.stations:
                print(f"更新站點 {place_id} 的站點資料")
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    resp: httpx.Response = await client.get(api)
                    if resp.status_code == httpx.codes.OK:
                        print(f"取得站點 {place_id} 的站點資料成功")
                        data: dict[str, any] = resp.json()
                        for station_data in data["data"]["content"][0]["items"]:
                            station_data["page"].pop("country", None)
                            station_data["page"].pop("place", None)
                            station = RadioStation(
                                id=station_data["page"]["url"].split("/")[-1],
                                place_id=place_id,
                                country=place.country,
                                utc_offset=timedelta(minutes=data["data"]["utcOffset"]),
                                **station_data["page"]
                            )
                            place.utc_offset = timedelta(minutes=data["data"]["utcOffset"])
                            db.session.add(station)
                    else:
                        resp.raise_for_status()
                        print(f"取得站點 {place_id} 的站點資料失敗")
            else:
                print(f"站點 {place_id} 已有站點資料")
            

    async def country_autocomplete(self, ctx: discord.AutocompleteContext) -> typing.List[str]:
        with Database(auto_commit=False) as db:
            countries = db.session.execute(
                select(RadioPlace.country)
                .where(RadioPlace.country.ilike(f"%{ctx.value}%"))
                .distinct()
                .limit(25)).scalars().all()
        return [
            country
            for country in countries if ctx.value.casefold() in country.casefold()
        ]

    async def place_autocomplete(self, ctx: discord.AutocompleteContext) -> typing.List[str]:
        with Database(auto_commit=False) as db:
            places = db.session.execute(
                select(RadioPlace)
                .where(RadioPlace.country.ilike(f"%{ctx.options.get('country')}%"))
                .limit(25)).unique().scalars().all()
        return [
            place.title
            for place in places if ctx.value.casefold() in place.title.casefold()
        ]

    @discord.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player: wavelink.Player | None = payload.player
        if not player:
            return

        track: wavelink.Playable = payload.track
        if dict(track.extras).get("from_cog", None) != "RadioCog":
            return

    @discord.slash_command(
        i18n_name=_("收音機"),
        i18n_description=_("播放廣播"),
    )
    @discord.option(
        "country",
        str,
        name_localizations=_("國家"),
        description_localizations=_(
            "廣播的來源國家"),
        autocomplete=country_autocomplete
    )
    @discord.option(
        "place",
        str,
        name_localizations=_("區域"),
        description_localizations=_(
            "廣播的來源區域"),
        autocomplete=place_autocomplete
    )
    async def radio(self, ctx: ApplicationContext, country: str, place: str) -> None:
        place_id: str | None = None
        with Database(auto_commit=False) as db:
            place_id = db.session.execute(select(RadioPlace.id).where(RadioPlace.country == country, RadioPlace.title == place)).scalars().first()

        if not place_id:
            await ctx.response.send_message("> 未知的地點")
            return

        await RadioCog.update_place_stations(place_id)

        with Database(auto_commit=False) as db:
            radio_place: RadioPlace | None = db.session.execute(
                select(RadioPlace)
                .where(RadioPlace.id == place_id)
                .options(joinedload(RadioPlace.stations))
            ).unique().scalars().first()

            embed: discord.Embed = radio_place.create_embed()
            await ctx.response.send_message(embed=embed, view=RadioView(radio_place))


class RadioView(discord.ui.View):

    def __init__(self, place: Optional[RadioPlace] = None):
        super().__init__(timeout=None)
        self.place: Optional[RadioPlace] = place
        self.station: Optional[RadioStation] = None
        self._batch_index: int = 0
        self._batch_count: int = 0
        if place:
            asyncio.create_task(RadioCog.update_place_stations(place.id))
            self.reload_selector_options()

            self.batch_count = math.ceil(len(place.stations) / 25)

    @property
    def batch_index(self) -> int:
        return self._batch_index

    @batch_index.setter
    def batch_index(self, value: int):
        self._batch_index = value
        self.station_page_index_button.label = f"{value+1}/{self._batch_count}"

    @property
    def batch_count(self) -> int:
        return self._batch_count

    @batch_count.setter
    def batch_count(self, value: int):
        self._batch_count = value
        self.station_page_index_button.label = f"{self._batch_index+1}/{value}"

    @property
    def station_page_index_button(self) -> discord.ui.Button:
        return self.get_item("persistent_view:radio:station_page_index_button")

    @property
    def radio_station_selector(self) -> discord.ui.Select:
        return self.get_item("persistent_view:radio:radio_station_selector")

    @property
    def pause_resume_button(self) -> discord.ui.Button:
        return self.get_item("persistent_view:radio:pause_resume_button")

    def load_from_message(self, ctx: discord.Interaction):
        view: discord.ui.View = self.from_message(ctx.message)
        embed: discord.Embed = ctx.message.embeds[0]
        place: RadioPlace = None

        station_selector: discord.ui.Select = view.get_item(
            "persistent_view:radio:radio_station_selector")
        station_page_index_button: discord.ui.Button = view.get_item(
            "persistent_view:radio:station_page_index_button")

        country_name: str
        place_name: str
        station_name: Optional[str]
        if (selected_values := (station_selector.values or self.radio_station_selector.values)):
            country_name, place_name, station_name = selected_values[0].split(":")
        else:
            country_name: str = embed.fields[0].value
            place_name: str = embed.fields[1].value
            station_name: Optional[str] = None

        with Database(auto_commit=False) as db:
            place = db.session.execute(select(RadioPlace).where(RadioPlace.country == country_name, RadioPlace.title == place_name)).unique().scalars().first()
            station = db.session.execute(select(RadioStation).where(RadioStation.title == station_name)).scalars().first()

        self.place = place
        self.station = station
        batch_index, batch_count = map(int, station_page_index_button.label.split("/"))
        self.batch_index, self.batch_count = batch_index - 1, batch_count

        self.reload_selector_options()

    def reload_selector_options(self):
        options = []
        asyncio.create_task(RadioCog.update_place_stations(self.place.id))
        batched_stations = list(itertools.batched(self.place.stations, 25))
        for station in batched_stations[self.batch_index]:
            options.append(
                discord.SelectOption(
                    default=(station == self.station),
                    label=station.title,
                    value="{country}:{place}:{title}".format(
                        country=station.country, place=self.place.title, title=station.title),
                )
            )
        self.radio_station_selector.options = options

    @discord.ui.button(label="⏯️", style=discord.ButtonStyle.secondary, row=0, custom_id="persistent_view:radio:pause_resume_button")
    async def pause_resume_button_callback(self, button: discord.Button, ctx: discord.Interaction):
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)

        if player and (current := player.current):

            if dict(current.extras).get("from_cog", None) == "RadioCog":
                
                self.load_from_message(ctx)
                await player.pause(not player.paused)
                button.label = ("⏸️", "▶️")[player.paused]

            await ctx.response.edit_message(view=self)

    @discord.ui.button(label="🔉", style=discord.ButtonStyle.secondary, row=0, custom_id="persistent_view:radio:volume_down_button")
    async def volume_down_button_callback(self, button: discord.Button, ctx: discord.Interaction):
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)

        if player and (current := player.current):

            if dict(current.extras).get("from_cog", None) == "RadioCog":
                
                self.load_from_message(ctx)
                await player.set_volume(max(0, player.volume - 10))

            await ctx.response.edit_message(view=self)

    @discord.ui.button(label="🔊", style=discord.ButtonStyle.secondary, row=0, custom_id="persistent_view:radio:volume_up_button")
    async def volume_up_button_callback(self, button: discord.Button, ctx: discord.Interaction):
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)

        if player and (current := player.current):

            if dict(current.extras).get("from_cog", None) == "RadioCog":

                self.load_from_message(ctx)
                await player.set_volume(min(100, player.volume + 10))

            await ctx.response.edit_message(view=self)

    @discord.ui.button(label="🔄️", style=discord.ButtonStyle.secondary, row=0, custom_id="persistent_view:radio:refresh_radio_button")
    async def refresh_radio_button_callback(self, button, ctx: discord.Interaction):
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)

        embed: discord.Embed = ctx.message.embeds[0]
        if player and (current := player.current):
            if dict(current.extras).get("from_cog", None) == "RadioCog":
                with Database(auto_commit=False) as db:
                    place = db.session.execute(select(RadioPlace).where(RadioPlace.country == current.extras.country, RadioPlace.title == current.extras.place)).unique().scalars().first()
                    station = db.session.execute(select(RadioStation).where(RadioStation.title == current.extras.station)).scalars().first()
                self.place = place
                self.station = station
                self.batch_count = math.ceil(len(place.stations) / 25)
                self.batch_index = math.floor(
                    place.stations.index(self.station) / 25)
                self.reload_selector_options()
                embed = self.station.create_embed()

            await ctx.response.edit_message(view=self, embed=embed)
        else:
            country_name: str = embed.fields[0].value
            place_name: str = embed.fields[1].value

            with Database(auto_commit=False) as db:
                place = db.session.execute(select(RadioPlace).where(RadioPlace.country == country_name, RadioPlace.title == place_name)).unique().scalars().first()
                # stations retrieval line removed as 'station_name' is undefined and result unused
            self.place = place
            self.station = None
            embed: discord.Embed = self.place.create_embed()
            self.batch_count = math.ceil(len(self.place.stations) / 25)
            self.batch_index = 0
            self.reload_selector_options()
            await ctx.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.blurple, row=2, custom_id="persistent_view:radio:prev_station_page_button")
    async def prev_station_page_button_callback(self, button, ctx: discord.Interaction):
        self.load_from_message(ctx)

        self.batch_index = (self.batch_index - 1) % (self.batch_count)

        self.reload_selector_options()

        await ctx.response.edit_message(view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, disabled=True, row=2, custom_id="persistent_view:radio:station_page_index_button")
    async def station_page_index_button_callback(self, button, ctx: discord.Interaction):
        pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary, row=2, custom_id="persistent_view:radio:next_station_page_button")
    async def next_station_page_button_callback(self, button, ctx: discord.Interaction):
        self.load_from_message(ctx)

        self.batch_index = (self.batch_index + 1) % (self.batch_count)

        self.reload_selector_options()

        await ctx.response.edit_message(view=self)

    @discord.ui.select(custom_id="persistent_view:radio:radio_station_selector", row=1, min_values=1, max_values=1, placeholder="廣播站點")
    async def radio_station_selector_callback(self, select: discord.ui.Select, ctx: discord.Interaction):
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx, ensure=True)

        if not player:
            return

        await ctx.response.defer()

        self.load_from_message(ctx)

        if self.place:
            station: RadioStation = next(filter(lambda s: s.title==select.values[0].split(":")[-1], self.place.stations), None)

            if station:
                url = station.url

                tracks: wavelink.Search = await wavelink.Playable.search(f"https://radio.garden/api/ara/content/listen/{station.id}/channel.mp3")

                track: wavelink.Playable = tracks[0]
                track._title = station.title
                track.extras = {"from_cog": "RadioCog", "station": station.title,
                                "place": self.place.title, "country": self.place.country}

                player.autoplay = wavelink.AutoPlayMode.enabled
                await player.queue.put_wait(track)
                if player.playing:
                    await player.skip(force=True)
                else:
                    await player.play(await player.queue.get_wait(), replace=True, volume=30)

                embed = ctx.message.embeds[0]
                embed = station.create_embed()

                await ctx.followup.edit_message(message_id=ctx.message.id, embed=embed, view=self)
                return

        await ctx.followup.send("> 未知的站點")


def setup(bot: "Bot"):
    bot.add_cog(RadioCog(bot))
