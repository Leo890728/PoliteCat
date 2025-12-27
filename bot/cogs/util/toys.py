import random

import discord
from discord import Embed

from bot import ApplicationContext, BaseCog, Bot, Translator, cog_i18n

_ = Translator(__name__)


@cog_i18n
class ToysCog(BaseCog, name="小工具"):

    @discord.slash_command(
        i18n_name=_("擲骰"),
        i18n_description=_("擲個運氣☘️"),
    )
    @discord.option(
        "dice",
        int,
        name_localizations=_("骰子數"),
        description_localizations=_(
            "骰子數量(最大值25)"),
    )
    @discord.option(
        "face",
        int,
        name_localizations=_("面數"),
        description_localizations=_(
            "骰子面數(最大值100)"),
    )
    async def dice_roller(self, ctx: ApplicationContext, dice: int, face: int):
        dice = min(25, max(1, dice))
        face = min(100, max(1, face))
        await ctx.response.defer()
        result = [random.randint(1, face) for _ in range(dice)]
        result_sum = sum(result)

        dp = [[0] * (result_sum + 1) for _ in range(dice + 1)]
        dp[0][0] = 1  # 初始條件：0 個骰子總和為 0

        # 動態規劃填表
        for i in range(1, dice + 1):
            for j in range(1, result_sum + 1):
                dp[i][j] = sum(dp[i-1][j-k] for k in range(1, face+1) if j-k >= 0)

        # 返回總和為 target_sum 的可能性
        chance = 100 * (dp[dice][result_sum] / (face**dice))

        embed = Embed(
            title=f"{dice}D{face} 擲骰結果",
            description=str(result)
        )
        embed.add_field(name="總數", value=str(result_sum))
        embed.add_field(name="機率", value="<0.01%" if (v:=f"{chance:.2f}%") == "0.00%" else v)

        await ctx.followup.send(embed=embed)


def setup(bot: "Bot"):
    bot.add_cog(ToysCog(bot))
