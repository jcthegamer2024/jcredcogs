import discord
from redbot.core import commands, Config

class Counting(commands.Cog):
    """A direction-switching counting game with rounds, milestones, and turn enforcement."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=246813579)
        self.config.register_guild(
            channel=None,
            current_number=0,
            last_user=None,
            mode="UP",  # UP or DOWN
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
        await self.config.guild(ctx.guild).mode.set("UP")

        # Update topic immediately
        await self.update_topic(ctx.channel, number + 1, "UP", 0)

        await ctx.send(f"Starting number set to **{number}**")

    # ============================================================
    # Helpers
    # ============================================================

    async def update_topic(self, channel: discord.TextChannel, next_number: int, mode: str, length: int):
        topic = f"Let's count! - Next number is {next_number} - Mode: {mode} - Chain length: {length}"
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

    # ============================================================
    # Direction Flip + Restart Logic (FIXED)
    # ============================================================

    async def flip_direction_and_restart(self, guild, channel, last_correct):
        mode = await self.config.guild(guild).mode()

        # Flip direction
        new_mode = "DOWN" if mode == "UP" else "UP"
        await self.config.guild(guild).mode.set(new_mode)

        # Announce direction change
        await channel.send(f"**Switching direction → {new_mode}!**")

        # Bot posts the restart number (last correct)
        await channel.send(str(last_correct))

        # Reset round stats
        await self.config.guild(guild).current_number.set(last_correct)
        await self.config.guild(guild).last_user.set(None)
        await self.config.guild(guild).round_length.set(0)
        await self.config.guild(guild).round_high.set(last_correct)

        # Compute next expected number
        next_number = last_correct + (1 if new_mode == "UP" else -1)

        # Update topic immediately (FIXED)
        await self.update_topic(channel, next_number, new_mode, 0)

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
        mode = await self.config.guild(guild).mode()
        round_high = await self.config.guild(guild).round_high()
        round_length = await self.config.guild(guild).round_length()

        # Turn enforcement
        if last_user is not None and message.author.id == last_user:
            await message.add_reaction("❌")
            await self.announce_round_end(message.channel, round_high, round_length)
            await self.flip_direction_and_restart(guild, message.channel, current)
            return

        # Determine expected number
        expected = current + 1 if mode == "UP" else current - 1

        # Correct number
        if number == expected:
            await message.add_reaction("✅")

            await self.config.guild(guild).current_number.set(number)
            await self.config.guild(guild).last_user.set(message.author.id)

            new_length = round_length + 1
            await self.config.guild(guild).round_length.set(new_length)

            if (mode == "UP" and number > round_high) or (mode == "DOWN" and number < round_high):
                await self.config.guild(guild).round_high.set(number)

            await self.update_topic(
                message.channel,
                number + (1 if mode == "UP" else -1),
                mode,
                new_length
            )

            await self.milestone(message, number)
            return

        # Incorrect number → round ends
        await message.add_reaction("❌")
        await self.announce_round_end(message.channel, round_high, round_length)
        await self.flip_direction_and_restart(guild, message.channel, current)
