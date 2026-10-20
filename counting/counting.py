import discord
from redbot.core import commands, Config

class Counting(commands.Cog):
    """A standard counting game with rounds, milestones, and turn enforcement."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=246813579)
        self.config.register_guild(
            channel=None,
            current_number=0,
            last_user=None,
            round_high=0,
            round_length=0,
            start_number=0
        )

    # ============================================================
    # Admin Commands
    # ============================================================

    @commands.command()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def setcountchannel(self, ctx, channel: discord.TextChannel):
        """Set the counting channel."""
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"Counting channel set to {channel.mention}")

    @commands.command()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def setcountstart(self, ctx, number: int):
        """Set the starting number."""
        await self.config.guild(ctx.guild).current_number.set(number)
        await self.config.guild(ctx.guild).round_high.set(number)
        await self.config.guild(ctx.guild).round_length.set(0)
        await self.config.guild(ctx.guild).start_number.set(number)

        # Update topic immediately
        await self.update_topic(ctx.channel, number + 1, 0)

        await ctx.send(f"Starting number set to **{number}**")

    @commands.command()
    @commands.guild_only()
    async def countdebug(self, ctx):
        """Debug: show stored channel ID and current channel ID."""
        stored = await self.config.guild(ctx.guild).channel()
        await ctx.send(
            f"Stored channel ID: `{stored}`\n"
            f"This channel ID: `{ctx.channel.id}`\n"
            f"Match: `{stored == ctx.channel.id}`"
        )

    # ============================================================
    # Helpers
    # ============================================================

    async def update_topic(self, channel: discord.TextChannel, next_number: int, length: int):
        topic = f"Let's count! - Next number is {next_number} - Chain length: {length}"
        try:
            await channel.edit(topic=topic)
        except discord.Forbidden:
            pass

    async def milestone(self, message: discord.Message, number: int):
        if number % 100 == 0:
            m = await message.channel.send(f"🎉 **Milestone reached: {number}!** 🎉")
            await m.add_reaction("🎉")
            try:
                await m.pin()
            except discord.Forbidden:
                pass

    async def announce_round_end(self, channel, high, length):
        await channel.send(
            f"**== ROUND OVER ==**\n"
            f"Reached: **{high}**\n"
            f"Chain length: **{length}**"
        )

    async def reset_counting(self, guild, channel):
        """Resets the counting game back to 0."""
        await channel.send("**Counting reset to 0!**")
        await channel.send("0")

        # Reset round and count stats to 0
        await self.config.guild(guild).current_number.set(0)
        await self.config.guild(guild).last_user.set(None)
        await self.config.guild(guild).round_length.set(0)
        await self.config.guild(guild).round_high.set(0)

        # Update topic for the next expected number (1)
        await self.update_topic(channel, 1, 0)

    # ============================================================
    # Message Listener
    # ============================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild = message.guild
        channel_id = await self.config.guild(guild).channel()
        if channel_id is None or message.channel.id != channel_id:
            return

        # Try to parse number
        try:
            number = int(message.content.strip())
        except ValueError:
            return

        current = await self.config.guild(guild).current_number()
        last_user = await self.config.guild(guild).last_user()
        round_high = await self.config.guild(guild).round_high()
        round_length = await self.config.guild(guild).round_length()

        # Turn enforcement (same user counting twice in a row)
        if last_user is not None and message.author.id == last_user:
            await message.add_reaction("❌")
            await self.announce_round_end(message.channel, round_high, round_length)
            await self.reset_counting(guild, message.channel)
            return

        # Expected number is always current + 1
        expected = current + 1

        # Correct number
        if number == expected:
            await message.add_reaction("✅")

            await self.config.guild(guild).current_number.set(number)
            await self.config.guild(guild).last_user.set(message.author.id)

            new_length = round_length + 1
            await self.config.guild(guild).round_length.set(new_length)

            if number > round_high:
                await self.config.guild(guild).round_high.set(number)

            await self.update_topic(
                message.channel,
                number + 1,
                new_length
            )

            await self.milestone(message, number)
            return

        # Incorrect number → round ends and resets to 0
        await message.add_reaction("❌")
        await self.announce_round_end(message.channel, round_high, round_length)
        await self.reset_counting(guild, message.channel)
