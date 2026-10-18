from .streaks import Streaks

async def setup(bot):
    await bot.add_cog(Streaks(bot))
