from .wordchain import WordChain

async def setup(bot):
    await bot.add_cog(WordChain(bot))
