import sys
import discord
from discord.ext import commands
from datetime import timedelta, datetime, timezone
import mysql.connector
from mysql.connector import Error
from discord.utils import utcnow
import os
import asyncio


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from dbconnMOD import add_mod_log, get_warnings, remove_warning, get_notes, add_note_to_db

JRMOD_ROLE_ID = int(os.getenv('JRMOD_ROLE_ID', 0))
MODS_ROLE_ID = int(os.getenv('MODS_ROLE_ID', 0))
ADMINS_ROLE_ID = int(os.getenv('ADMINS_ROLE_ID', 0))
CO_OWNERS_ROLE_ID = int(os.getenv('CO_OWNERS_ROLE_ID', 0))
OWNERS_ROLE_ID = int(os.getenv('OWNERS_ROLE_ID', 0))
BOT_MANAGER_ID = int(os.getenv('BOT_MANAGER_ID', 0))
print(f"Loaded Role IDs: {JRMOD_ROLE_ID}, {MODS_ROLE_ID}, {ADMINS_ROLE_ID}, {CO_OWNERS_ROLE_ID}, {OWNERS_ROLE_ID}, {BOT_MANAGER_ID}")

warnings = {"minor": {}, "major": {}}
todo_lists = {}

def get_permissions(permissions):
    return [perm.replace("_", " ").title() for perm, value in permissions if value]

class Mod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # !purge <count>
    @commands.command(name="purge")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, count: int):
        if count < 1 or count > 100:
            await ctx.send(embed=discord.Embed(description="Please provide a number between 1 and 100.", color=discord.Color.red()))
            return
        deleted = await ctx.channel.purge(limit=count)
        embed = discord.Embed(description=f"🧹 Purged {len(deleted)} messages.", color=discord.Color.green())
        await ctx.send(embed=embed, delete_after=5)

    # !slow <duration> <unit>
    @commands.command(name="slow")
    @commands.has_permissions(manage_channels=True)
    async def slow(self, ctx, duration: int, unit: str):
        unit = unit.lower()
        seconds = 0
        if unit in ["second", "seconds"]:
            seconds = duration
        elif unit in ["minute", "minutes"]:
            seconds = duration * 60
        elif unit in ["hour", "hours"]:
            seconds = duration * 3600
        elif unit in ["day", "days"]:
            seconds = duration * 86400
        else:
            await ctx.send(embed=discord.Embed(description="Invalid unit. Use seconds, minutes, hours, or days.", color=discord.Color.red()))
            return
        if seconds > 21600:
            await ctx.send(embed=discord.Embed(description="Slowmode cannot exceed 6 hours (21600 seconds).", color=discord.Color.red()))
            return
        await ctx.channel.edit(slowmode_delay=seconds)
        embed = discord.Embed(description=f"🐢 Slowmode set to {duration} {unit}.", color=discord.Color.orange())
        await ctx.send(embed=embed)

    # !unban <userID> <reason>
    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason: str):
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        embed = discord.Embed(title="User Unbanned", color=discord.Color.green())
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=True)
        embed.add_field(name="Unbanned by", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)
        add_mod_log(user.id, reason, ctx.author.id, "unban")

    # !timeremove <userID>
    @commands.command(name="timeremove")
    @commands.has_permissions(moderate_members=True)
    async def timeremove(self, ctx, user_id: int):
        member = ctx.guild.get_member(user_id)
        if not member:
            await ctx.send(embed=discord.Embed(description="User not found in this server.", color=discord.Color.red()))
            return
        await member.edit(timed_out_until=None)
        embed = discord.Embed(description=f"⏱️ Timeout removed for {member.mention}.", color=discord.Color.green())
        await ctx.send(embed=embed)
        add_mod_log(member.id, "Timeout removed", ctx.author.id, "timeremove")

    # !todo <message>
    @commands.command(name="todo")
    async def todo(self, ctx, *, message: str):
        user_id = ctx.author.id
        if user_id not in todo_lists:
            todo_lists[user_id] = []
        todo_lists[user_id].append({"task": message, "created": utcnow()})
        embed = discord.Embed(description=f"📝 Added to your to-do list: `{message}`", color=discord.Color.blue())
        await ctx.send(embed=embed)

    # !whois <userID>
    @commands.command(name="whois")
    async def whois(self, ctx, user_id: int = None):
        member = None
        user = None
        if user_id:
            member = ctx.guild.get_member(user_id)
            if not member:
                try:
                    user = await self.bot.fetch_user(user_id)
                except Exception:
                    await ctx.send(embed=discord.Embed(description="User not found.", color=discord.Color.red()))
                    return
        else:
            member = ctx.author

        if member:
            username = member.name
            user_id = member.id
            created_at = member.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            joined_at = member.joined_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            roles = ", ".join([role.mention for role in member.roles if role.name != "@everyone"])
            minor_warnings, major_warnings = get_warnings(user_id)
            notes = get_notes(user_id)
        else:
            username = user.name
            user_id = user.id
            created_at = user.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            joined_at = "Not in server"
            roles = "Not in server"
            minor_warnings, major_warnings = get_warnings(user_id)
            notes = get_notes(user_id)

        embed = discord.Embed(title=f"User Info - {username}", color=discord.Color.blue())
        if member and member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        elif user and user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        embed.add_field(name="Username", value=username, inline=True)
        embed.add_field(name="User ID", value=user_id, inline=True)
        embed.add_field(name="Account Created", value=created_at, inline=False)
        embed.add_field(name="Joined Server", value=joined_at, inline=False)
        embed.add_field(name="Roles", value=roles if roles else "None", inline=False)
        embed.add_field(name="Minor Warnings", value=str(len(minor_warnings)), inline=True)
        embed.add_field(name="Major Warnings", value=str(len(major_warnings)), inline=True)
        if notes:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="View Notes", style=discord.ButtonStyle.secondary, custom_id=f"view_notes_{user_id}"))
            embed.add_field(name="Mod Notes", value="Click the button below to view notes.", inline=False)
            await ctx.send(embed=embed, view=view)
        else:
            embed.add_field(name="Mod Notes", value="None", inline=False)
            await ctx.send(embed=embed)

    # !wlist <user_ID>
    @commands.command(name="wlist")
    async def wlist(self, ctx, user_id: int):
        minor_warnings, major_warnings = get_warnings(user_id)
        embed = discord.Embed(title=f"Warnings for <@{user_id}>", color=discord.Color.orange())

        # Minor warnings
        if minor_warnings:
            value = "\n".join(
                f"{i+1}. [{w['log_id']}] {w['reason']} - by <@{w['mod_id']}> - {w['date'].strftime('%d/%m/%Y')}"
                for i, w in enumerate(minor_warnings)
            )
            embed.add_field(name="Minor Warnings", value=value, inline=False)
        else:
            embed.add_field(name="Minor Warnings", value="None", inline=False)

        # Major warnings
        if major_warnings:
            value = "\n".join(
                f"{i+1}. [{w['log_id']}] {w['reason']} - by <@{w['mod_id']}> - {w['date'].strftime('%d/%m/%Y')}"
                for i, w in enumerate(major_warnings)
            )
            embed.add_field(name="Major Warnings", value=value, inline=False)
        else:
            embed.add_field(name="Major Warnings", value="None", inline=False)

        await ctx.send(embed=embed)


    # !note <user_ID> <message>
    @commands.command(name="note")
    @commands.has_any_role(MODS_ROLE_ID, ADMINS_ROLE_ID, CO_OWNERS_ROLE_ID, OWNERS_ROLE_ID, BOT_MANAGER_ID)
    async def note(self, ctx, user_id: int, *, message: str):
        if add_note_to_db(user_id, message):
            await ctx.send(embed=discord.Embed(description=f"✅ Added note for <@{user_id}>.", color=discord.Color.green()))
        else:
            await ctx.send(embed=discord.Embed(description=f"❌ Failed to add note.", color=discord.Color.red()))

    # !timeout <userID> <duration> <unit> <reason>
    @commands.command(name="timeout")
    @commands.has_any_role(JRMOD_ROLE_ID, MODS_ROLE_ID, ADMINS_ROLE_ID, CO_OWNERS_ROLE_ID, OWNERS_ROLE_ID, BOT_MANAGER_ID)
    async def timeout(self, ctx, user_id: int, duration: int, unit: str, *, reason="No reason provided"):
        member = ctx.guild.get_member(user_id)
        if not member:
            await ctx.send(embed=discord.Embed(description="User not found in this server.", color=discord.Color.red()))
            return
        if unit not in ["minutes", "hours", "days"]:
            await ctx.send(embed=discord.Embed(description='Invalid time unit. Please use "minutes", "hours", or "days".', color=discord.Color.red()))
            return
        delta = timedelta(minutes=duration) if unit == "minutes" else timedelta(hours=duration) if unit == "hours" else timedelta(days=duration)
        if delta.total_seconds() > 2592000:
            await ctx.send(embed=discord.Embed(description='Timeout duration cannot exceed 30 days. Please adjust the duration.', color=discord.Color.red()))
            return
        await member.edit(timed_out_until=utcnow() + delta)
        embed = discord.Embed(title="User Timed Out", color=discord.Color.orange())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Timed out by", value=ctx.author.mention, inline=True)
        embed.add_field(name="Duration", value=f'{duration} {unit}', inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)
        add_mod_log(member.id, f"timeout: {duration} {unit}", ctx.author.id, "timeout")

    # !wminor <userID> <reason>
    @commands.command(name="wminor")
    async def warn_minor(self, ctx, user_id: int, *, reason=None):
        member = ctx.guild.get_member(user_id)
        if not member:
            await ctx.send(embed=discord.Embed(description="User not found in this server.", color=discord.Color.red()))
            return
        await self.issue_warning(ctx, member, "minor", reason)

    # !wmajor <userID> <reason>
    @commands.command(name="wmajor")
    @commands.has_any_role(JRMOD_ROLE_ID, MODS_ROLE_ID, ADMINS_ROLE_ID, CO_OWNERS_ROLE_ID, OWNERS_ROLE_ID, BOT_MANAGER_ID)
    async def warn_major(self, ctx, user_id: int, *, reason=None):
        member = ctx.guild.get_member(user_id)
        if not member:
            await ctx.send(embed=discord.Embed(description="User not found in this server.", color=discord.Color.red()))
            return
        await self.issue_warning(ctx, member, "major", reason)

    # !wremoveminor <userID> <logID>
    @commands.command(name="wremoveminor")
    @commands.has_any_role(JRMOD_ROLE_ID, MODS_ROLE_ID, ADMINS_ROLE_ID, CO_OWNERS_ROLE_ID, OWNERS_ROLE_ID, BOT_MANAGER_ID)
    async def wremoveminor(self, ctx, user_id: int, log_id: int):
        if remove_warning(user_id, "minor", log_id):
            await ctx.send(embed=discord.Embed(description=f"✅ Successfully removed **minor** warning for user <@{user_id}> (LogID: {log_id})", color=discord.Color.green()))
        else:
            await ctx.send(embed=discord.Embed(description=f"❌ Failed to remove **minor** warning for user <@{user_id}>. Either the warning doesn't exist or there was an error.", color=discord.Color.red()))

    # !wremovemajor <userID> <logID>
    @commands.command(name="wremovemajor")
    @commands.has_any_role(JRMOD_ROLE_ID, MODS_ROLE_ID, ADMINS_ROLE_ID, CO_OWNERS_ROLE_ID, OWNERS_ROLE_ID, BOT_MANAGER_ID)
    async def wremovemajor(self, ctx, user_id: int, log_id: int):
        if remove_warning(user_id, "major", log_id):
            await ctx.send(embed=discord.Embed(description=f"✅ Successfully removed **major** warning for user <@{user_id}> (LogID: {log_id})", color=discord.Color.green()))
        else:
            await ctx.send(embed=discord.Embed(description=f"❌ Failed to remove **major** warning for user <@{user_id}>. Either the warning doesn't exist or there was an error.", color=discord.Color.red()))

    # !kick <userID> <reason>
    @commands.command(name="kick")
    @commands.has_any_role(JRMOD_ROLE_ID, MODS_ROLE_ID, ADMINS_ROLE_ID, CO_OWNERS_ROLE_ID, OWNERS_ROLE_ID, BOT_MANAGER_ID)
    async def kick(self, ctx, user_id: int, *, reason="No reason provided"):
        member = ctx.guild.get_member(user_id)
        if not member:
            await ctx.send(embed=discord.Embed(description="User not found in this server.", color=discord.Color.red()))
            return
        await member.kick(reason=reason)
        embed = discord.Embed(title="User Kicked", color=discord.Color.yellow())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Kicked by", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)
        add_mod_log(member.id, reason, ctx.author.id, "kick")
        try:
            await member.send(f'You have been kicked from {ctx.guild.name} for: {reason}')
        except discord.Forbidden:
            await ctx.send(embed=discord.Embed(description=f'Could not send DM to {member.mention}, they might have DMs disabled.', color=discord.Color.red()))

    # !ban <userID> <reason>
    @commands.command(name="ban")
    @commands.has_any_role(MODS_ROLE_ID, ADMINS_ROLE_ID, CO_OWNERS_ROLE_ID, OWNERS_ROLE_ID, BOT_MANAGER_ID)
    async def ban(self, ctx, user_id: int, *, reason="No reason provided"):
        member = ctx.guild.get_member(user_id)
        if not member:
            await ctx.send(embed=discord.Embed(description="User not found in this server.", color=discord.Color.red()))
            return
        await member.ban(reason=reason)
        embed = discord.Embed(title="User Banned", color=discord.Color.red())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Banned by", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)
        add_mod_log(member.id, reason, ctx.author.id, "ban")
        try:
            await member.send(f'You have been banned from {ctx.guild.name} for: {reason}')
        except discord.Forbidden:
            await ctx.send(embed=discord.Embed(description=f'Could not send DM to {member.mention}, they might have DMs disabled.', color=discord.Color.red()))

    # Helper for warnings
    async def issue_warning(self, ctx, member: discord.Member, warning_type: str, reason: str):
        if not reason:
            await ctx.send(embed=discord.Embed(description=f'Please provide a reason for the warning, {ctx.author.mention}.', color=discord.Color.red()))
            return
    
        # Save directly to DB
        add_mod_log(member.id, reason, ctx.author.id, f"{warning_type}_warning")
    
        # Embed feedback
        minor_warnings, major_warnings = get_warnings(member.id)
        total_warnings = len(minor_warnings) if warning_type == "minor" else len(major_warnings)
    
        embed = discord.Embed(title=f"{warning_type.capitalize()} Warning Issued", color=discord.Color.orange())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Warned by", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name=f"Total {warning_type.capitalize()} Warnings", value=total_warnings, inline=False)
        await ctx.send(embed=embed)

        try:
            await member.send(f'You have received a {warning_type} warning in {ctx.guild.name} for: {reason}')
        except discord.Forbidden:
            await ctx.send(embed=discord.Embed(description=f'Could not send DM to {member.mention}, they might have DMs disabled.', color=discord.Color.red()))


async def setup(bot):
    await bot.add_cog(Mod(bot))
