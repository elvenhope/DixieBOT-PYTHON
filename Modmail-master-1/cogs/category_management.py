from discord.ext import commands
import discord

class CategoryManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.category_ids = {
            "contact": 1346881466881146910,
            "trusted": 1346882153279000648,
            "questions": 1402347454438838443,
            "suggestions": 1402347609460576367,
            "partnerships": 1402347709976936591,
            "reports": 1402347829409874032,
            "appeals": 1402347868756643900,
            "ko-fi": 1402348823598203061,
            "nsfw": 1346881386510024745,
            "tech": 1346882435400466495,
            
            
        }

    @commands.Cog.listener()
    async def on_ready(self):
        # Fetch category IDs from the guild and store them
        guild = discord.utils.get(self.bot.guilds, id=self.bot.guild_id)
        for category_name in self.category_ids.keys():
            category = discord.utils.get(guild.categories, name=category_name)
            if category:
                self.category_ids[category_name] = category.id

    @commands.command(name='move')
    @commands.has_permissions(manage_channels=True)
    async def move_ticket(self, ctx, category_name: str):
        """Move the current ticket to a specified category."""
        if category_name not in self.category_ids:
            await ctx.send(f"Category '{category_name}' does not exist.")
            return

        channel = ctx.channel
        new_category_id = self.category_ids[category_name]
        new_category = self.bot.get_channel(new_category_id)

        if new_category:
            await channel.edit(category=new_category)
            await ctx.send(f"Moved ticket to '{category_name}' category.")
        else:
            await ctx.send("Failed to move ticket. Category not found.")

 
async def setup(bot):
    await bot.add_cog(CategoryManagement(bot))