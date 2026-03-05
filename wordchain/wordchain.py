import discord
from redbot.core import commands, Config

class WordChain(commands.Cog):
    """A word chain game with scoring and turn enforcement."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            channel=None,
            last_word=None,
            last_user=None,
            round_score=0
        )

    @commands.command()
    @commands.guild_only()
    async def setwordchainchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel to use for the word chain game."""
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"Word chain channel set to {channel.mention}")

    async def end_game(self, guild, channel):
        """Ends the game, announces score, and resets state."""
        score = await self.config.guild(guild).round_score()
        await channel.send(f"**== GAME ENDED - SCORE: {score} ==**")

        # Reset game state
        await self.config.guild(guild).last_word.set(None)
        await self.config.guild(guild).last_user.set(None)
        await self.config.guild(guild).round_score.set(0)

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

        # Only allow single alphabetic words
        if " " in content or not content.isalpha():
            return

        last_word = await self.config.guild(guild).last_word()
        last_user = await self.config.guild(guild).last_user()
        round_score = await self.config.guild(guild).round_score()

        # Prevent same user from playing twice
        if last_user is not None and message.author.id == last_user:
            await message.add_reaction("❌")
            await self.end_game(guild, message.channel)
            return

        # First word of the game
        if last_word is None:
            await self.config.guild(guild).last_word.set(content)
            await self.config.guild(guild).last_user.set(message.author.id)
            await self.config.guild(guild).round_score.set(1)
            await message.add_reaction("✅")
            return

        # Check chain rule
        if content[0] == last_word[-1]:
            # Valid word
            await self.config.guild(guild).last_word.set(content)
            await self.config.guild(guild).last_user.set(message.author.id)
            await self.config.guild(guild).round_score.set(round_score + 1)
            await message.add_reaction("✅")
        else:
            # Invalid word → end game
            await message.add_reaction("❌")
            await self.end_game(guild, message.channel)
