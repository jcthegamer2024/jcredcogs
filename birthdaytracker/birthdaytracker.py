import calendar
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import tasks
from redbot.core import Config, checks, commands

DEFAULT_GUILD = {
    "birthdays": {},  # str(user_id): {"day": int, "month": int, "year": Optional[int]}
    "list_channel_id": None,
    "list_message_id": None,
    "announce_channel_id": None,
    "last_announced_date": None,  # Tracks "YYYY-MM-DD"
}

def get_ordinal_suffix(number: int) -> str:
    """Returns ordinal string for numbers (e.g., 21 -> 21st, 22 -> 22nd, 23 -> 23rd)."""
    if 11 <= (number % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


class BirthdayTracker(commands.Cog):
    """Tracks birthdays, maintains a live vertical embed list by month, and announces daily birthdays."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_guild(**DEFAULT_GUILD)
        self.check_birthdays_loop.start()

    def cog_unload(self):
        self.check_birthdays_loop.cancel()

    @tasks.loop(minutes=30)
    async def check_birthdays_loop(self):
        """Background loop to check and announce birthdays daily."""
        await self.bot.wait_until_red_ready()
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        for guild in self.bot.guilds:
            channel_id = await self.config.guild(guild).announce_channel_id()
            if not channel_id:
                continue

            last_announced = await self.config.guild(guild).last_announced_date()
            if last_announced == today_str:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            birthdays = await self.config.guild(guild).birthdays()
            if not birthdays:
                continue

            # Process members whose birthday matches today
            for user_id_str, data in birthdays.items():
                if data["month"] == now.month and data["day"] == now.day:
                    member = guild.get_member(int(user_id_str))
                    if not member:
                        continue

                    year = data.get("year")
                    if year:
                        age = now.year - year
                        bday_text = f"Happy {get_ordinal_suffix(age)} Birthday!"
                    else:
                        bday_text = "Happy Birthday!"

                    embed = discord.Embed(
                        title="📣 Birthday Announcement!",
                        color=discord.Color.teal()
                    )
                    embed.description = (
                        "❯ Today is a special Day!\n"
                        f"🎁 Please wish {member.mention} a {bday_text}"
                    )

                    await channel.send(content=member.mention, embed=embed)

            await self.config.guild(guild).last_announced_date.set(today_str)

    async def build_birthday_embed(self, guild: discord.Guild) -> discord.Embed:
        """Formats the birthday list into an Embed grouped from January to December."""
        birthdays = await self.config.guild(guild).birthdays()

        # Group birthdays by month (1 to 12)
        months_data = {m: [] for m in range(1, 13)}
        for user_id_str, data in birthdays.items():
            months_data[data["month"]].append((user_id_str, data["day"], data.get("year")))

        lines = []
        for month_num in range(1, 13):
            month_name = calendar.month_name[month_num]
            entries = months_data[month_num]

            lines.append(f"**{month_name}**")

            if not entries:
                lines.append("› *No birthdays*")
            else:
                entries.sort(key=lambda x: x[1])
                for uid, day, year in entries:
                    formatted_day = f"{day:02d}"
                    if year:
                        date_str = f"{formatted_day}. {month_name} {year}"
                    else:
                        date_str = f"{formatted_day}. {month_name}"
                    
                    lines.append(f"› <@{uid}> {date_str}")

            lines.append("")  # Blank line separator between months

        embed = discord.Embed(
            title="🎂 Server Birthdays",
            description="\n".join(lines).strip(),
            color=discord.Color.teal()
        )
        embed.set_footer(text="Use !bday set DD/MM/YYYY or DD/MM to add your birthday!")
        return embed

    async def update_dynamic_list(self, guild: discord.Guild):
        """Deletes the old message and sends a fresh updated dynamic birthday list embed."""
        channel_id = await self.config.guild(guild).list_channel_id()
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # Delete the old message if it exists
        message_id = await self.config.guild(guild).list_message_id()
        if message_id:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                pass

        # Fetch clean data, send new embed, and store new message ID
        embed = await self.build_birthday_embed(guild)
        new_msg = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await self.config.guild(guild).list_message_id.set(new_msg.id)

    @commands.group(name="bday", invoke_without_command=True)
    async def bday(self, ctx):
        """Birthday tracking commands."""
        await ctx.send_help(ctx.command)

    @bday.command(name="set")
    async def bday_set(self, ctx, date_str: Optional[str] = None):
        """Set your birthday.
        
        Format: DD/MM/YYYY or DD/MM
        Examples: !bday set 25/06/2006 or !bday set 25/06
        """
        if not date_str:
            await ctx.send(
                "❌ **Missing date format!**\n"
                "Please provide your birthday in **DD/MM/YYYY** or **DD/MM** format.\n\n"
                "**Examples:**\n"
                f"• `{ctx.clean_prefix}bday set 25/06/2006`\n"
                f"• `{ctx.clean_prefix}bday set 25/06`"
            )
            return

        parsed_date = None
        has_year = False

        # Try DD/MM/YYYY
        try:
            parsed_date = datetime.strptime(date_str, "%d/%m/%Y")
            has_year = True
        except ValueError:
            # Try DD/MM without year
            try:
                parsed_date = datetime.strptime(date_str, "%d/%m")
            except ValueError:
                await ctx.send(
                    "❌ **Invalid date format!** Please use **DD/MM/YYYY** or **DD/MM**.\n"
                    f"Examples:\n• `{ctx.clean_prefix}bday set 25/06/2006`\n• `{ctx.clean_prefix}bday set 25/06`"
                )
                return

        async with self.config.guild(ctx.guild).birthdays() as birthdays:
            birthdays[str(ctx.author.id)] = {
                "month": parsed_date.month,
                "day": parsed_date.day,
                "year": parsed_date.year if has_year else None,
            }

        month_name = calendar.month_name[parsed_date.month]
        formatted_day = f"{parsed_date.day:02d}"

        if has_year:
            display_str = f"{formatted_day}. {month_name} {parsed_date.year}"
        else:
            display_str = f"{formatted_day}. {month_name}"

        await ctx.send(f"✅ Saved your birthday as **{display_str}**!")
        await self.update_dynamic_list(ctx.guild)

    @bday.command(name="remove")
    async def bday_remove(self, ctx):
        """Remove your birthday from the list."""
        removed = False
        async with self.config.guild(ctx.guild).birthdays() as birthdays:
            if str(ctx.author.id) in birthdays:
                del birthdays[str(ctx.author.id)]
                removed = True

        if removed:
            await ctx.send("✅ Removed your birthday.")
            await self.update_dynamic_list(ctx.guild)
        else:
            await ctx.send("❌ You don't have a birthday saved.")

    @bday.command(name="adminset")
    @checks.admin_or_permissions(manage_guild=True)
    async def bday_adminset(self, ctx, member: discord.Member, date_str: str):
        """[Admin] Set or update the birthday for another user.
        
        Format: !bday adminset @user DD/MM/YYYY or DD/MM
        Examples: !bday adminset @User 25/06/2006
        """
        parsed_date = None
        has_year = False

        try:
            parsed_date = datetime.strptime(date_str, "%d/%m/%Y")
            has_year = True
        except ValueError:
            try:
                parsed_date = datetime.strptime(date_str, "%d/%m")
            except ValueError:
                await ctx.send(
                    "❌ **Invalid date format!** Please use **DD/MM/YYYY** or **DD/MM**.\n"
                    f"Example: `{ctx.clean_prefix}bday adminset {member.mention} 25/06/2006`"
                )
                return

        async with self.config.guild(ctx.guild).birthdays() as birthdays:
            birthdays[str(member.id)] = {
                "month": parsed_date.month,
                "day": parsed_date.day,
                "year": parsed_date.year if has_year else None,
            }

        month_name = calendar.month_name[parsed_date.month]
        formatted_day = f"{parsed_date.day:02d}"

        if has_year:
            display_str = f"{formatted_day}. {month_name} {parsed_date.year}"
        else:
            display_str = f"{formatted_day}. {month_name}"

        await ctx.send(f"✅ Set **{member.display_name}**'s birthday to **{display_str}**!")
        await self.update_dynamic_list(ctx.guild)

    @bday.command(name="adminremove")
    @checks.admin_or_permissions(manage_guild=True)
    async def bday_adminremove(self, ctx, member: discord.Member):
        """[Admin] Remove the birthday for another user."""
        removed = False
        async with self.config.guild(ctx.guild).birthdays() as birthdays:
            if str(member.id) in birthdays:
                del birthdays[str(member.id)]
                removed = True

        if removed:
            await ctx.send(f"✅ Removed **{member.display_name}**'s birthday.")
            await self.update_dynamic_list(ctx.guild)
        else:
            await ctx.send(f"❌ **{member.display_name}** does not have a birthday saved.")

    @bday.group(name="dynamiclist")
    @checks.admin_or_permissions(manage_guild=True)
    async def dynamiclist(self, ctx):
        """Admin settings for the dynamic vertical birthday list."""
        pass

    @dynamiclist.command(name="setchannel")
    async def set_list_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for the live updating birthday list embed."""
        await self.config.guild(ctx.guild).list_channel_id.set(channel.id)
        await self.config.guild(ctx.guild).list_message_id.set(None)

        await ctx.send(f"✅ Dynamic birthday list channel set to {channel.mention}.")
        await self.update_dynamic_list(ctx.guild)

    @bday.command(name="setannouncechannel")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_announce_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for daily birthday announcements."""
        await self.config.guild(ctx.guild).announce_channel_id.set(channel.id)
        await ctx.send(f"✅ Birthday announcement channel set to {channel.mention}.")

    @bday.command(name="testannounce")
    @checks.admin_or_permissions(manage_guild=True)
    async def test_announce(self, ctx, member: discord.Member):
        """Test the birthday announcement embed for a specific user."""
        channel_id = await self.config.guild(ctx.guild).announce_channel_id()
        if not channel_id:
            await ctx.send("❌ No announcement channel configured! Set one first using `!bday setannouncechannel #channel`.")
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Configured announcement channel could not be found.")
            return

        birthdays = await self.config.guild(ctx.guild).birthdays()
        user_data = birthdays.get(str(member.id))

        now = datetime.now(timezone.utc)
        if user_data and user_data.get("year"):
            age = now.year - user_data["year"]
            bday_text = f"Happy {get_ordinal_suffix(age)} Birthday!"
        else:
            bday_text = "Happy Birthday!"

        embed = discord.Embed(
            title="📣 Birthday Announcement!",
            color=discord.Color.teal()
        )
        embed.description = (
            "❯ Today is a special Day!\n"
            f"🎁 Please wish {member.mention} a {bday_text}"
        )

        await channel.send(content=member.mention, embed=embed)
        await ctx.send(f"✅ Sent test birthday announcement for {member.mention} to {channel.mention}!")
