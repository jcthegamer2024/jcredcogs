from .birthdaytracker import BirthdayTracker

async def setup(bot):
    await bot.add_cog(BirthdayTracker(bot))
