import asyncio
from typing import Dict, Optional, Set

import discord
from discord.ext import tasks
from redbot.core import Config, checks, commands

DEFAULT_GUILD = {
    "category_id": None,
    "panel_channel_id": None,
    "panel_message_id": None,
}


class UserLimitModal(discord.ui.Modal, title="Set Voice Channel User Limit"):
    limit = discord.ui.TextInput(
        label="User Limit (0 for unlimited)",
        placeholder="Enter a number between 0 and 99...",
        min_length=1,
        max_length=2,
        required=True,
    )

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_limit = int(self.limit.value)
            if not (0 <= user_limit <= 99):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number between **0** and **99**.", ephemeral=True
            )
            return

        await self.channel.edit(user_limit=user_limit)
        display = "Unlimited" if user_limit == 0 else str(user_limit)
        await interaction.response.send_message(
            f"✅ User limit for {self.channel.mention} updated to **{display}**.", ephemeral=True
        )


class AllowUserSelect(discord.ui.UserSelect):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(
            placeholder="Select users allowed to join...",
            min_values=1,
            max_values=10,
        )
        self.cog = cog
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        # First ensure @everyone cannot connect if lock mode is engaged
        overwrites = self.channel.overwrites
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False)

        added_mentions = []
        for user in self.values:
            overwrites[user] = discord.PermissionOverwrite(connect=True, view_channel=True)
            added_mentions.append(user.mention)

        await self.channel.edit(overwrites=overwrites)
        await interaction.response.send_message(
            f"🔒 Granted join access to: {', '.join(added_mentions)}", ephemeral=True
        )


class AccessControlView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.add_item(AllowUserSelect(cog, channel))


class VCControlView(discord.ui.View):
    """Control panel attached inside the newly created voice channel's chat interface."""

    def __init__(self, cog, channel: discord.VoiceChannel, owner: discord.Member):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel = channel
        self.owner = owner

    @discord.ui.button(label="Set Limit", style=discord.ButtonStyle.secondary, emoji="🔢")
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Only the channel creator can modify settings.", ephemeral=True)
            return
        await interaction.response.send_modal(UserLimitModal(self.cog, self.channel))

    @discord.ui.button(label="Allow Users", style=discord.ButtonStyle.primary, emoji="🔐")
    async def allow_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Only the channel creator can modify settings.", ephemeral=True)
            return
        view = AccessControlView(self.cog, self.channel)
        await interaction.response.send_message("Select members who are permitted to join your channel:", view=view, ephemeral=True)

    @discord.ui.button(label="Lock / Unlock", style=discord.ButtonStyle.danger, emoji="🔒")
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Only the channel creator can modify settings.", ephemeral=True)
            return

        current_overwrite = self.channel.overwrites_for(interaction.guild.default_role)
        if current_overwrite.connect is False:
            # Unlock
            await self.channel.set_permissions(interaction.guild.default_role, connect=None)
            await interaction.response.send_message("🔓 Channel is now **unlocked** for everyone.", ephemeral=True)
        else:
            # Lock
            await self.channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 Channel is now **locked**. Use **Allow Users** to grant access.", ephemeral=True)


class VCCreationPanelView(discord.ui.View):
    """Persistent view attached to the main public VC Creation Panel embed."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Create Voice Channel", style=discord.ButtonStyle.success, emoji="➕", custom_id="tempvc_create_btn")
    async def create_vc(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category_id = await self.cog.config.guild(guild).category_id()

        if not category_id:
            await interaction.response.send_message("❌ TempVC category is not configured. An admin must run `!tempvc setcategory`.", ephemeral=True)
            return

        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ Configured category was not found.", ephemeral=True)
            return

        # Check if user already owns an active voice channel
        for vc_id, owner_id in self.cog.active_channels.items():
            if owner_id == interaction.user.id:
                existing_vc = guild.get_channel(vc_id)
                if existing_vc:
                    await interaction.response.send_message(f"❌ You already have an active channel: {existing_vc.mention}", ephemeral=True)
                    return

        # Create new Voice Channel
        channel_name = f"🔊 {interaction.user.display_name}'s VC"
        new_vc = await guild.create_voice_channel(
            name=channel_name,
            category=category,
            reason=f"TempVC created by {interaction.user}"
        )

        # Track created channel
        self.cog.active_channels[new_vc.id] = interaction.user.id

        # Send control embed directly inside the new Voice Channel chat
        control_embed = discord.Embed(
            title=f"🎙️ {interaction.user.display_name}'s Voice Channel",
            description=(
                "Welcome to your temporary voice channel!\n\n"
                "**Controls:**\n"
                "• 🔢 **Set Limit:** Choose maximum users allowed (0-99).\n"
                "• 🔐 **Allow Users:** Pick specific members who can join.\n"
                "• 🔒 **Lock / Unlock:** Toggle general access for everyone.\n\n"
                "⚠️ *Note: This channel will automatically delete after 5 minutes if left empty.*"
            ),
            color=discord.Color.teal()
        )
        control_view = VCControlView(self.cog, new_vc, interaction.user)
        await new_vc.send(embed=control_embed, view=control_view)

        await interaction.response.send_message(
            f"✅ Created your voice channel: {new_vc.mention}\nJoin within 5 minutes to keep it active!",
            ephemeral=True
        )


class TempVoice(commands.Cog):
    """Dynamic voice channel creator with interactive controls and 5-minute cleanup logic."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8473629101, force_registration=True)
        self.config.register_guild(**DEFAULT_GUILD)

        # In-memory tracking
        self.active_channels: Dict[int, int] = {}  # channel_id: owner_user_id
        self.empty_timers: Dict[int, int] = {}     # channel_id: empty_seconds

        self.bot.add_view(VCCreationPanelView(self))
        self.cleanup_loop.start()

    def cog_unload(self):
        self.cleanup_loop.cancel()

    @tasks.loop(seconds=30)
    async def cleanup_loop(self):
        """Scans active channels every 30 seconds and deletes those empty for >= 5 minutes (300s)."""
        await self.bot.wait_until_red_ready()

        channels_to_remove: Set[int] = set()

        for channel_id in list(self.active_channels.keys()):
            channel = self.bot.get_channel(channel_id)

            # Channel deleted manually or no longer exists
            if not channel or not isinstance(channel, discord.VoiceChannel):
                channels_to_remove.add(channel_id)
                continue

            # Check occupancy
            if len(channel.members) == 0:
                self.empty_timers[channel_id] = self.empty_timers.get(channel_id, 0) + 30
                
                # Delete after 300 seconds (5 minutes)
                if self.empty_timers[channel_id] >= 300:
                    try:
                        await channel.delete(reason="TempVC empty for 5 minutes.")
                    except (discord.HTTPException, discord.Forbidden):
                        pass
                    channels_to_remove.add(channel_id)
            else:
                # Reset timer if members are present
                self.empty_timers[channel_id] = 0

        # Clean tracking dictionaries
        for cid in channels_to_remove:
            self.active_channels.pop(cid, None)
            self.empty_timers.pop(cid, None)

    @commands.group(name="tempvc", invoke_without_command=True)
    async def tempvc(self, ctx):
        """TempVC admin management commands."""
        await ctx.send_help(ctx.command)

    @tempvc.command(name="setcategory")
    @checks.admin_or_permissions(manage_channels=True)
    async def set_category(self, ctx, category: discord.CategoryChannel):
        """Set the Discord Category where temp voice channels will be created."""
        await self.config.guild(ctx.guild).category_id.set(category.id)
        await ctx.send(f"✅ TempVC category set to **{category.name}**.")

    @tempvc.command(name="sendpanel")
    @checks.admin_or_permissions(manage_channels=True)
    async def send_panel(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Send the interactive VC Creation Panel embed."""
        target_channel = channel or ctx.channel

        embed = discord.Embed(
            title="🎙️ Voice Channel Generator",
            description=(
                "Click the button below to generate your own personal temporary voice channel!\n\n"
                "**Features:**\n"
                "• Adjust user limits (0–99)\n"
                "• Lock or permit specific members\n"
                "• Auto-deletes 5 minutes after everyone leaves"
            ),
            color=discord.Color.teal()
        )

        view = VCCreationPanelView(self)
        msg = await target_channel.send(embed=embed, view=view)

        await self.config.guild(ctx.guild).panel_channel_id.set(target_channel.id)
        await self.config.guild(ctx.guild).panel_message_id.set(msg.id)

        if target_channel != ctx.channel:
            await ctx.send(f"✅ VC Creation Panel sent to {target_channel.mention}.")
