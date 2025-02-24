import os
import typing
import sys
import math
import weakref

from datetime import timedelta
from typing import Union, Tuple, List
from itertools import chain, batched

import discord
import wavelink

from discord import Interaction
from discord.utils import basic_autocomplete

from bot import ApplicationContext, BaseCog, Bot, Translator, cog_i18n
from bot.utils import get_image_dominant_color, CharWidthCounter

_ = Translator(__name__)


@cog_i18n
class PlayerCog(BaseCog, name="Player"):

    def __init__(self, bot: discord.Bot):
        super().__init__(bot)
        self.node: wavelink.Node

    @discord.Cog.listener()
    async def on_ready(self):
        await self.connect_nodes()

    @discord.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        self.log.info("Wavelink Node connected: %r | Resumed: %s",
                      payload.node, payload.resumed)

    async def connect_nodes(self) -> None:
        """Connect to our Lavalink nodes."""
        await self.bot.wait_until_ready()  # wait until the bot is ready
        self.node = wavelink.Node(
            # Protocol (http/s) is required, port must be 443 as it is the one lavalink uses
            uri=os.getenv("LAVA_LINK_URI"),
            password=os.getenv("LAVA_LINK_PASSWORD")
        )
        await wavelink.Pool.connect(nodes=[self.node], client=self.bot)  # Connect our nodes

    @staticmethod
    async def get_voice_client(ctx: Union[ApplicationContext, Interaction], *, ensure: bool = False) -> wavelink.Player | None:
        if not ctx.guild:
            await ctx.response.send_message("請先加入伺服器語音頻道再使用此指令。")
            return None

        player: wavelink.Player
        player = typing.cast(wavelink.Player, ctx.guild.voice_client)  # type: ignore

        if not player and ensure:
            try:
                # type: ignore
                player = await ctx.user.voice.channel.connect(cls=wavelink.Player)
                await ctx.guild.change_voice_state(
                    channel=ctx.user.voice.channel, self_deaf=True)

            except AttributeError:
                await ctx.response.send_message("請先加入語音頻道再使用此指令。")

            except discord.ClientException:
                await ctx.response.send_message("無法加入此語音頻道。請再試一次。")

        return player

    @staticmethod
    async def pasue_or_resume(ctx: ApplicationContext) -> bool:
        player: wavelink.Player = typing.cast(wavelink.Player, ctx.guild.voice_client)
        if player:
            await player.pause(not player.paused)
        return player.paused


@cog_i18n
@discord.guild_only()
class MusicCog(BaseCog, name="Music"):

    def __init__(self, bot):
        super().__init__(bot)

    @discord.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player: wavelink.Player | None = payload.player
        if not player:
            # Handle edge cases...
            return

        original: wavelink.Playable | None = payload.original
        track: wavelink.Playable = payload.track

        if dict(original.extras).get("from_cog", None) != "MusicCog" and not original.recommended:
            return

        track_queue: wavelink.Queue = player.auto_queue if player.queue.is_empty else player.queue
        next_track: wavelink.Playable | None = None if track_queue.is_empty else track_queue.peek()

        embed: discord.Embed = discord.Embed(
            title=_("正在播放"), description=f"", colour=discord.Color.from_rgb(*await get_image_dominant_color(track.artwork)),)

        embed.add_field(name=track.title, value=track.author)
        embed.add_field(name=_("時長"), value=f"{timedelta(milliseconds=track.length) if track.length < sys.maxsize else 'inf'}")

        if track.artwork:
            embed.set_image(url=track.artwork)

        if original and original.recommended:
            embed.description += _("\n\n`此歌曲由 {source} 推薦`").format(source=track.source)

        if track.album.name:
            embed.add_field(name="Album", value=track.album.name)

        if next_track:
            embed.set_footer(text=_("下一首 » {next_track_title}").format(next_track_title=next_track.title),
                             icon_url=next_track.artwork)

        await player.home.send(embed=embed, silent=True)

    @discord.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player: wavelink.Player | None = payload.player

        if not player:
            return

        if player.autoplay == wavelink.AutoPlayMode.enabled:
            return
        elif player.queue.is_empty:
            await player.disconnect()

    @discord.slash_command(
        i18n_name=_("播放"),
        i18n_description=_("播放音樂、串流或播放清單"),
    )
    @discord.option(
        "query",
        str,
        name_localizations=_("搜尋詞或輸入網址"),
        description_localizations=_(
            "想播放的歌曲或播放列表（可以是名稱、網址，或搜尋詞）"),
    )
    @discord.option(
        "recommend_queue",
        bool,
        name_localizations=_("推薦播放清單"),
        description_localizations=_(
            "啟用或停用自動推薦播放列表功能（預設為停用）"),
        default=False,
    )
    async def play(self, ctx: ApplicationContext, query: str, recommend_queue: bool) -> None:
        """Play a song with the given query."""
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx, ensure=True)

        # Turn on AutoPlay to enabled mode.
        # enabled = AutoPlay will play songs for us and fetch recommendations...
        # partial = AutoPlay will play songs for us, but WILL NOT fetch recommendations...
        # disabled = AutoPlay will do nothing...
        player.autoplay = wavelink.AutoPlayMode.enabled if recommend_queue else wavelink.AutoPlayMode.partial

        # Lock the player to this channel...
        if not hasattr(player, "home"):
            player.home = ctx.channel
        elif player.home != ctx.channel:
            await ctx.response.send_message(f"You can only play songs in {player.home.mention}, as the player has already started there.")
            return

        # This will handle fetching Tracks and Playlists...
        # Seed the doc strings for more information on this method...
        # If spotify is enabled via LavaSrc, this will automatically fetch Spotify tracks if you pass a URL...
        # Defaults to YouTube for non URL based queries...
        tracks: wavelink.Search = await wavelink.Playable.search(query)
        if not tracks:
            await ctx.response.send_message(f"{ctx.user.mention} - Could not find any tracks with that query. Please try again.")
            return

        if isinstance(tracks, wavelink.Playlist):
            # tracks is a playlist...
            tracks.track_extras(from_cog="MusicCog")
            added: int = await player.queue.put_wait(tracks)
            await ctx.response.send_message(f"Added the playlist **`{tracks.name}`** ({added} songs) to the queue.")
        else:
            track: wavelink.Playable = tracks[0]
            track.extras = {"from_cog": "MusicCog"}
            await player.queue.put_wait(track)
            await ctx.response.send_message(f"Added **`{track}`** to the queue.")

        if not player.playing:
            # Play now since we aren't playing anything...
            await player.play(player.queue.get(), volume=30)

    @discord.slash_command(
        i18n_name=_("跳過"),
        i18n_description=_("跳過目前曲目"),
    )
    async def skip(self, ctx: ApplicationContext) -> None:
        """Skip the current song."""
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)
        if not player:
            return

        await ctx.response.send_message(f"{ctx.user.mention} 跳過 **{player.current.title}**", delete_after=5)
        await player.skip(force=True)

    @discord.slash_command(
        i18n_name=_("待播清單"),
        i18n_description=_("顯示待播清單"),
    )
    async def queue(self, ctx: ApplicationContext) -> None:
        """show a track queue"""
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)
        # if not player:
        #     await ctx.response.send_message("> 未在播放狀態", delete_after=5)
        #     return

        # track_list_string: str = ""
        # track_queue: wavelink.Queue | None = None
        # total_length: int = 0

        # # 隊列不是空的
        # if not player.queue.is_empty:
        #     track_queue = player.queue

        # elif not getattr(player.current, 'recommended', False) and player.playing:
        #     track_queue = player.queue

        # elif not player.auto_queue.is_empty or not player.auto_queue.history.is_empty:
        #     track_queue = player.auto_queue

        # elif player.queue.is_empty and player.auto_queue.is_empty and player.playing:
        #     track_queue = player.queue

        # else:
        #     await ctx.response.send_message("> 沒有待播的列表")
        #     return

        # for index, track in enumerate(chain(track_queue.history, track_queue), 1):
        #     if track.is_stream or track.length > sys.maxsize:
        #         track_length = "stream"
        #     else:
        #         track_length = str(timedelta(milliseconds=track.length)).removeprefix("0:")

        #     # Current playing track
        #     if index == track_queue.history.count:
        #         ansi_color_tag = "[2;33m"
        #     elif index < track_queue.history.count:
        #         ansi_color_tag = "[2;30m"
        #     else:
        #         ansi_color_tag = "[1;2m"

        #     title = track.title
        #     width_counter = CharWidthCounter(title)

        #     if (width_counter.width()) >= 40:
        #         title = width_counter[:37]
        #         title.update("...")
        #     else:
        #         title = width_counter

        #     track_list_string += f"{ansi_color_tag}[1;2m{title.just("left", 45)}{track_length}[0m[0m\n"
        #     total_length += track.length


        # embed: discord.Embed = discord.Embed(
        #     title="播放列表" + ("- 推薦播放" if track_queue is player.auto_queue else ""), colour=discord.Colour.blurple())

        # embed.description = f"已播放 **{track_queue.history.count} / {track_queue.history.count+track_queue.count}** 首\n"
        # embed.description += f"總時長 **{timedelta(milliseconds=total_length) if total_length < sys.maxsize else 'inf'}**\n"
        # embed.description += f"```ansi\n{track_list_string}```"
        if player:
            view = PlayerQueueView(player.queue)
            await view.reload(ctx)
            embed = await view.create_embed(0)
            await ctx.response.send_message(view=view, embeds=[embed])
        else:
            embed: discord.Embed = discord.Embed(
                title="沒有待播的列表", colour=discord.Colour.blurple())
            await ctx.response.send_message(embed=embed)

    @discord.slash_command(
        i18n_name=_("調音器"),
        i18n_description=_("Set the filter to a other style"),
    )
    @discord.option(
        "style",
        str,
        name_localizations=_("調音模式"),
        description_localizations=_(
            "更改調音模式"),
        default="Default",
        autocomplete=basic_autocomplete(
            ("Default", "Nightcore", "Bassboost",
             "Karaoke", "Vaporwave", "8bit",
             "Reverb", "Treble Boost", "Lofi",
             "Echo", "Stereo Enhance", "Chipmunk",
             "Distortion", "Pitch Shift", "Radio", "Phaser"))
    )
    async def filter(self, ctx: ApplicationContext, style: str) -> None:
        """Set the filter to a other style."""
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)
        if not player:
            await ctx.response.send_message("> 未在播放狀態", delete_after=5)
            return

        filters: wavelink.Filters = player.filters

        match style:
            case "Nightcore":
                filters.timescale.set(pitch=1.2, speed=1.2, rate=1)

            case "Bassboost":
                # Bassboost effect (boost low-frequency bands)
                bands = [
                    {"band": 0, "gain": 0.3},  # Boost bass frequencies (band 0)
                    {"band": 1, "gain": 0.3},  # Boost bass frequencies (band 1)
                    {"band": 2, "gain": 0.1},  # Slight boost for mid-bass (band 2)
                    # Slight boost for low-mid (band 3), to avoid distortion
                    {"band": 3, "gain": 0.1},
                ]
                filters.equalizer.set(bands=bands)

            case "Karaoke":
                # Reset timescale and adjust equalizer to suppress vocals
                # Reset to normal speed/pitch
                filters.timescale.set(pitch=1, speed=1, rate=1)
                bands = [
                    # Reduce mid frequencies (vocals usually in this range)
                    {"band": 3, "gain": -0.3},
                    {"band": 4, "gain": -0.3},  # Reduce mid frequencies further
                    {"band": 5, "gain": -0.3},
                ]
                filters.equalizer.set(bands=bands)

            case "Vaporwave":
                filters.timescale.set(pitch=0.8, speed=0.9, rate=1)

            case "8bit":
                # Slow down and lower pitch for 8-bit style
                filters.timescale.set(pitch=0.9, speed=1.1, rate=1)
                # Boost high frequencies for that retro sound
                bands = [
                    {"band": 0, "gain": 0.2},  # Boost higher frequencies (band 0)
                    {"band": 1, "gain": 0.2},  # Boost higher frequencies (band 1)
                ]
                filters.equalizer.set(bands=bands)

            case "Reverb":
                # Reset to normal speed/pitch
                filters.timescale.set(pitch=1, speed=1, rate=1)
                # Apply a reverb-like effect by boosting mid to high frequencies
                bands = [
                    # Boost mid frequencies for reverb effect (band 2)
                    {"band": 2, "gain": 0.3},
                    {"band": 3, "gain": 0.2},  # Boost mid-high frequencies (band 3)
                ]
                filters.equalizer.set(bands=bands)

            case "Treble Boost":
                bands = [
                    {"band": 11, "gain": 0.5},  # 增強高頻（例如 11 - 14 頻段）
                    {"band": 12, "gain": 0.5},  # 增強高頻（例如 12 頻段）
                    {"band": 13, "gain": 0.5},
                ]
                filters.equalizer.set(bands=bands)

            case "Lofi":
                filters.timescale.set(pitch=0.9, speed=0.9, rate=1)  # 降低速度與音高，增加音樂的懷舊感
                bands = [
                    {"band": 0, "gain": -0.1},  # 稍微削弱低頻
                    {"band": 1, "gain": -0.1},  # 稍微削弱低頻
                    {"band": 2, "gain": -0.2},  # 減少中頻
                    {"band": 3, "gain": -0.3},  # 減少中頻
                    {"band": 10, "gain": -0.2},  # 削弱高頻
                ]
                filters.equalizer.set(bands=bands)

            case "Echo":
                # 使用適中的回聲效果，讓聲音感覺有延遲
                filters.timescale.set(pitch=1, speed=1, rate=1)  # 保持正常的音高和速度
                # 此時可對某些頻段稍微增強，以加強回聲感
                bands = [
                    {"band": 2, "gain": 0.3},  # 提升中頻，讓回聲聽起來更加明顯
                    {"band": 3, "gain": 0.2},  # 提升中高頻
                ]
                filters.equalizer.set(bands=bands)

            case "Stereo Enhance":
                # 增加立體聲的深度和寬度
                filters.timescale.set(pitch=1, speed=1, rate=1)  # 保持正常音高與速度
                # 可選擇對高頻進行一些增強來加強立體聲的表現
                bands = [
                    {"band": 10, "gain": 0.3},  # 提升高頻
                    {"band": 11, "gain": 0.3},  # 提升高頻
                ]
                filters.equalizer.set(bands=bands)

            case "Chipmunk":
                filters.timescale.set(pitch=2.0, speed=1.5, rate=1)  # 音高加倍，播放速度加快

            case "Distortion":
                bands = [
                    {"band": 0, "gain": 0.2},  # 稍微增強低頻
                    {"band": 1, "gain": 0.2},  # 增強低頻
                    {"band": 10, "gain": 0.4},  # 增強中高頻，讓失真更加明顯
                ]
                filters.equalizer.set(bands=bands)

            case "Pitch Shift":
                filters.timescale.set(pitch=1.5, speed=1, rate=1)  # 提高音高50%

            case "Radio":
                filters.timescale.set(pitch=1, speed=1, rate=1)  # 保持正常音高和速度
                bands = [
                    {"band": 0, "gain": -0.5},  # 減少低頻
                    {"band": 1, "gain": -0.5},  # 減少低頻
                    {"band": 2, "gain": -0.2},  # 減少中頻
                    {"band": 10, "gain": -0.2},  # 減少高頻
                ]
                filters.equalizer.set(bands=bands)

            case "Phaser":
                filters.timescale.set(pitch=1, speed=1, rate=1)  # 保持正常音高和速度
                bands = [
                    {"band": 3, "gain": 0.3},  # 增強中頻
                    {"band": 5, "gain": 0.2},  # 增強高頻
                ]
                filters.equalizer.set(bands=bands)

            case _:
                # Reset all filters if no match
                style = "Default"
                filters.reset()

        await player.set_filters(filters)
        await ctx.response.send_message(f"Set the filter to a **{style}** style")

    @discord.slash_command(
        i18n_name=_("繼續-暫停"),
        i18n_description=_("繼續或暫停目前曲目"),
    )
    async def pause_resume(self, ctx: ApplicationContext) -> None:
        """Pause or Resume the Player depending on its current state."""
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)
        if not player:
            await ctx.response.send_message("> 未在播放狀態", delete_after=5)
            return

        await player.pause(not player.paused)
        await ctx.response.send_message(f"{ctx.user.mention} {'繼續' if not player.paused else '暫停'}播放 **{player.current.title}**")

    @discord.slash_command(
        i18n_name=_("音量"),
        i18n_description=_("更改播放音量"),
    )
    @discord.option(
        "value",
        int,
        name_localizations=_("音量比"),
        description_localizations=_(
            "音量比(%) (預設 30%)"),
        default=30,
    )
    async def volume(self, ctx: ApplicationContext, value: int) -> None:
        """Change the volume of the player."""
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)
        if not player:
            await ctx.response.send_message("> 未在播放狀態", delete_after=5)
            return

        await ctx.response.send_message(f"{ctx.user.mention} 調整音量 **{player.volume}%** → **{value}%**", delete_after=5)
        await player.set_volume(value)

    @discord.slash_command(
        i18n_name=_("歌詞"),
        i18n_description=_("正在播放曲目的歌詞"),
    )
    async def lyrics(self, ctx: ApplicationContext) -> None:
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)
        if not player:
            await ctx.response.send_message("> 未在播放狀態", delete_after=5)
            return

        node: wavelink.Node = player.node
        track: wavelink.Playable = player.current

        if not track:
            return

        result = await node.send(
            method="GET", path=f"v4/sessions/{node.session_id}/players/{ctx.guild_id}/track/lyrics?skipTrackSource=false")

        if not result:
            await ctx.response.send_message(f"> 查無 {track.title} 歌詞")
            return

        embed = discord.Embed(title=f"{track.title} 的歌詞",
                              description=f"```{result['text']}```")
        embed.set_footer(text=f"提供者 {result['provider']}")

        await ctx.response.send_message(embed=embed)

        # await ctx.response.send_message(file=discord.File(io.StringIO(json.dumps(result['text'], indent=4, ensure_ascii=False)), "lyrics.txt"))

    @discord.slash_command(
        i18n_name=_("中斷連接"),
        i18n_description=_("離開語音頻道"),
    )
    async def disconnect(self, ctx: ApplicationContext) -> None:
        """Disconnect the Player."""
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)
        if not player:
            await ctx.response.send_message("> 未在播放狀態", delete_after=5)
            return

        await player.disconnect()
        player.cleanup()
        await ctx.response.send_message("bye")


class PlayerQueueView(discord.ui.View):

    def __init__(self, queue: wavelink.Queue | None = None):
        self.queue = weakref.proxy(queue)
        self.recommended = False
        self._batch_index = 0
        self._batch_count = 1
        super().__init__(timeout=None)

    async def create_embed(self, batch_index=0) -> discord.Embed:
        track_string_list: List[str] = []
        total_length: int = 0
        
        if self.queue is not None:
            for index, track in enumerate(chain(self.queue.history, self.queue), 1):
                if track.is_stream or track.length > sys.maxsize:
                    track_length = "stream"
                else:
                    track_length = str(timedelta(milliseconds=track.length)).removeprefix("0:")

                # Current playing track
                if index == self.queue.history.count:
                    ansi_color_tag = "[2;33m"
                elif index < self.queue.history.count:
                    ansi_color_tag = "[2;30m"
                else:
                    ansi_color_tag = "[1;2m"

                title = track.title
                width_counter = CharWidthCounter(title)

                if (width_counter.width()) >= 40:
                    title = width_counter[:37]
                    title.update("...")
                else:
                    title = width_counter

                track_string_list.append(f"{ansi_color_tag}[1;2m{title.just("left", 45)}{track_length}[0m[0m\n")
                total_length += track.length

            embed: discord.Embed = discord.Embed(
                title="播放列表" + ("- 推薦播放" if self.recommended else ""), colour=discord.Colour.blurple())
            embed.description = f"已播放 **{self.queue.history.count} / {self.queue.history.count+self.queue.count}** 首\n"
            embed.description += f"總時長 **{timedelta(milliseconds=total_length) if total_length < sys.maxsize else 'inf'}**\n"
            batched_track_string_list = (batched_list := list(batched(track_string_list, 20)))[min(batch_index, len(batched_list)-1)]
            embed.description += f"```ansi\n{''.join(batched_track_string_list)}```"
        else:
            embed: discord.Embed = discord.Embed(
                title="沒有待播的列表", colour=discord.Colour.blurple())

        return embed
    
    @property
    def batch_index(self) -> int:
        return self._batch_index

    @batch_index.setter
    def batch_index(self, value: int):
        self._batch_index = value
        self.player_queue_index_button.label = f"{value+1}/{self._batch_count}"

    @property
    def batch_count(self) -> int:
        return self._batch_count

    @batch_count.setter
    def batch_count(self, value: int):
        self._batch_count = value
        self.player_queue_index_button.label = f"{self._batch_index+1}/{value}"
    
    @property
    def prev_player_queue_page_button(self) -> discord.ui.Button:
        return self.get_item("persistent_view:player:prev_player_queue_page_button")

    @property
    def player_queue_index_button(self) -> discord.ui.Select:
        return self.get_item("persistent_view:player:player_queue_index_button")

    @property
    def next_player_queue_page_button(self) -> discord.ui.Button:
        return self.get_item("persistent_view:player:next_player_queue_page_button")

    @discord.ui.button(label="◀", style=discord.ButtonStyle.blurple, row=2, custom_id="persistent_view:player:prev_player_queue_page_button")
    async def prev_player_queue_page_button_callback(self, button, ctx: discord.Interaction):
        self.batch_index = (self.batch_index - 1) % self.batch_count
        await self.reload(ctx)

        embed = await self.create_embed(self.batch_index)

        await ctx.response.edit_message(view=self, embed=embed)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, disabled=True, row=2, custom_id="persistent_view:player:player_queue_index_button")
    async def player_queue_index_button_callback(self, button, ctx: discord.Interaction):
        pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary, row=2, custom_id="persistent_view:player:next_player_queue_page_button")
    async def next_player_queue_page_button_callback(self, button, ctx: discord.Interaction):
        self.batch_index = (self.batch_index + 1) % self.batch_count
        await self.reload(ctx)
        embed = await self.create_embed(self.batch_index)

        await ctx.response.edit_message(view=self, embed=embed)
    
    async def reload(self, ctx):
        player: wavelink.Player = await PlayerCog.get_voice_client(ctx)
        if not player:
            return

        # 隊列不是空的
        if not player.queue.is_empty:
            self.queue = weakref.proxy(player.queue)

        elif not getattr(player.current, 'recommended', False) and player.playing:
            self.queue = weakref.proxy(player.queue)

        elif not player.auto_queue.is_empty or not player.auto_queue.history.is_empty:
            self.queue = weakref.proxy(player.auto_queue)

        elif player.queue.is_empty and player.auto_queue.is_empty and player.playing:
            self.queue = weakref.proxy(player.queue)
        
        else:
            self.queue = None
            return
        
        if getattr(player.current, 'recommended', False):
            self.recommended = True

        track_count = self.queue.count + self.queue.history.count
        _, self.batch_count = map(int, self.player_queue_index_button.label.split("/"))
        self.batch_count = math.ceil(track_count / 20)
        # self.batch_index = math.ceil((self.queue.history.count-1) / 20)
        
        

def setup(bot: "Bot"):
    bot.add_cog(PlayerCog(bot))
    bot.add_cog(MusicCog(bot))
