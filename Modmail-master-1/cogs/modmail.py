import discord
from discord.ext import commands
import asyncio
import io
from datetime import datetime, timedelta, timezone


class Modmail(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_id = 1346839676333461625
        self.category_id = 1386412081246200000
        self.log_channel_id = 1352669054346854502

        self.open_tickets = {}
        self.delayed_closures = {}
        self.suspended_tickets = {}
        self.notify_watchers = {}

        self.ticket_category_ids = {
            1346881466881146910,  # contact
            1346882153279000648,  # trusted
            1402347454438838443,  # questions
            1402347609460576367,  # suggestions
            1402347709976936591,  # partnerships
            1402347829409874032,  # reports
            1402347868756643900,  # appeals
            1402348823598203061,  # ko-fi
            1346881386510024745,  # nsfw
            1346882435400466495   # tech
        }

    async def generate_transcript(self, channel):
        topic = channel.topic or ""
        user_id = None
        if "(" in topic and ")" in topic:
            try:
                user_id = int(topic.split("(")[-1].split(")")[0])
            except ValueError:
                pass

        transcript = ""
        async for msg in channel.history(limit=None, oldest_first=True):
            # Only messages from user or staff with manage_channels permission
            if user_id and (msg.author.id == user_id or msg.author.guild_permissions.manage_channels):
                timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                author = msg.author.name

                # Start with the plain content if any
                content = msg.clean_content or ""

                # Extract embed text if any
                for embed in msg.embeds:
                    # Extract the title and description if available
                    if embed.title:
                        content += f"\n[Embed Title] {embed.title}"
                    if embed.description:
                        content += f"\n{embed.description}"

                    # Extract fields if any
                    for field in embed.fields:
                        content += f"\n{field.name}: {field.value}"

                    # Optionally, you can add footer, author, or other embed parts if needed

                if not content.strip():
                    content = "[no text]"

                transcript += f"[{timestamp}] {author}: {content}\n"

        if not transcript:
            transcript = "No messages found between user and staff."

        transcript_file = discord.File(io.BytesIO(transcript.encode()), filename="transcript.txt")
        return transcript_file


    @commands.command(name="cancelclose")
    @commands.has_permissions(manage_channels=True)
    async def cancel_close(self, ctx):
        await self.bot.db.cancel_ticket_timer(ctx.channel.id, "close")
        embed = discord.Embed(
            description="❌ Scheduled close canceled.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        await ctx.send(embed=embed)

    @commands.command(name='close')
    @commands.has_permissions(manage_channels=True)
    async def close_ticket(self, ctx, time: str = None):
        if not ctx.channel.category or ctx.channel.category.id not in self.ticket_category_ids:
            embed = discord.Embed(
                description="This command can only be used in ticket channels.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.send(embed=embed)
            return

        if not time:
            embed = discord.Embed(
                description="Usage: `!close hh:mm` (e.g. `!close 1:30`)",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.send(embed=embed)
            return

        try:
            hours, minutes = map(int, time.split(":"))
            delay = hours * 3600 + minutes * 60
        except ValueError:
            embed = discord.Embed(
                description="Invalid format. Use `hh:mm`.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.send(embed=embed)
            return

        topic = ctx.channel.topic or ""
        user_id = int(topic.split("(")[-1].split(")")[0])

        execute_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        await self.bot.db.add_ticket_timer(ctx.channel.id, user_id, "close", execute_at)

        embed = discord.Embed(
            description=f"⏲️ Ticket will close in {hours}h {minutes}m unless canceled with `!cancelclose`.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        await ctx.send(embed=embed)

    @commands.command(name='log')
    @commands.has_permissions(manage_channels=True)
    async def log_ticket(self, ctx):
        if not ctx.channel.category or ctx.channel.category.id not in self.ticket_category_ids:
            embed = discord.Embed(
                description="This command can only be used in ticket channels.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.send(embed=embed)
            return

        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            transcript = await self.generate_transcript(ctx.channel)
            embed = discord.Embed(
                title="Transcript generated",
                description=f"Ticket manually logged: `{ctx.channel.name}` by {ctx.author.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            await log_channel.send(embed=embed, file=transcript)
            confirm_embed = discord.Embed(
                description="Ticket has been logged with transcript.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.send(embed=confirm_embed)

    @commands.command(name="suspend")
    @commands.has_permissions(manage_channels=True)
    async def suspend_ticket(self, ctx):
        try:
            delay = 86400
        except ValueError:
            embed = discord.Embed(
                description="Invalid format. Use `hh:mm`.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.send(embed=embed)
            return

        topic = ctx.channel.topic or ""
        user_id = int(topic.split("(")[-1].split(")")[0])

        execute_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        await self.bot.db.add_ticket_timer(ctx.channel.id, user_id, "suspend", execute_at)

        embed = discord.Embed(
            description=f"🚫 Ticket suspended. Will close in {hours}h {minutes}m if user does not reply.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        await ctx.send(embed=embed)

    async def _delayed_suspend(self, channel, delay):
        await asyncio.sleep(delay)
        if channel.id in self.suspended_tickets:
            embed = discord.Embed(
                description="User did not respond in time. Closing ticket.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await channel.send(embed=embed)

            topic = channel.topic or ""
            user_id = None
            if "(" in topic and ")" in topic:
                try:
                    user_id = int(topic.split("(")[-1].split(")")[0])
                except ValueError:
                    pass

            if user_id and user_id in self.open_tickets:
                del self.open_tickets[user_id]

            log_channel = self.bot.get_channel(self.log_channel_id)
            if log_channel:
                transcript = await self.generate_transcript(channel)
                embed = discord.Embed(
                    title="Transcript generated",
                    description=f"Ticket auto-closed (no response): `{channel.name}`",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                await log_channel.send(embed=embed, file=transcript)

            await channel.delete()
            del self.suspended_tickets[channel.id]

    @commands.command(name="notifyme")
    @commands.has_permissions(manage_channels=True)
    async def notify_me(self, ctx):
        watchers = await self.bot.db.get_watchers(ctx.channel.id)

        if ctx.author.id in watchers:
            embed = discord.Embed(
                description="⚠️ You're already subscribed to notifications for this ticket.",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
        else:
            await self.bot.db.add_watcher(ctx.channel.id, ctx.author.id)
            embed = discord.Embed(
                description="✅ You'll be notified when the user responds.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )

        await ctx.send(embed=embed)

    @commands.command(name="cancelnotifyme")
    @commands.has_permissions(manage_channels=True)
    async def cancel_notify_me(self, ctx):
        watchers = await self.bot.db.get_watchers(ctx.channel.id)

        if ctx.author.id not in watchers:
            embed = discord.Embed(
                description="⚠️ You are not subscribed to notifications for this ticket.",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
        else:
            await self.bot.db.remove_watcher(ctx.channel.id, ctx.author.id)
            embed = discord.Embed(
                description="❌ You will no longer be notified when the user responds.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )

        await ctx.send(embed=embed)


# Required for loading as an extension
async def setup(bot):
    await bot.add_cog(Modmail(bot))
