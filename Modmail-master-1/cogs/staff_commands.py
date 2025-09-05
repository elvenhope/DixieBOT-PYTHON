from discord.ext import commands, tasks
from discord import CategoryChannel, TextChannel
import discord
import re
import io
import os
import json
from datetime import datetime, timedelta, timezone
from bot import ClaimTicketButton

TRANSCRIPT_DIR = "logs"
PREMADE_PATH = "replies.json"

ALLOWED_CATEGORIES = {
    1346881466881146910, 1346882153279000648, 1402347454438838443,
    1402347609460576367, 1402347709976936591, 1402347829409874032,
    1402347868756643900, 1402348823598203061, 1346882435400466495
}
DISALLOWED_CATEGORY = 1346881386510024745


class StaffCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # self.premade = self.load_premade()

    # def load_premade(self):
    #     if not os.path.exists(PREMADE_PATH):
    #         return {}
    #     with open(PREMADE_PATH, "r") as f:
    #         return json.load(f)

    # def save_premade(self):
    #     with open(PREMADE_PATH, "w") as f:
    #         json.dump(self.premade, f, indent=4)

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

    async def get_user_from_channel(self, channel: discord.TextChannel):
        if channel.topic:
            match = re.search(r"\((\d{17,20})\)", channel.topic)
            if match:
                user_id = int(match.group(1))
                return self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        return None

    @commands.command(name="dxadd")
    @commands.has_permissions(manage_guild=True)  # or manage_channels, adjust perms as needed
    async def add_dx_response(self, ctx, key: str, *, response: str):
        existing = await self.bot.db.get_dx_response(key)
        if existing:
            await ctx.send(embed=self.build_embed(
                "Add Failed",
                f"Response with key `{key}` already exists.",
                discord.Color.red()
            ))
            return
        await self.bot.db.add_dx_response(key, response)
        await ctx.send(embed=self.build_embed(
            "Premade Response Added",
            f"Key `{key}` added with response:\n{response}",
            discord.Color.green()
        ))

    @commands.command(name="dxremove")
    @commands.has_permissions(manage_guild=True)
    async def remove_dx_response(self, ctx, key: str):
        existing = await self.bot.db.get_dx_response(key)
        if not existing:
            await ctx.send(embed=self.build_embed(
                "Remove Failed",
                f"No response found for key `{key}`.",
                discord.Color.red()
            ))
            return
        await self.bot.db.remove_dx_response(key)
        await ctx.send(embed=self.build_embed(
            "Premade Response Removed",
            f"Key `{key}` has been removed.",
            discord.Color.green()
        ))

    @commands.command(name="dx")
    async def list_dx_responses(self, ctx):
        responses = await self.bot.db.get_all_dx_responses()
        if not responses:
            await ctx.send(embed=self.build_embed(
                "No Premade Responses",
                "No premade responses found in the database.",
                discord.Color.red()
            ))
            return
        # Only show the keys, not the full responses
        keys = "\n".join(f"`{r['key']}`" for r in responses)
        await ctx.send(embed=self.build_embed(
            "Available Premade Response Keys",
            keys,
            discord.Color.purple()
        ))
        return

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.content.startswith("!") or message.author.bot:
            # print("asdas")
            return

        ctx = await self.bot.get_context(message)
        cmd_key = message.content[1:].split()[0]

        # print(f"Command key: {cmd_key}")

        # Only handle premade responses in ticket channels starting with "dx-"
        if isinstance(ctx.channel, discord.TextChannel) and ctx.channel.name.startswith("dx-"):
            response = await self.bot.db.get_dx_response(cmd_key)
            if response:
                user = await self.get_user_from_channel(ctx.channel)
                if not user:
                    await ctx.send("Unable to find the user from this ticket channel.")
                    return

                try:
                    embed_user = self.build_embed(
                        "",
                        response,
                        discord.Color.orange(),
                        self.bot.user
                    )
                    user_msg = await user.send(embed=embed_user)

                    embed_staff = self.build_embed(
                        f"Premade Reply `{cmd_key}` Sent",
                        response,
                        discord.Color.green(),
                        ctx.author
                    )
                    embed_staff.set_footer(text=f"DixieMsgCode:{user_msg.id}")
                    await ctx.channel.send(embed=embed_staff)
                except Exception as e:
                    await ctx.send(embed=self.build_embed(
                        "Failed to Send",
                        str(e),
                        discord.Color.red()
                    ))
                return

        # If no DB premade response found, continue processing other commands normally
        # await self.bot.process_commands(message)

    @commands.command(name="r")
    async def reply_to_user(self, ctx, *, message: str = ""):
        if isinstance(ctx.channel, TextChannel):
            user = await self.get_user_from_channel(ctx.channel)
            if not user:
                await ctx.send("Unable to find the user from this ticket channel.")
                return

            try:
                # Take the first image attachment for the embed, if any
                image_url = None
                if ctx.message.attachments:
                    for attachment in ctx.message.attachments:
                        if attachment.content_type and attachment.content_type.startswith("image/"):
                            image_url = attachment.url
                            break  # only the first image

                # --- DM embed to user ---
                user_embed = self.build_embed(
                    title="",
                    description=message,
                    color=discord.Color.orange(),
                    author=self.bot.user
                )
                if image_url:
                    user_embed.set_image(url=image_url)

                user_msg = await user.send(embed=user_embed)

                # --- Staff embed in ticket channel ---
                staff_embed = self.build_embed(
                    title="",
                    description="STAFF RESPONSE:\n" + message,
                    color=discord.Color.green(),
                    author=ctx.author
                )
                if image_url:
                    staff_embed.set_image(url=image_url)
                staff_embed.set_footer(text=f"DixieMsgCode:{user_msg.id}")

                await ctx.channel.send(embed=staff_embed)

            except Exception as e:
                await ctx.send(embed=self.build_embed(
                    title="Error",
                    description=f"Failed to send reply: {e}",
                    color=discord.Color.red()
                ))
        else:
            await ctx.send("This command can only be used in a ticket channel.")

    @commands.command(name="re")
    async def edit_reply(self, ctx, *, new_message: str = ""):
        try:
            if not ctx.message.reference or not isinstance(ctx.message.reference.resolved, discord.Message):
                await ctx.send(embed=self.build_embed(
                    title="Error",
                    description="You must reply to the old bot message containing the DixieMsgCode.",
                    color=discord.Color.red()
                ))
                return

            replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)

            msg_id = (
                replied_msg.embeds[0].footer.text.replace("DixieMsgCode:", "").strip()
                if replied_msg.embeds and replied_msg.embeds[0].footer and "DixieMsgCode:" in replied_msg.embeds[0].footer.text
                else None
            )
            if not msg_id:
                await ctx.send(embed=self.build_embed(
                    title="Error",
                    description="No valid DixieMsgCode found in the replied message.",
                    color=discord.Color.red()
                ))
                return

            user = await self.get_user_from_channel(ctx.channel)
            if not user:
                await ctx.send("Unable to find the user from this ticket channel.")
                return

            # Fetch the old DM message
            dm_channel = await user.create_dm()
            target_msg = await dm_channel.fetch_message(int(msg_id))
            old_embed = target_msg.embeds[0]

            # Preserve existing image unless a new one is provided
            image_url = old_embed.image.url if old_embed.image else None
            if ctx.message.attachments:
                for attachment in ctx.message.attachments:
                    if attachment.content_type and attachment.content_type.startswith("image/"):
                        image_url = attachment.url
                        break

            # Use old text if no new text provided
            description = new_message if new_message.strip() else old_embed.description

            # --- Update DM embed ---
            new_embed = discord.Embed(
                title=old_embed.title,
                description=description,
                color=discord.Color.orange(),
                timestamp=old_embed.timestamp
            )
            if old_embed.author:
                new_embed.set_author(name=old_embed.author.name, icon_url=old_embed.author.icon_url)
            if old_embed.footer:
                new_embed.set_footer(text=old_embed.footer.text, icon_url=old_embed.footer.icon_url)
            if image_url:
                new_embed.set_image(url=image_url)

            await target_msg.edit(embed=new_embed)

            # --- Update staff embed in ticket channel ---
            staff_embed = discord.Embed(
                title=replied_msg.embeds[0].title,
                description=description,
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            if replied_msg.embeds[0].author:
                staff_embed.set_author(
                    name=replied_msg.embeds[0].author.name,
                    icon_url=replied_msg.embeds[0].author.icon_url
                )
            if replied_msg.embeds[0].footer:
                staff_embed.set_footer(
                    text=replied_msg.embeds[0].footer.text,
                    icon_url=replied_msg.embeds[0].footer.icon_url
                )
            if image_url:
                staff_embed.set_image(url=image_url)

            await replied_msg.edit(embed=staff_embed)

            # Delete the staff command message
            await ctx.message.delete()

        except Exception as e:
            await ctx.send(embed=self.build_embed(
                title="Edit Failed",
                description=str(e),
                color=discord.Color.red()
            ))





    @commands.command(name="transfer")
    @commands.has_permissions(manage_channels=True)
    async def transfer_ticket(self, ctx, new_mod: discord.Member):
        if ctx.channel.category_id is None:
            await ctx.send("❌ This command can only be used inside a ticket channel.")
            return

        channel_id = ctx.channel.id
        new_mod_id = new_mod.id
        new_mod_username = new_mod.name

        # Update the ticket assignment in DB
        await self.bot.db.assign_mod_to_ticket(channel_id, new_mod_id, new_mod_username)

        # Notify both parties
        await ctx.send(
            f"✅ Ticket has been transferred to {new_mod.mention}.\n"
            f"They are now responsible for this ticket."
        )
    
    @commands.command(name="contact")
    @commands.has_permissions(manage_guild=True)
    async def contact_user(self, ctx, user_id: int, *, reason: str = "No reason provided"):
        """Open a ticket with a user from staff side (reverse modmail)."""
        try:
            user = await self.bot.fetch_user(user_id)
            if not user:
                await ctx.send(embed=self.build_embed(
                    "Contact Failed",
                    f"User with ID `{user_id}` could not be found.",
                    discord.Color.red(),
                    ctx.author
                ))
                return

            guild = self.bot.get_guild(1346839676333461625)
            category = guild.get_channel(1346881466881146910)
            if not category or not isinstance(category, discord.CategoryChannel):
                await ctx.send(embed=self.build_embed(
                    "Error",
                    "Ticket category could not be found.",
                    discord.Color.red(),
                    ctx.author
                ))
                return

            # Create the channel
            channel_name = f"dx-{user.name}".replace(" ", "-").lower()
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Contact ticket with {user} ({user.id})"
            )

            # Save ticket in DB
            await self.bot.db.create_ticket_entry(
                user=user,
                channel=ticket_channel,
                category_id=category.id,
                ticket_type="contact"
            )


            # Notify staff
            staff_embed = self.build_embed(
                "Contact Ticket Opened",
                f"A new contact ticket has been opened with {user.mention}.\nReason: {reason}",
                discord.Color.green(),
                ctx.author
            )
            await ticket_channel.send(embed=staff_embed, view=ClaimTicketButton(ticket_channel.id))

            # DM user
            try:
                user_embed = self.build_embed(
                    "Staff Contact",
                    f"Our staff has opened a ticket with you:\n\n{reason}",
                    discord.Color.orange(),
                    self.bot.user
                )
                await user.send(embed=user_embed)
            except discord.Forbidden:
                await ticket_channel.send(embed=self.build_embed(
                    "DM Failed",
                    "❌ Could not DM the user (they may have DMs disabled).",
                    discord.Color.red()
                ))

            await ctx.send(embed=self.build_embed(
                "Success",
                f"Ticket opened with {user.mention} in {ticket_channel.mention}.",
                discord.Color.green(),
                ctx.author
            ))

        except Exception as e:
            await ctx.send(embed=self.build_embed(
                "Error",
                str(e),
                discord.Color.red(),
                ctx.author
            ))


       


class TranscriptManager:
    @staticmethod
    def save_transcript(user_id: int, channel: discord.TextChannel, messages):
        transcript_lines = []
        for msg in messages:
            author = f"{msg.author.name}#{msg.author.discriminator}"
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = msg.content.strip()
            content = re.sub(r"DixieMsgCode:\s*\\d+", "", content)
            transcript_lines.append({
                "timestamp": timestamp,
                "author": author,
                "content": content
            })

        save_path = os.path.join(TRANSCRIPT_DIR, f"{user_id}.json")
        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []

        data.append({
            "channel": channel.name,
            "category_id": channel.category_id,
            "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "messages": transcript_lines
        })

        os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def load_transcripts(user_id: int):
        path = os.path.join(TRANSCRIPT_DIR, f"{user_id}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

class StaffTranscriptCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_user_from_channel(self, channel: discord.TextChannel):
        if channel.topic:
            match = re.search(r"\\((\\d{17,20})\\)", channel.topic)
            if match:
                user_id = int(match.group(1))
                return self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        return None

    @commands.command(name='transcript')
    async def transcript_command(self, ctx, user_id: int = None):
        if user_id:
            data = TranscriptManager.load_transcripts(user_id)
            if not data:
                await ctx.send(f"No transcripts found for user ID `{user_id}`.")
                return

            for i, entry in enumerate(data):
                content = "\n".join(f"[{m['timestamp']}] {m['author']}: {m['content']}" for m in entry['messages'])
                file = discord.File(io.BytesIO(content.encode()), filename=f"ticket_{i+1}.txt")
                await ctx.send(f"Transcript from `{entry['channel']}` saved on `{entry['saved_at']}`:", file=file)
        else:
            # Save the transcript of the current channel (if allowed)
            if not isinstance(ctx.channel, discord.TextChannel):
                await ctx.send("This command must be run in a text channel.")
                return

            if ctx.channel.category_id == DISALLOWED_CATEGORY:
                await ctx.send("Transcript saving is disabled for this category.")
                return

            if ctx.channel.category_id not in ALLOWED_CATEGORIES:
                await ctx.send("This category is not configured for automatic transcript saving.")
                return

            user = await self.get_user_from_channel(ctx.channel)
            if not user:
                await ctx.send("User could not be resolved from the channel topic.")
                return

            messages = [msg async for msg in ctx.channel.history(limit=None, oldest_first=True)]
            TranscriptManager.save_transcript(user.id, ctx.channel, messages)
            await ctx.send(f"Transcript has been saved for user `{user.name}`.")

async def setup(bot):
    await bot.add_cog(StaffCommands(bot))
