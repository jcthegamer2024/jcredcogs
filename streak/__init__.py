from .streaks import streak


async def setup(bot):
    await bot.add_cog(streak(bot))
