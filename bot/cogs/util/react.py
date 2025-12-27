import asyncio
import os
import sys
import re

from pathlib import Path
from typing import List, Optional

import discord
import sqlalchemy
import sqlalchemy.exc
import wavelink

from discord import OptionChoice

from bot.models.react_model import KeywordsType, KeywordsMatch, ReactType, ReactGuildConfig, GuildReact
from bot.cogs.util.player import PlayerCog
from bot.core.model import Database
from bot import ApplicationContext, Bot, BaseCog, Translator, cog_i18n


_ = Translator(__name__)


async def sticker_autocomplete(ctx: discord.AutocompleteContext) -> List[OptionChoice]:
    stickers = ctx.interaction.guild.stickers
    return [
        OptionChoice(name=f"{sticker.emoji} {sticker.name}", value=str(sticker.id))
        for sticker in stickers if ctx.value.casefold() in sticker.name.casefold()
    ][:25]


async def voice_autocomplete(ctx: discord.AutocompleteContext) -> List[OptionChoice]:
    choices = [
        OptionChoice(name=f"🎵 {voice.stem}", value=voice.name)
        for voice in list(Path(os.getenv("REACT_AUDIO_DIR")).glob("*.mp3")) if ctx.value.lower() in voice.name.lower()
    ]
    return choices[:25]


@cog_i18n
@discord.guild_only()
class React(BaseCog, name="反應"):

    def should_trigger_react(self, react: GuildReact, message: discord.Message) -> bool:
        if react.keywords_type == KeywordsType.STICKER:
            return int(react.keywords) in [sticker.id for sticker in message.stickers]

        elif react.keywords_type in (KeywordsType.PLAIN, KeywordsType.REGEX):
            rule = re.match if react.keywords_match == KeywordsMatch.MATCH else re.fullmatch
            return bool(rule(react.keywords, message.content))

        else:
            return False

    @discord.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        with Database() as database, \
          database.guild_config(message.guild.id, ReactGuildConfig, ensure=True) as guild_config:
            for react in guild_config.reacts:
                match react.react_type:
                    case ReactType.TEXT:
                        if not guild_config.enable_text_react:
                            return
                        if self.should_trigger_react(react, message):
                            await message.reply(react.react)

                    case ReactType.VOICE:
                        if not guild_config.enable_voice_react:
                            return

                        if message.author.voice and self.should_trigger_react(react, message):
                            player: wavelink.Player = await PlayerCog.get_voice_client(message, ensure=True, send_error_message=False)
                            if not player:
                                return
                            track_path: Path = Path(os.getenv("REACT_AUDIO_DIR")) / react.react
                            track: wavelink.Playable = (await wavelink.Playable.search(str(track_path.absolute()), source=""))[0]
                            track.extras = {"from_cog": "React"}

                            current_track = player.current
                            position = player.position
                            await player.play(track, add_history=False, volume=20)
                            await asyncio.sleep(track.length/1000)
                            if current_track:
                                await player.play(current_track, start=position if current_track.length < sys.maxsize else 0)

                    case ReactType.STICKER:
                        if not guild_config.enable_sticker_react:
                            return


@cog_i18n
@discord.guild_only()
class ReactCommands(BaseCog, name="反應指令"):

    def get_sticker(self, sticker_id: int | str) -> Optional[discord.Sticker]:
        for sticker in self.bot.stickers:
            if sticker.id == int(sticker_id):
                return sticker
        return None

    def format(self, *, react: GuildReact, string: str, **kwargs: str) -> str:
        type_emoji = {KeywordsType.PLAIN: "📄", KeywordsType.REGEX: "📑", KeywordsType.STICKER: "🖼️"}
        keywords_type_emoji = type_emoji.get(react.keywords_type, "❓")

        react_emoji = {ReactType.VOICE: "🎵", ReactType.TEXT: "📃"}
        react_type_emoji = react_emoji.get(react.react_type, "❓")

        if KeywordsType(react.keywords_type) == KeywordsType.STICKER:
            if sticker := self.get_sticker(react.keywords):
                keywords = sticker.name
            else:
                keywords = "[~~已移除的貼圖~~]"
        elif KeywordsType(react.keywords_type) in (KeywordsType.PLAIN, KeywordsType.REGEX):
            keywords = react.keywords
        else:
            raise ValueError(f"Unknow keywords type: {react.keywords_type}")

        if KeywordsMatch(react.keywords_match) == KeywordsMatch.MATCH:
            markdown_keywords = f"**{keywords}**"
        elif KeywordsMatch(react.keywords_match) == KeywordsMatch.FULL_MATCH:
            markdown_keywords = f"__***{keywords}***__"
        else:
            markdown_keywords = keywords

        result = string.format(
            keywords_type_emoji=keywords_type_emoji,
            react_type_emoji=react_type_emoji,
            markdown_keywords=markdown_keywords,
            keywords=keywords,
            react_type=react.react_type.value,
            react=react.react,
            **kwargs
        )
        return result
            
    
    async def react_autocomplete(self, ctx: discord.AutocompleteContext) -> List[OptionChoice]:
        with Database() as database, database.guild_config(ctx.interaction.guild_id, ReactGuildConfig, ensure=True) as guild_config:
            react_type = ReactType(ctx.options["react_type"])
            choices = []
            for index, react in enumerate(filter(lambda r: r.react_type == react_type, guild_config.reacts)):
                if ctx.value in react.keywords:
                    option = self.format(
                        react = react, 
                        string = "{index}. {keywords_type_emoji} {keywords}   ➜   {react_type_emoji} {react}",
                        index = index+1
                    )
                    choices.append(
                        OptionChoice(name=option, value=str(index))
                    )  
            return choices[:25]

    async def react_sticker_autocomplete(self, ctx: discord.AutocompleteContext) -> List[OptionChoice]:
        if KeywordsType(ctx.options["keywords_type"]) == KeywordsType.STICKER:
            return await sticker_autocomplete(ctx)
        else:
            return []
    
    async def react_audio_autocomplete(self, ctx: discord.AutocompleteContext) -> List[OptionChoice]:
        if ReactType(ctx.options["react_type"]) == ReactType.VOICE:
            return await voice_autocomplete(ctx)
        else:
            return []

# ----------------------------------------------------------------------------------------------
    
    @discord.slash_command(
        i18n_name=_("新增反應"),
        i18n_description=_("新增機器人對群組訊息的反應"),
    )
    @discord.option(
        "react_type",
        str,
        name_localizations=_("反應類型"),
        description_localizations=_("反應的類型"),
        autocomplete=discord.utils.basic_autocomplete(list(map(lambda x: x.value, ReactType))),
    )
    @discord.option(
        "keywords_type",
        str,
        name_localizations=_("關鍵詞類型"),
        description_localizations=_(
            "關鍵詞的類型"),
        autocomplete=discord.utils.basic_autocomplete(list(map(lambda x: x.value, KeywordsType))),
    )
    @discord.option(
        "keywords_match",
        str,
        name_localizations=_("關鍵詞規則"),
        description_localizations=_("關鍵詞的規則"),
        autocomplete=discord.utils.basic_autocomplete(list(map(lambda x: x.value, KeywordsMatch))),
    )
    @discord.option(
        "keywords",
        str,
        name_localizations=_("關鍵詞"),
        description_localizations=_("觸發反應的關鍵詞"),
        autocomplete=react_sticker_autocomplete
    )
    @discord.option(
        "react",
        str,
        name_localizations=_("反應"),
        description_localizations=_("偵測到關鍵詞後的反應"),
        autocomplete=react_audio_autocomplete
    )
    async def add_react(self, ctx: ApplicationContext, 
                             react_type: ReactType, keywords_type: KeywordsType, keywords_match: KeywordsMatch,
                             keywords: str, react: str) -> None:

        react_type = ReactType(react_type)
        keywords_type = KeywordsType(keywords_type)
        keywords_match = KeywordsMatch(keywords_match)

        if keywords_type == KeywordsType.PLAIN:
            keywords = re.escape(keywords)
        with Database() as database:
            new_react = GuildReact(
                guild_id = ctx.guild_id,
                keywords_type = keywords_type,
                keywords_match = keywords_match,
                keywords = keywords,
                react_type = react_type,
                react = react
            )
            try:
                database.session.add(new_react)
                database.session.commit()
            except sqlalchemy.exc.IntegrityError:
                reply_content = self.format(
                    react = new_react,
                    string = ">>> 重複的{react_type} - {keywords_type_emoji} {markdown_keywords} 已存在"
                )
            else:
                reply_content = self.format(
                    react = new_react,
                    string = ">>> 已新增 {react_type} **[** {keywords_type_emoji} {markdown_keywords}   ➜  {react_type_emoji} {react} **]**"
                )

        await ctx.response.send_message(content=reply_content)

    @discord.slash_command(
        i18n_name=_("列出所有反應"),
        i18n_description=_("列出機器人對群組訊息的所有反應"),
    )
    @discord.option(
        "react_type",
        str,
        name_localizations=_("反應類型"),
        description_localizations=_("反應的類型"),
        autocomplete=discord.utils.basic_autocomplete(list(map(lambda x: x.value, ReactType))),
    )
    async def list_reacts(self, ctx: ApplicationContext, react_type: ReactType) -> None:
        react_type = ReactType(react_type)
        with Database() as database, database.guild_config(ctx.guild_id, ReactGuildConfig, ensure=True) as guild_config:
            embed = discord.Embed(
                type  = "rich",
                title = react_type.value,
                color = discord.Colour.blue()
            )
            for index, react in enumerate(guild_config.reacts):
                if react.react_type == react_type:
                    name = self.format(
                        react = react,
                        string = "{index}. {keywords_type_emoji} {markdown_keywords}",
                        index = index + 1
                    )
                    embed.add_field(name=name, value=f">>> {react.react}", inline=True)

        await ctx.response.send_message(embed=embed)

# ----------------------------------------------------------------------------------------------

    @discord.slash_command(
        i18n_name=_("移除反應"),
        i18n_description=_("移除選定的反應"),
    )
    @discord.option(
        "react_type",
        str,
        name_localizations=_("反應類型"),
        description_localizations=_("反應的類型"),
        autocomplete=discord.utils.basic_autocomplete(list(map(lambda x: x.value, ReactType))),
    )
    @discord.option(
        "react",
        str,
        name_localizations=_("反應"),
        description_localizations=_("要移除的反應"),
        autocomplete=react_autocomplete
    )
    async def remove_react(self, ctx: ApplicationContext, 
                           react_type: ReactType, react: str) -> None:
        with Database() as database, database.guild_config(ctx.guild_id, ReactGuildConfig, ensure=True) as guild_config:
            react = guild_config.reacts.pop(int(react))
            database.session.delete(react)

            reply_content = self.format(
                react = react,
                string = ">>> 已移除 **[** {keywords_type_emoji} {markdown_keywords}   ➜   {react_type_emoji} {react} **]**",
            )
            
        await ctx.response.send_message(content=reply_content)


def setup(bot: "Bot"):
    bot.add_cog(React(bot))
    bot.add_cog(ReactCommands(bot))

# ----------------------------------------------------------------------------------------------

#     @app_commands.guild_only()
#     @group.command(name="新增語音反應", description="新增機器人對群組訊息的語音反應")
#     @app_commands.describe(
#         keywords_type="關鍵詞的類型", 
#         keywords_rule="關鍵詞文字規則",
#         keywords="觸發反應的關鍵詞",
#         react="偵測到關鍵詞後的反應"
#     )
#     @app_commands.rename(keywords_type='關鍵詞類型', keywords_rule="關鍵詞規則", keywords="關鍵詞", react="反應")
#     @app_commands.autocomplete(react=voice_autocomplete, keywords=react_sticker_autocomplete)
#     async def add_voice_react(self, interaction: discord.Interaction, 
#                               keywords_type: KeywordsTypeChoices, keywords_rule: KeywordsRuleChoices, 
#                               keywords: str, react: str) -> None:
#         if keywords_type.value == "PLAIN":
#             keywords = re.escape(keywords)

#         async with ConfigLoader.Guild(interaction.guild_id) as conf:
#             react_obj = conf.reacts.add_voice_react(
#                 keywords_type=keywords_type.value,
#                 keywords_rule=keywords_rule.value,
#                 keywords=keywords,
#                 react=react
#             )
#         reply_content = self.format(
#             react = react_obj,
#             string = ">>> 已新增 **[** {keywords_type_emoji} {markdown_keywords}   ➜   {react_type_emoji} {react} **]**"
#         )

#         await interaction.response.send_message(content=reply_content, silent=True, ephemeral=True) 

# # ----------------------------------------------------------------------------------------------

#     @app_commands.guild_only()
#     @group.command(name="列出所有反應", description="列出選定類型的所有反應")
#     @app_commands.describe(react_type="反應類型")
#     @app_commands.rename(react_type="反應類型")
#     async def list_reacts(self, interaction: discord.Interaction, 
#                           react_type: ReactTypeChoices) -> None:
#         async with ConfigLoader.Guild(interaction.guild_id) as conf:
#             reacts = getattr(conf.reacts, react_type.value)
#             embed = discord.Embed(
#                 type  = "rich",
#                 title = react_type.name,
#                 color = discord.Colour.blue()
#             )
#             for index, react in enumerate(reacts):
#                 name = self.format(
#                     react = react,
#                     string = "{index}. {keywords_type_emoji} {markdown_keywords}",
#                     index = index + 1
#                 )
#                 embed.add_field(name=name, value=f">>> {react.react}", inline=True)

#         await interaction.response.send_message(embed=embed)

# # ----------------------------------------------------------------------------------------------

#     @app_commands.guild_only()
#     @group.command(name="移除反應", description="移除選定的反應")
#     @app_commands.describe(react_type="反應類型", react="要移除的反應")
#     @app_commands.rename(react_type="反應類型", react="反應")
#     async def remove_react(self, interaction: discord.Interaction, 
#                            react_type: ReactTypeChoices, react: str) -> None:
#         async with ConfigLoader.Guild(interaction.guild_id) as conf:
#             reacts = getattr(conf.reacts, react_type.value)
#             react = reacts.pop(int(react))

#         reply_content = self.format(
#             react = react,
#             string = ">>> 已移除 **[** {keywords_type_emoji} {markdown_keywords}   ➜   {react_type_emoji} {react} **]**",
#         )
            
#         await interaction.response.send_message(content=reply_content, silent=True)

#     remove_react.autocomplete("react")(react_autocomplete)

# # ----------------------------------------------------------------------------------------------

#     async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
#         await ctx.send('An error occurred: {}'.format(str(error)))

#     async def cog_app_command_error(self, interaction: discord.Interaction, 
#                                     error: commands.CommandError, *args) -> None:
#          await interaction.response.send_message('An error occurred: {}'.format(str(error)))

# async def setup(bot: commands.Bot):
#     await bot.add_cog(React(bot))
#     await bot.add_cog(ReactCommands(bot))