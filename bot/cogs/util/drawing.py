import typing
import sqlite3
import random

import discord

from discord import (
    ButtonStyle,
    Interaction,
)
from discord import ui as Ui

from bot import ApplicationContext, BaseCog, Bot, Translator, cog_i18n

_ = Translator(__name__)


class DrawingBoxDataBase:
    def __init__(self):
        self.database = sqlite3.connect("bot.db")

    def __enter__(self):
        self.cursor = self.database.cursor()
        return self

    def __exit__(self, exc_type, exc_value, exc_trace):
        self.database.close()

    def get_boxes(self, guild_id):
        result = self.cursor.execute(
            "SELECT * FROM DrawingBox WHERE GuildID = ?", (guild_id,))


@cog_i18n
@discord.guild_only()
class DrawingCog(BaseCog, name="抽籤"):

    def __init__(self, bot):
        super().__init__(bot)
        self.database = sqlite3.connect("bot.db")

    def cog_unload(self):
        self.database.close()

    async def boxes_name_autocomplete(self, ctx: discord.AutocompleteContext) -> typing.List[str]:
        drawing_boxes = self.get_guild_drawing_boxes(ctx.interaction.guild_id)
        if drawing_boxes:
            return [
                box_name
                for box_name in drawing_boxes if ctx.value in box_name
            ]
        else:
            return []

    def get_guild_drawing_boxes(self, guild_id):
        cursor = self.database.cursor()
        box_items = list(
            map(
                lambda i: i[0],
                cursor.execute(
                    "SELECT BoxName FROM DrawingBox WHERE DrawingBox.GuildID = ?", (guild_id,))
            )
        )
        return box_items

    @discord.slash_command(
        i18n_name=_("建立抽籤盒"),
        i18n_description=_("建立抽籤盒"),
    )
    @discord.option(
        "drawing_box_name",
        str,
        name_localizations=_("抽籤盒名稱"),
        description_localizations=_(
            "抽籤盒的名稱"),
    )
    async def create_drawing_box(self, ctx: ApplicationContext, drawing_box_name: str):
        try:
            cursor = self.database.cursor()
            cursor.execute("INSERT INTO DrawingBox(BoxName, GuildID) VALUES (?, ?)",
                           (drawing_box_name, ctx.guild_id))
            self.database.commit()
            await ctx.response.send_message(f"> 成功建立抽籤盒 {drawing_box_name}")
        except sqlite3.IntegrityError as e:
            await ctx.response.send_message("> 已存在的抽籤盒")
        except Exception as e:
            await ctx.response.send_message(f"> {e}")

    @discord.slash_command(
        i18n_name=_("加入抽籤項"),
        i18n_description=_("在抽籤盒加入抽籤項"),
    )
    @discord.option(
        "box_name",
        str,
        name_localizations=_("抽籤盒"),
        description_localizations=_(
            "抽籤盒的名稱"),
        autocomplete=boxes_name_autocomplete
    )
    @discord.option(
        "option_value",
        str,
        name_localizations=_("抽籤項"),
        description_localizations=_(
            "加入抽籤盒的籤"),
    )
    async def add_drawing_box_option(self, ctx: ApplicationContext, box_name: str, option_value: str):
        try:
            cursor = self.database.cursor()

            box_name, box_id = cursor.execute(
                "SELECT BoxName, BoxID FROM DrawingBox WHERE DrawingBox.GuildID = ? AND DrawingBox.BoxName = ?",
                (ctx.guild_id, box_name)
            ).fetchone()

            cursor.execute(
                "INSERT INTO DrawnItem(DrawingBoxID, Value) VALUES (?, ?)", (box_id, option_value))
            self.database.commit()
            await ctx.response.send_message(f"> 成功在抽籤盒 `{box_name}` 加入選項 `{option_value}`")
        except sqlite3.IntegrityError as e:
            await ctx.response.send_message("> 重複的選項或不存在的抽籤盒")
        except Exception as e:
            await ctx.response.send_message(f"> {e}")

    @discord.slash_command(
        i18n_name=_("開始抽籤"),
        i18n_description=_("開始抽籤"),
    )
    @discord.option(
        "box_name",
        str,
        name_localizations=_("抽籤盒"),
        description_localizations=_("抽籤盒的名稱"),
        autocomplete=boxes_name_autocomplete
    )
    async def create_drawing_box_view(self, ctx: ApplicationContext, box_name: str):
        try:
            cursor = self.database.cursor()

            box_name, box_id = cursor.execute(
                "SELECT BoxName, BoxID FROM DrawingBox WHERE DrawingBox.GuildID = ? AND DrawingBox.BoxName = ?",
                (ctx.guild_id, box_name)
            ).fetchone()

            box_items = list(
                map(
                    lambda i: i[0],
                    cursor.execute(
                        "SELECT Value FROM DrawnItem WHERE DrawingBoxID = ?", (box_id,))
                )
            )

            if not box_items:
                await ctx.response.send_message("> 籤箱沒籤是在抽個芭樂 🙄🤌")
                return

            embed = discord.Embed(
                title=f"抽籤盒 {box_name}",
                description=f"內含 **{len(box_items)}** 支籤",
            )

            view = DrawingBoxView(box_name, box_items)

            await ctx.response.send_message(embed=embed, view=view)
        except sqlite3.IntegrityError as e:
            await ctx.response.send_message("> 不存在的抽籤盒")
        except Exception as e:
            await ctx.response.send_message(f"> {e}")


class DrawingBoxView(discord.ui.View):

    def __init__(self, box_name, items):
        super().__init__(timeout=None)
        self.box_name = box_name
        self.items = items
        self.drawn_result = dict()

    @Ui.button(
        label="抽籤",
        style=ButtonStyle.green,
        custom_id="persistent_view:drawing_box:drawing",
    )
    async def drawing_button(self, _: Ui.Button, interaction: Interaction):
        done_count = 0
        errors: typing.Dict[str, Exception] = {}

        drawer = interaction.user

        if drawer in self.drawn_result.keys():
            return await interaction.response.send_message(f"{drawer.mention} 你已經抽過了🫵🤨")

        drawer_item = list(filter(lambda i: drawer.mention in i, self.items))
        if drawer_item:
            self.items.remove(drawer_item[0])
        random.shuffle(self.items)
        result = self.items.pop()
        self.drawn_result.setdefault(drawer, result)
        if drawer_item:
            self.items.append(drawer_item)

        embed = discord.Embed(
            title=f"抽籤盒 {self.box_name}",
            description=f"已抽 **{len(self.drawn_result)}** 支籤 \n剩餘 **{len(self.items)}** 支籤",
        )

        for user, drawn_item in reversed(self.drawn_result.items()):
            embed.add_field(name=user.name, value=drawn_item, inline=True)

        await interaction.message.edit(
            content="",
            embed=embed,
            view=self,
        )
        await interaction.response.send_message(f"{drawer.mention} 抽到了 **{result}**")


def setup(bot: "Bot"):
    bot.add_cog(DrawingCog(bot))
