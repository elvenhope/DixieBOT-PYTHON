from datetime import datetime, timezone
import os
import asyncio
import discord
from discord.ext import commands
from aiohttp import ClientSession
import logging

from config_manager import ConfigManager
from thread_manager import ThreadManager
from database_manager import DatabaseManager

logger = logging.getLogger("modmail")

def configure_logging():
    logging.basicConfig(level=logging.INFO)

temp_dir = "."

CATEGORY_IDS = {
    "contact": 1346881466881146910,
    "trusted": 1346882153279000648,
    "questions": 1402347454438838443,
    "suggestions": 1402347609460576367,
    "partnerships": 1402347709976936591,
    "reports": 1402347829409874032,
    "appeals": 1402347868756643900,
    "ko-fi": 1402348823598203061,
    "nsfw": 1346881386510024745,
}

class ModmailBot(commands.Bot):
    def __init__(self):
        self.config = ConfigManager(self)
        self.config.populate_cache()
        self.confirmed_users = set()

        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.members = True
        intents.dm_messages = True
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents)

        self.session = None
        self.loaded_cogs = [
            "cogs.staff_commands",
            "cogs.category_management",
            "cogs.modmail",
            "cogs.mod"
        ]
        self._connected = asyncio.Event()

        self.guild_id = 1346839676333461625
        self.threads = ThreadManager(self)
        self.db = DatabaseManager(self)

        log_dir = os.path.join(temp_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file_path = os.path.join(log_dir, "modmail.log")
        configure_logging()

    async def on_ready(self):
        logger.info(f"Bot ready as {self.user} (ID: {self.user.id})")
        await self.load_extensions()
        self.loop.create_task(self.timer_task())
        self._connected.set()

    async def timer_task(self):
        await self.wait_until_ready()
        while not self.is_closed():
            timers = await self.db.get_pending_timers()
            for t in timers:
                channel = self.get_channel(t["channel_id"])
                if not channel:
                    continue
                if t["action"] in ("close", "suspend"):
                    if t["action"] == "suspend":
                        await channel.send("⏰ User did not respond. Closing suspended ticket.")
                    # Call close_ticket_now directly on the bot
                    await self.close_ticket_now(channel)

            await asyncio.sleep(60)  # prevent tight loop


    async def close_ticket_now(self, channel):
        await self.db.close_ticket(channel.id, datetime.now(timezone.utc))
        await channel.delete()

    async def load_extensions(self):
        for cog in self.loaded_cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                logger.error(f"Failed to load extension {cog}: {e}")

    def build_embed(self, title, description, color, author=None):
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        if author:
            embed.set_author(name=str(author), icon_url=author.display_avatar.url)
        return embed

    async def on_message(self, message):
        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            await self.handle_user_dm(message)

        await self.process_commands(message)

    async def handle_user_dm(self, message: discord.Message):
        user = message.author
        channel_id = await self.db.get_open_ticket_channel_id(user.id)

        if channel_id:
            # Try to get existing ticket channel
            channel = self.get_channel(channel_id)

            if channel is None:
                # Ticket channel was deleted, close ticket in DB
                await self.db.close_ticket(channel_id)
                self.confirmed_users.discard(user.id)
            else:
                # --- NEW LOGIC: Cancel suspend and notify ---
                await self.db.cancel_ticket_timer(channel_id, "suspend")

                watchers = await self.db.get_watchers(channel_id)
                # ticket = await self.db.get_ticket_by_channel(channel_id)
                # if ticket and ticket["mod_id"]:
                #     watchers.append(ticket["mod_id"])  # include assigned mod

                mentions = []
                for watcher_id in set(watchers):  # deduplicate
                    watcher = self.get_user(watcher_id)
                    if watcher:
                        mentions.append(watcher.mention)

                # print(f"Notifying watchers: {mentions}")

                if len(mentions) > 0:
                    await channel.send(f"🔔 User responded! Notifying: {' '.join(mentions)}")
                    await self.db.remove_watcher(channel_id, watcher_id)  # remove after notifying
                    mentions = []  # clear mentions to avoid duplicate notifications

                # --- END NEW LOGIC ---

                # Forward user message into the ticket channel
                embed = self.build_embed(
                    title="",
                    description=f"**USER MESSAGE:**\n{message.content}",
                    color=discord.Color.blue(),
                    author=user
                )
                await channel.send(embed=embed)
                return  # Don't send welcome menu again

        # No open ticket → send welcome embed + ticket category options
        welcome_embed = self.build_embed(
            title="🎟️ Contact Staff!",
            description=(
                "**Please select the reason for your ticket below:**\n\n"
                "📌 **Reporting a User** – Rule-breaking reports\n"
                "💡 **Suggestions** – Event ideas or server improvement\n"
                "📝 **Appeals** – Appeal a warning\n"
                "🛠️ **Technical Issues** – Channel/reaction issues (not device support)\n"
                "❓ **General Questions** – Ask about server/partnerships\n\n"
                "🍰 **Cheesecake Reminder:**\n"
                "Please do **not spam** staff. Have all necessary materials ready before submitting.\n"
                "Thank you!"
            ),
            color=discord.Color.pink()
        )

        welcome_embed.set_image(
            url="https://media.discordapp.net/attachments/1329869584190406780/1351717260145852458/IMG_5552.png"
        )

        await message.channel.send(embed=welcome_embed, view=TicketCategoryView())



    async def on_guild_channel_delete(self, channel):
        if channel.topic:
            try:
                user_id_str = channel.topic.split("(")[-1].rstrip(")")
                user_id = int(user_id_str)

                channel_id = await self.db.get_open_ticket_channel_id(user_id)
                if channel_id == channel.id:
                    await self.db.close_ticket(user_id)
                    self.confirmed_users.discard(user_id)
                    logger.info(f"Removed ticket for user {user_id} due to channel deletion.")
            except Exception as e:
                logger.warning(f"Failed to parse user ID from channel topic: {e}")

    def run(self):
        async def runner():
            async with self:
                self.session = ClientSession()
                await self.db.setup()
                await self.start(self.config['token'])

        asyncio.run(runner())


class TicketCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.categories = {
            "contact": "📩 Contact Staff",
            "trusted": "✅ Trusted Seller/Buyer",
            "questions": "❓ General Questions",
            "suggestions": "💡 Suggestions",
            "partnerships": "🤝 Partnerships",
            "reports": "🚨 Reports",
            "appeals": "🛑 Appeals",
            "ko-fi": "☕ Ko-Fi Help",
            "nsfw": "🔞 NSFW Access",
        }

        for key, label in self.categories.items():
            self.add_item(TicketCategoryButton(label=label, custom_id=key))


class TicketCategoryButton(discord.ui.Button):
    def __init__(self, label, custom_id):
        super().__init__(label=label, custom_id=custom_id, style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await send_category_details(interaction, self.custom_id)


class ClaimTicketButton(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

        # self.add_item(discord.ui.Button(label="Claim Ticket", style=discord.ButtonStyle.success, custom_id="claim_ticket"))

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.success)
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot: ModmailBot = interaction.client
        mod = interaction.user

        await bot.db.assign_mod_to_ticket(self.channel_id, mod.id, mod.name)

        await interaction.response.send_message(f"✅ You have claimed this ticket, {mod.mention}.", ephemeral=True)

        await interaction.channel.send(
            embed=discord.Embed(
                description=f"👮 Ticket claimed by {mod.mention}.",
                color=discord.Color.orange()
            )
        )

        self.clear_items()
        await interaction.message.edit(view=self)



async def send_category_details(interaction: discord.Interaction, category_key: str):
    details_map = {
        "contact": "**Contact Staff!**\nPlease select the reason for your ticket.",
        "trusted": "**Trusted Seller/Buyer Requirements...**",
        "questions": "**General Questions...**",
        "suggestions": "**Suggestions...**",
        "partnerships": "**Partnership Applications...**",
        "reports": "**Report a User...**",
        "appeals": "**Appeal a Warning...**",
        "ko-fi": "**Ko-Fi Help...**",
        "nsfw": "**NSFW Access Verification...**",
    }

    embed = discord.Embed(
        title="📌 Category Info",
        description=details_map.get(category_key, "No information available."),
        color=discord.Color.purple()
    )

    if category_key == "nsfw":
        embed.set_image(
            url="https://i.imgur.com/TAuTurS.png"
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

    user = interaction.user
    bot: ModmailBot = interaction.client
    guild = bot.get_guild(bot.guild_id)

    existing_channel_id = await bot.db.get_open_ticket_channel_id(user.id)
    if existing_channel_id:
        return  # user already has an open ticket

    category_id = CATEGORY_IDS.get(category_key)
    if not category_id:
        return

    discord_category = guild.get_channel(category_id)
    if not isinstance(discord_category, discord.CategoryChannel):
        return

    ticket_channel = await guild.create_text_channel(
        name=f"dx-{user.name}",
        category=discord_category,
        topic=f"Ticket for {user.name} ({user.id})"
    )

    await bot.db.create_ticket_entry(user, ticket_channel, category_id, category_key)

    embed = discord.Embed(
        description="🎫 A new ticket has been created.\nClick **Claim Ticket** below to take responsibility.",
        color=discord.Color.blurple()
    )

    await ticket_channel.send(
        content=f"📩 New ticket from {user.mention} (ID: {user.id}) - Category: `{category_key}`\n<@&1392477456232878242>",
        embed=embed,
        view=ClaimTicketButton(ticket_channel.id)
    )

    try:
        await user.send(
            embed=discord.Embed(
                title="✅ Ticket Created",
                description="Your ticket has been opened. Please describe your issue or request here.",
                color=discord.Color.green()
            )
        )
    except discord.Forbidden:
        pass


if __name__ == "__main__":
    bot = ModmailBot()
    bot.run()
