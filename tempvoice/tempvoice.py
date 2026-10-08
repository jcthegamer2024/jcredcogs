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


class VCCreationModal(discord.ui.Modal, title="Create Your Voice Channel"):
    channel_name = discord.ui.TextInput(
        label="Voice Channel Name",
        placeholder="Enter channel name (e.g. Chill Zone)...",
        min_length=1,
        max_length=32,
        required=True,
    )
    limit = discord.ui.TextInput(
        label="User Limit (0 for unlimited)",
        placeholder="Enter a number between 0 and 99...",
        min_length=1,
        max_length=2,
        default="0",
        required=False,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        category_id = await self.cog.config.guild(guild).category_id()

        if not category_id:
            await interaction.response.send_message("❌ TempVC category is not configured. An admin must run `!tempvc setcategory`.", ephemeral=True)
            return

        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ Configured category was not found.", ephemeral=True)
            return

        # Validate limit input
        user_limit = 0
        if self.limit.value:
            try:
                user_limit = int(self.limit.value)
                if not (0 <= user_limit <= 99):
                    raise ValueError
            except ValueError:
                await interaction.response.send_message("❌ Please enter a valid user limit between **0** and **99**.", ephemeral=True)
                return

        # Check if user already owns an active voice channel
        for vc_id, owner_id in self.cog.active_channels.items():
            if owner_id == interaction.user.id:
                existing_vc = guild.get_channel(vc_id)
                if existing_vc:
                    await interaction.response.send_message(f"❌ You already have an active channel: {existing_vc.mention}", ephemeral=True)
                    return

        # Create Voice Channel
        new_vc = await guild.create_voice_channel(
            name=f"🔊 {self.channel_name.value}",
            category=category,
            user_limit=user_limit,
            reason=f"TempVC created by {interaction.user}"
        )

        # Track created channel
        self.cog.active_channels[new_vc.id] = interaction.user.id

        # Send internal control panel embed inside the voice channel's text chat
        control_embed = discord.Embed(
            title=f"🎙️ {new_vc.name}",
            description=(
                "Welcome to your temporary voice channel!\n\n"
                "**Controls:**\n"
                "• ✏️ **Rename VC:** Change your channel's name.\n"
                "• 🔢 **Set Limit:** Change the maximum users allowed (0-99).\n"
                "• 🔐 **Allow Users:** Pick specific members permitted to join.\n"
                "• 🔒 **Lock / Unlock:** Toggle general access for everyone.\n"
                "• 🗑️ **End VC:** Immediately delete this voice channel.\n\n"
                "⚠️ *Note: This channel will automatically delete after 5 minutes if left empty.*"
            ),
            color=discord.Color.teal()
        )
        control_view = VCControlView(self.cog, new_vc, interaction.user)
        await new_vc.send(embed=control_embed, view=control_view)

        await interaction.response.send_message(
            f"✅ Created your voice channel: {new_vc.mention}\n"
            f"💡 *Tip: Open your new voice channel's text chat to access settings like renaming, locking, or deleting it!*",
            ephemeral=True
        )


class RenameVCModal(discord.ui.Modal, title="Rename Voice Channel"):
    new_name = discord.ui.TextInput(
        label="New Voice Channel Name",
        placeholder="Enter a new name...",
        min_length=1,
        max_length=32,
        required=True,
    )

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        formatted_name = f"🔊 {self.new_name.value.strip()}"
        await self.channel.edit(name=formatted_name)
        await interaction.response.send_message(
            f"✅ Channel renamed to **{formatted_name}**.", ephemeral=True
        )


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

    @discord.ui.button(label="Rename VC", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_vc(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Only the channel creator can modify settings.", ephemeral=True)
            return
        await interaction.response.send_modal(RenameVCModal(self.cog, self.channel))

    @discord.ui.button(label="Set Limit", style=discord.ButtonStyle.secondary, emoji="🔢")
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Only the channel creator can modify settings.", ephemeral=True)
            return
        await interaction.response.send_modal(UserLimitModal(self.cog, self.channel))

    @discord.ui.button(label="Allow Users", style=discord.ButtonStyle.secondary, emoji="🔐")
    async def allow_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Only the channel creator can modify settings.", ephemeral=True)
            return
        view = AccessControlView(self.cog, self.channel)
        await interaction.response.send_message("Select members permitted to join your channel:", view=view, ephemeral=True)

    @discord.ui.button(label="Lock / Unlock", style=discord.ButtonStyle.secondary, emoji="🔒")
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Only the channel creator can modify settings.", ephemeral=True)
            return

        current_overwrite = self.channel.overwrites_for(interaction.guild.default_role)
        if current_overwrite.connect is False:
            await self.channel.set_permissions(interaction.guild.default_role, connect=None)
            await interaction.response.send_message("🔓 Channel is now **unlocked** for everyone.", ephemeral=True)
        else:
            await self.channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 Channel is now **locked**. Use **Allow Users** to grant access.", ephemeral=True)

    @discord.ui.button(label="End VC", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def end_vc(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Only the channel creator can end this voice channel.", ephemeral=True)
            return

        await interaction.response.send_message("🗑️ Ending voice channel now...", ephemeral=True)
        
        self.cog.active_channels.pop(self.channel.id, None)
        self.cog.empty_timers.pop(self.channel.id, None)

        try:
            await self.channel.delete(reason=f"TempVC manually ended by owner {interaction.user}")
        except (discord.HTTPException, discord.Forbidden):
            pass


class VCCreationPanelView(discord.ui.View):
    """Persistent view attached to the main public VC Creation Panel embed."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Create Voice Channel", style=discord.ButtonStyle.success, emoji="➕", custom_id="tempvc_create_btn")
    async def create_vc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VCCreationModal(self.cog))


class TempVoice(commands.Cog):
    """Dynamic voice channel creator with interactive controls and 5-minute cleanup logic."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8473629101, force_registration=True)
        self.config.register_guild(**DEFAULT_GUILD)

        self.active_channels: Dict[int, int] = {}
        self.empty_timers: Dict[int, int] = {}

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

            if not channel or not isinstance(channel, discord.VoiceChannel):
                channels_to_remove.add(channel_id)
                continue

            if len(channel.members) == 0:
                self.empty_timers[channel_id] = self.empty_timers.get(channel_id, 0) + 30

                if self.empty_timers[channel_id] >= 300:
                    try:
                        await channel.delete(reason="TempVC empty for 5 minutes.")
                    except (discord.HTTPException, discord.Forbidden):
                        pass
                    channels_to_remove.add(channel_id)
            else:
                self.empty_timers[channel_id] = 0

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
                "Click the button below to generate your personal temporary voice channel!\n\n"
                "**How it works:**\n"
                "1. Click **Create Voice Channel** and enter your desired channel name and limit.\n"
                "2. Join your new voice channel.\n"
                "3. Open the **integrated text chat inside your voice channel** to access all controls:\n"
                "   • ✏️ **Rename VC** | 🔢 **Set Limit** | 🔐 **Allow Users**\n"
                "   • 🔒 **Lock / Unlock** | 🗑️ **End VC** (Immediate Delete)\n\n"
                "⚠️ *Channels delete automatically after 5 minutes of inactivity.*"
            ),
            color=discord.Color.teal()
        )

        view = VCCreationPanelView(self)
        msg = await target_channel.send(embed=embed, view=view)

        await self.config.guild(ctx.guild).panel_channel_id.set(target_channel.id)
        await self.config.guild(ctx.guild).panel_message_id.set(msg.id)

        if target_channel != ctx.channel:
            await ctx.send(f"✅ VC Creation Panel sent to {target_channel.mention}.")
