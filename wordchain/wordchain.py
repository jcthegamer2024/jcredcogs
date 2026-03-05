import discord
from redbot.core import commands, Config

class WordChain(commands.Cog):
    """A simple word chain game."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            channel=None,
            last_word=None
        )

    @commands.command()
    @commands.guild_only()
    async def setwordchainchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel to use for the word chain game."""
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"Word chain channel set to {channel.mention}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return

        guild = message.guild
        channel_id = await self.config.guild(guild).channel()
        if channel_id is None:
            return  # No channel configured

        if message.channel.id != channel_id:
            return  # Not in the wordchain channel

        content = message.content.strip().lower()
        if " " in content:
            return  # Ignore multi-word messages

        if not content.isalpha():
            return  # Ignore non-word messages

        last_word = await self.config.guild(guild).last_word()

        # First word in chain
        if last_word is None:
            await self.config.guild(guild).last_word.set(content)
            await message.add_reaction("✅")
            return

        # Check chain rule
        if content[0] == last_word[-1]:
            await self.config.guild(guild).last_word.set(content)
            await message.add_reaction("✅")
        else:
            # Word breaks the chain — optional: add ❌ or message
            pass
