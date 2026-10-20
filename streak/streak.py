import asyncio
from datetime import datetime, timezone, timedelta
import discord
from redbot.core import commands, Config

class streak(commands.Cog):
    """A UTC calendar daily streak tracking cog for images, stickers, and GIFs with expiry reminders."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210, force_registration=True
        )
        
        default_guild = {
            "streak_channel": None,
        }
        
        default_member = {
            "current_streak": 0,
            "best_streak": 0,
            "last_date": None,        # Stored as YYYY-MM-DD in UTC
            "last_remind_date": None, # Tracks if user was already pinged today
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        # Start the background checker loop
        self.reminder_task = self.bot.loop.create_task(self.streak_reminder_loop())

    def cog_unload(self):
        """Cancel background loop when cog unloads."""
        if self.reminder_task:
            self.reminder_task.cancel()

    async def streak_reminder_loop(self):
        """Background loop running every 30 minutes to check for expiring streaks."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._check_expiring_streaks()
            except Exception as e:
                print(f"Error in streak reminder loop: {e}")
            await asyncio.sleep(1800)  # Check every 30 minutes

    async def _check_expiring_streaks(self):
        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.strftime("%Y-%m-%d")
        yesterday_str = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")

        # Only trigger reminders during the last 3 hours of the UTC day (21:00 to 23:59 UTC)
        if now_utc.hour < 21:
            return

        all_guilds_data = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds_data.items():
            channel_id = guild_data.get("streak_channel")
            if not channel_id:
                continue

            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            all_members_data = await self.config.all_members(guild)
            for member_id, member_data in all_members_data.items():
                current_streak = member_data.get("current_streak", 0)
                last_date = member_data.get("last_date")
                last_remind_date = member_data.get("last_remind_date")

                if current_streak > 0 and last_date == yesterday_str and last_remind_date != today_str:
                    member = guild.get_member(member_id)
                    if member:
                        try:
                            embed = discord.Embed(
                                description=f"⚠️ {member.mention}, your **{current_streak}** day streak is about to expire in a couple of hours! Post an image, GIF, or sticker in {channel.mention} to keep it alive!",
                                color=discord.Color.red()
                            )
                            await channel.send(embed=embed)
                            await self.config.member(member).last_remind_date.set(today_str)
                        except discord.HTTPException:
                            pass

    def _is_valid_streak_content(self, message: discord.Message) -> bool:
        """Checks if a message contains an image attachment, sticker, or gif link."""
        if message.stickers:
            return True

        for attachment in message.attachments:
            if attachment.content_type and "image" in attachment.content_type:
                return True
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
                return True

        if message.embeds:
            for embed in message.embeds:
                if embed.type in ("image", "gifv") or embed.thumbnail or embed.image:
                    return True

        content_lower = message.content.lower()
        gif_providers = ['tenor.com', 'giphy.com', 'imgur.com', 'gfycat.com']
        if any(provider in content_lower for provider in gif_providers):
            return True

        if any(ext in content_lower for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            return True

        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        streak_channel_id = await self.config.guild(message.guild).streak_channel()

        if not streak_channel_id or message.channel.id != streak_channel_id:
            return

        # If it looks like a URL/link, give Discord 1.5s to generate the embed
        if "http://" in message.content.lower() or "https://" in message.content.lower():
            await asyncio.sleep(1.5)
            # Refetch message to get generated embeds
            try:
                message = await message.channel.fetch_message(message.id)
            except discord.HTTPException:
                pass

        if not self._is_valid_streak_content(message):
            try:
                await message.add_reaction("❌")
            except discord.HTTPException:
                pass
            return

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        member_config = self.config.member(message.author)
        
        last_date = await member_config.last_date()
        current_streak = await member_config.current_streak()
        best_streak = await member_config.best_streak()

        if last_date == today_str:
            embed = discord.Embed(
                description=f"⚠️ **• Streak already updated**\n\n• {message.author.mention}, you've already logged your streak for today! Come back tomorrow (UTC).",
                color=discord.Color.orange()
            )
            await message.reply(embed=embed)
            return

        if last_date is None:
            current_streak = 1
        else:
            last_dt = datetime.strptime(last_date, "%Y-%m-%d").date()
            today_dt = datetime.strptime(today_str, "%Y-%m-%d").date()
            diff = (today_dt - last_dt).days

            if diff == 1:
                current_streak += 1
            elif diff > 1:
                current_streak = 1
            else:
                return

        if current_streak > best_streak:
            best_streak = current_streak

        await member_config.current_streak.set(current_streak)
        await member_config.best_streak.set(best_streak)
        await member_config.last_date.set(today_str)

        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass

        embed = discord.Embed(
            description=f"✅ **• Streak updated**\n\n• {message.author.mention}\n\t• 🔥 **{current_streak}**",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        
        await message.reply(embed=embed)

    @commands.group(name="streak")
    @commands.guild_only()
    async def streak(self, ctx: commands.Context):
        """Streak command group."""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.streak_check)

    @streak.command(name="check")
    @commands.guild_only()
    async def streak_check(self, ctx: commands.Context, member: discord.Member = None):
        """Check your own or another user's current streak."""
        if member is None:
            member = ctx.author

        member_config = self.config.member(member)
        current = await member_config.current_streak()
        best = await member_config.best_streak()
        last_date = await member_config.last_date()

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        embed = discord.Embed(
            title=f"🔥 Streak Stats for {member.display_name}",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Current Streak", value=f"🔥 {current}", inline=True)
        embed.add_field(name="Best Streak", value=f"⭐ {best}", inline=True)
        
        if last_date == today_str:
            embed.set_footer(text="Streak updated today! Post again tomorrow (UTC) to extend.")
        elif last_date:
            embed.set_footer(text=f"Last streak update: {last_date} UTC. Post today to maintain it!")
        else:
            embed.set_footer(text="No active streak yet. Post an image/GIF/sticker in the streak channel!")

        await ctx.send(embed=embed)

    @streak.command(name="reset")
    @commands.admin_or_permissions(manage_guild=True)
    async def streak_reset(self, ctx: commands.Context, member: discord.Member):
        """Reset a user's streak back to 0."""
        member_config = self.config.member(member)
        await member_config.current_streak.set(0)
        await member_config.best_streak.set(0)
        await member_config.last_date.set(None)
        await member_config.last_remind_date.set(None)

        await ctx.send(f"✅ Successfully reset streak data for {member.mention}.")

    @commands.command(name="streaklb", aliases=["streaksleaderboard"])
    @commands.guild_only()
    async def streak_leaderboard(self, ctx: commands.Context):
        """View the server's top streaks leaderboard."""
        all_members = await self.config.all_members(ctx.guild)
        
        if not all_members:
            await ctx.send("No streak data found for this server yet!")
            return

        sorted_members = sorted(
            all_members.items(),
            key=lambda item: item[1].get("current_streak", 0),
            reverse=True
        )

        description_lines = []
        for rank, (member_id, data) in enumerate(sorted_members[:10], start=1):
            current = data.get("current_streak", 0)
            if current == 0:
                continue
            user = ctx.guild.get_member(member_id)
            name = user.display_name if user else f"Unknown User ({member_id})"
            description_lines.append(f"**{rank}.** {name} — 🔥 **{current}**")

        if not description_lines:
            await ctx.send("No active streaks found right now!")
            return

        embed = discord.Embed(
            title=f"🔥 Top Streaks Leaderboard — {ctx.guild.name}",
            description="\n".join(description_lines),
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    @commands.group()
    @commands.guild_only()
    async def streakset(self, ctx: commands.Context):
        """Configure streak settings."""
        pass

    @streakset.command(name="channel")
    @commands.admin_or_permissions(manage_guild=True)
    async def streakset_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where streak images/GIFs/stickers must be posted."""
        await self.config.guild(ctx.guild).streak_channel.set(channel.id)
        await ctx.send(f"✅ Streak channel has been set to {channel.mention}.")
