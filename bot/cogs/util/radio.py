import datetime
import typing
import json
import itertools
import math

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Union

import discord
import httpx
import wavelink

from bot import ApplicationContext, Bot, BaseCog, Translator, cog_i18n
from bot.cogs.util.player import PlayerCog

_ = Translator(__name__)

type CountryID = str
type ConntryName = str


@dataclass
class Place:
    """
    Place class represents a geographical location with radio stations.
    Attributes:
        size (int): The size of the place.
        id (str): The unique identifier of the place.
        geo (Tuple[float, float]): The geographical coordinates of the place.
        url (str): The URL associated with the place.
        boost (bool): A flag indicating if the place has a boost.
        title (str): The title of the place.
        country (str): The country where the place is located.
        stations (Optional[List["RadioStation"]]): A list of radio stations in the place.
        utc_offset (datetime.timedelta): The UTC offset of the place.
    Methods:
        from_raw_data(cls, data: dict[str, any]) -> "Place":
            Creates a Place instance from raw data.
        async get_stations() -> Optional[List["RadioStation"]]:
            Retrieves the list of radio stations for the place.
        async find_station(**keyword) -> Optional["RadioStation"]:
            Finds a radio station in the place based on keyword arguments.
    """
    size: int
    id: str
    geo: Tuple[float, float]
    url: str
    boost: bool
    title: str
    country: str
    stations: Optional[List["RadioStation"]] = None
    utc_offset: datetime.timedelta = None

    @classmethod
    def from_raw_data(cls, data: dict[str, any]) -> "Place":
        return cls(
            size=data["size"],
            id=data["id"],
            geo=tuple(data["geo"]),
            url=data["url"],
            boost=data["boost"],
            title=data["title"],
            country=data["country"]
        )

    def get_stations(self):
        if self.stations:
            return self.stations
        else:
            api: str = f"https://radio.garden/api/ara/content/page/{self.id}/channels"
            with httpx.Client() as client:
                resp: httpx.Response = client.get(api)
            if resp.status_code == httpx.codes.OK:
                data: dict[str, any] = resp.json()
                self.stations = RadioStation.from_raw_data(data, self)
                return self.stations
            else:
                resp.raise_for_status()

    def find_station(self, **keyword) -> Optional["RadioStation"]:
        for station in self.get_stations():
            if all(getattr(station, key) == value for key, value in keyword.items()):
                return station

    def create_embed(self) -> discord.Embed:
        utc_now: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
        if self.utc_offset == None:
            self.get_stations()
        place_local_time: datetime.datetime = utc_now + self.utc_offset

        map_style: str = "toner-grey" if place_local_time.hour in range(
            6, 19) else "dark-matter-brown"

        embed: discord.Embed = discord.Embed()
        embed.set_author(
            name="選擇站點",
            icon_url="https://radio.garden/icons/favicon.png"
        )
        embed.set_footer(text="Powered by RadioGarden")
        embed.timestamp = datetime.datetime.now()

        embed.set_image(
            url="https://maps.geoapify.com/v1/staticmap?style={2}&width=600&height=400&center=lonlat:{0},{1}&zoom=10&apiKey=c891120c903649f5966a3719fcffb3aa".format(*self.geo, map_style))

        embed.add_field(name="國家", value=self.country)
        embed.add_field(name="區域", value=self.title)
        embed.add_field(
            name="當地時間", value=f"{place_local_time.strftime('%Y-%m-%d %H:%M:%S')} (UTC {int(self.utc_offset.seconds/3600):+})")
        return embed


@dataclass
class RadioStation:
    url: str
    id: str
    type: str
    place: "Place"
    title: str
    secure: bool
    country: Dict[str, Union[CountryID, ConntryName]]
    stream: Optional[str]
    utc_offset: datetime.timedelta

    @classmethod
    def from_raw_data(cls, data: dict[str, any], place: Place) -> List["RadioStation"]:
        place.utc_offset = datetime.timedelta(
            minutes=data["data"]["utcOffset"]) if not place.utc_offset else place.utc_offset
        return list(
            cls(
                url=station_data["page"]["url"],
                id=(url := station_data["page"]["url"])[url.rfind("/") + 1:],
                type=station_data["page"]["type"],
                place=place,
                title=station_data["page"]["title"],
                secure=station_data["page"]["secure"],
                country=station_data["page"]["country"],
                stream=station_data["page"].get("stream", None),
                utc_offset=place.utc_offset,
            ) for station_data in data["data"]["content"][0]["items"]
        )

    def create_embed(self) -> discord.Embed:
        embed: discord.Embed = self.place.create_embed()
        embed.set_author(
            name=self.title,
            url="https://radio.garden" + self.url,
            icon_url="https://radio.garden/icons/favicon.png"
        )
        return embed


class RadioData:
    place_data: dict[str, dict] = {}

    @staticmethod
    async def load_places_data():
        # api: str = "https://radio.garden/api/ara/content/places"
        # async with httpx.AsyncClient() as client:
        #     resp: httpx.Response = await client.get(api)
        # if resp.status_code == httpx.codes.OK:
        #     data: dict[str, any] = resp.json()

        #     for country, places in itertools.groupby(data["data"]["list"], lambda d: d["country"]):
        #         RadioData.place_data.setdefault(country, []).extend(
        #             list(map(Place.from_raw_data, places)))

        # else:
        #     resp.raise_for_status()
        with open(r"places.json", "r", encoding="utf-8") as f:
            data: dict[str, any] = json.load(f)
            for country, places in itertools.groupby(data["data"]["list"], lambda d: d["country"]):
                RadioData.place_data.setdefault(country, []).extend(
                    list(map(Place.from_raw_data, places)))

    @staticmethod
    def get_countries() -> List[str]:
        return list(RadioData.place_data.keys())

    @staticmethod
    def get_country_places(country_name) -> List[Place]:
        return RadioData.place_data.get(country_name, [])

    @staticmethod
    def get_place(country_name: str, place_name: str) -> Optional[Place]:
        return next(filter(lambda place: place.title == place_name, RadioData.get_country_places(country_name)), None)


@cog_i18n
@discord.guild_only()
class RadioCog(BaseCog, name="Radio"):

    def __init__(self, bot: discord.Bot):
        super().__init__(bot)
        bot.loop.create_task(RadioData.load_places_data())

    @discord.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(RadioView())

    async def country_autocomplete(self, ctx: discord.AutocompleteContext) -> typing.List[str]:
        return [
            country
            for country in RadioData.get_countries() if ctx.value.casefold() in country.casefold()
        ][:25]

    async def place_autocomplete(self, ctx: discord.AutocompleteContext) -> typing.List[str]:
        return [
            place.title
            for place in RadioData.get_country_places(ctx.options.get("country")) if ctx.value.casefold() in place.title.casefold()
        ][:25]

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
        place_: Place = RadioData.get_place(country, place)
        if place_:
            embed: discord.Embed = place_.create_embed()
            await ctx.response.send_message(embed=embed, view=RadioView(place_))
        else:
            await ctx.response.send_message("> 未知的地點")


class RadioView(discord.ui.View):

    def __init__(self, place: Optional[Place] = None):
        super().__init__(timeout=None)
        self.place: Optional[Place] = place
        self.station: Optional[RadioStation] = None
        self._batch_index: int = 0
        self._batch_count: int = 0
        if place:
            self.reload_selector_options()
            self.batch_count = math.ceil(len(place.get_stations()) / 25)

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
        place: Place = None

        station_selector: discord.ui.Select = view.get_item(
            "persistent_view:radio:radio_station_selector")
        station_page_index_button: discord.ui.Button = view.get_item(
            "persistent_view:radio:station_page_index_button")

        country_name: str
        place_name: str
        station_name: Optional[str]
        if (selected_values := (station_selector.values or self.radio_station_selector.values)):
            country_name, place_name, station_name = selected_values[0].split(
                ":")
        else:
            country_name: str = embed.fields[0].value
            place_name: str = embed.fields[1].value
            station_name: Optional[str] = None

        place = RadioData.get_place(country_name, place_name)

        self.place = place
        self.station = place.find_station(title=station_name)
        batch_index, batch_count = map(int, station_page_index_button.label.split("/"))
        self.batch_index, self.batch_count = batch_index - 1, batch_count

        self.reload_selector_options()

    def reload_selector_options(self):
        options = []
        batched_stations = list(itertools.batched(self.place.get_stations(), 25))
        for station in batched_stations[self.batch_index]:
            options.append(
                discord.SelectOption(
                    default=(station == self.station),
                    label=station.title,
                    value="{country}:{place}:{title}".format(
                        country=station.country["title"], place=station.place.title, title=station.title),
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

    @discord.ui.button(label="🔄️", style=discord.ButtonStyle.secondary, row=0, custom_id="persistent_view:radio:refresh_radio_button")
    async def refresh_radio_button_callback(self, button, ctx: discord.Interaction):
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)

        embed: discord.Embed = ctx.message.embeds[0]
        if player and (current := player.current):
            if dict(current.extras).get("from_cog", None) == "RadioCog":
                place: Place = RadioData.get_place(
                    current.extras.country, current.extras.place)
                self.place = place
                self.station = place.find_station(title=current.extras.station)
                self.batch_count = math.ceil(len(place.get_stations()) / 25)
                self.batch_index = math.floor(
                    place.stations.index(self.station) / 25)
                self.reload_selector_options()
                embed = self.station.create_embed()

            await ctx.response.edit_message(view=self, embed=embed)
        else:
            country_name: str = embed.fields[0].value
            place_name: str = embed.fields[1].value

            self.place = RadioData.get_place(country_name, place_name)
            self.station = None
            embed: discord.Embed = self.place.create_embed()
            self.batch_count = math.ceil(len(self.place.get_stations()) / 25)
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
            station: RadioStation = self.place.find_station(
                title=select.values[0].split(":")[-1])

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


# class RadioStationSelector(discord.ui.Select):
#     def __init__(self, place: Optional[Place] = None):
#         self._place: Optional[Place] = place
#         self._batch_index: Optional[int] = None
#         self._batch_count: Optional[int] = None
#         super().__init__(
#             row=1,
#             min_values=1,
#             max_values=1,
#             placeholder="廣播站點",
#             custom_id="persistent_view:radio:radio_station_selector",
#             options=self.get_options(place)
#         )


#     @property
#     def place(self) -> Place:
#         return self._place

#     @place.setter
#     def place(self, value: Place):
#         self._place = value
#         self._batch_index = 0
#         self._batch_count = len(list(itertools.batched(value.get_stations(), 25)))
#         self.view.batch_count = self._batch_count
#         self.options = self.generate_options(batch_index=0)

#     @property
#     def batch_index(self):
#         return self._batch_index

#     @batch_index.setter
#     def batch_index(self, value: int):
#         self._batch_index = value
#         self.view.batch_index = value
#         self.options = self.generate_options(batch_index=value)

#     @property
#     def batch_count(self):
#         return self._batch_count

#     def generate_options(self, *, batch_index: int) -> List[discord.SelectOption]:
#         options = []
#         if self._place:
#             batched_stations = list(itertools.batched(self._place.get_stations(), 25))
#             for station in batched_stations[batch_index]:
#                 options.append(
#                     discord.SelectOption(
#                         label=station.title,
#                         value="{country}:{place}:{title}".format(
#                             country=station.country["title"], place=station.place.title, title=station.title)
#                     )
#                 )
#         return options

#     def get_options(self, place: Optional[Place], batch_index: int = 0) -> List[discord.SelectOption]:
#         options: List[discord.SelectOption] = []
#         if place:
#             batched_stations = list(itertools.batched(place.get_stations(), 25))
#             for station in batched_stations[batch_index]:
#                 options.append(
#                     discord.SelectOption(
#                         label=station.title,
#                         value="{country}:{place}:{title}".format(
#                             country=station.country["title"], place=station.place.title, title=station.title)
#                     )
#                 )

#         if self.values:
#             for option in options:
#                 if option.value == self.values[0]:
#                     option.default = True
#                 else:
#                     option.default = False
#         return options

#     async def callback(self, interaction: discord.Interaction):
#         player: wavelink.Player = await PlayerCog.get_voice_client(interaction, ensure=True)

#         if not player:
#             return

#         await interaction.response.defer()

#         country_name, place_name, station_name = self.values[0].split(":")
#         place: Place = RadioData.get_place(country_name, place_name)

#         if place:
#             station: RadioStation = place.find_station(title=station_name)

#             if station:
#                 url = station.url

#                 tracks: wavelink.Search = await wavelink.Playable.search(f"https://radio.garden/api/ara/content/listen/{station.id}/channel.mp3")

#                 track: wavelink.Playable = tracks[0]
#                 track._title = station.title
#                 track.extras = {"from_cog": "RadioCog", "station": station.title,
#                                 "place": place.title, "country": place.country}

#                 player.autoplay = wavelink.AutoPlayMode.enabled
#                 await player.queue.put_wait(track)
#                 if player.playing:
#                     await player.skip(force=True)
#                 else:
#                     await player.play(await player.queue.get_wait(), replace=True, volume=30)

#                 embed = interaction.message.embeds[0]
#                 embed.set_author(
#                     name=station.title,
#                     url="https://radio.garden" + url,
#                     icon_url=embed.author.icon_url
#                 )
#                 self.place = place
#                 self.ensure_options(place, )

#                 await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self.view)
#                 return

#         await interaction.followup.send("> 未知的站點")


def setup(bot: "Bot"):
    bot.add_cog(RadioCog(bot))
