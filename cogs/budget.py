import discord
import re
import datetime
import google.generativeai as genai
from discord.ext import commands
from discord.ui import Button, View
from currency_converter import CurrencyConverter
import os
from dotenv import load_dotenv
import emoji  
from dbconnMOD import add_mod_log, get_warnings
import asyncio

load_dotenv()
API_KEY = os.getenv("API_KEY") 
genai.configure(api_key=API_KEY)

model = genai.GenerativeModel("gemini-pro")  
c = CurrencyConverter()

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True  

MOD_LOG_CHANNEL_ID = 1338401271119347743  
WARNING_LOG_CHANNEL_ID = 1243663526715850762
TARGET_CHANNEL_ID = [1338422604897456129, 1248315045000253530, 1244399296279740558, 1240456287473369170, 1246266893925482641, 1243567009564721243, 1244400051879546930]

class Budget(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    log_counter = 1  

    def get_next_log_number(self):
        log_number = self.log_counter
        self.log_counter += 1
        return log_number

    def clean_text(self, text):
        # Remove links
        text = re.sub(r"https?://\S+", "", text)
        
        # Ignore TAT, TURN AROUND TIME, and SLOTS
        text = re.sub(r"(?i)(TAT|TURN AROUND TIME|SLOTS)", "", text)
        
        # Remove emoji and other unwanted characters
        text = emoji.replace_emoji(text, replace="")  # Removes any emojis
        text = re.sub(r"<a?:\w+:\d+>", "", text)  # Removes animated emojis and other special characters
        
        return text


    def extract_prices(self, text):
        # Extract prices from the text
        price_patterns = re.finditer(
            r"(?P<currency>[$€£¥₹]|USD|EUR|GBP|JPY|INR)?\s*(?P<amount>\d+(?:\.\d+)?)\s*(?P<post_currency>[$€£¥₹]|USD|EUR|GBP|JPY|INR)?",
            text,
            re.IGNORECASE,
        )
        prices = []
        currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
        
        for match in price_patterns:
            pre_currency = match.group("currency")  
            amount = match.group("amount")  
            post_currency = match.group("post_currency")  
            
            currency_code = currency_map.get(pre_currency, "USD")
            if post_currency:
                currency_code = currency_map.get(post_currency, "USD")
            
            if amount:
                prices.append((float(amount), currency_code.upper()))
        return prices

    def check_price(self, text):
        # Clean the text to remove unwanted keywords
        text = self.clean_text(text)

        # Ignore the price range "$100-$140"
        text = re.sub(r"\$100-\$140", "", text)

        # Extract prices from the text
        prices = self.extract_prices(text)

        # Check if any price is below $15
        for price, currency in prices:
            try:
                price_in_usd = c.convert(price, currency) if currency in c.currencies else price
                if price_in_usd < 14:
                    return True  # Flag this message as INVALID
            except (ValueError, KeyError):
                pass
        return False  # No price below $15, so the message is valid


    async def analyze_with_gemini(self, text):
        try:
            model = genai.GenerativeModel("gemini-pro")
            prompt = f"""
            You are a moderator assistant reviewing marketplace messages.
            **Only flag messages as "INVALID" if they contain a price below $15 USD.**
            **Ignore prices labeled as add-ons, fees, or commercial use fees.**
            **Bulk deals (e.g., "minimum", "bundle", "bulk", "at least") are valid.**
            **TAT (Turnaround Time) mentions make the message valid.**
            ** if mentions of Turn Around Time / TAT then the message is VALID**
            **If "payment after sketch" are invalid**
            **User Message:**
            {text}
            """
            response = model.generate_content(prompt)
            return "INVALID" if "INVALID" in response.text else "VALID"
        except Exception:
            return "VALID"  

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Initialize variables to ensure they are always defined
        regex_check = None
        ai_check = "VALID"  # Default to "VALID" for AI check, since we don't flag it by default

        # Check if the message is in the target channels
        if message.channel.id in TARGET_CHANNEL_ID:
            text_without_links = self.clean_text(message.content)

            # Debugging: print the cleaned text
            print(f"Cleaned message content: {text_without_links}")

            # Check using regex
            regex_check = self.check_price(text_without_links)

            # Debugging: print the result of regex check
            print(f"Regex check result: {regex_check}")

            # AI Check
            ai_check = await self.analyze_with_gemini(text_without_links)

            # Debugging: print the AI check result
            print(f"AI check result: {ai_check}")

        # Check if either the regex or AI check flags the message
        if regex_check or ai_check == "INVALID":
            # Log the invalid message
            mod_log_channel = self.bot.get_channel(MOD_LOG_CHANNEL_ID)

            # Creating the log embed
            embed = discord.Embed(title="🚨 Possible Rule Violation", color=discord.Color.red())
            embed.set_author(name=message.author.name, icon_url=message.author.display_avatar.url)
            embed.add_field(name="User ID", value=message.author.id, inline=True)

            # Replace Channel field with Message Link
            message_link = message.jump_url  # Provides the link to the message
            embed.add_field(name="Message Link", value=f"[Click Here]({message_link})", inline=True)

            embed.add_field(name="Message Content", value=message.content[:1024], inline=False)
            embed.set_footer(text=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            # Check if message was edited, and include the original message in the log
            if message.edited_at:
                original_content = message.content
                embed.add_field(name="Original Message (if edited)", value=original_content, inline=False)

            # Check if the message was forwarded from another server
            if message.reference:
                embed.add_field(name="Message Forwarded", value="Yes", inline=False)

            # Send the log
            await mod_log_channel.send(embed=embed, view=WarningButton(self.bot, message.author.id, message, self.get_next_log_number()))

class WarningButton(View):
    def __init__(self, bot, user_id, message, log_number):
        super().__init__(timeout=None)
        self.bot = bot  
        self.user_id = user_id
        self.message = message
        self.log_number = log_number  

    async def issue_warning(self, interaction, warning_type):
        user = await self.bot.fetch_user(self.user_id)

        # Fetch warnings
        minor_warnings, major_warnings = get_warnings(user.id)
        count = len(minor_warnings) + 1 if warning_type == "Minor Warning" else len(major_warnings) + 1

        # Ask for automated/custom message
        await interaction.response.send_message(
            "Would you like to send an automated warning message or write a custom one?",
            view=CustomMessageView(self.bot, user, self.message, warning_type, count),
            ephemeral=True
        )

        add_mod_log(user.id, f"{warning_type} for pricing rule violation", interaction.user.id, warning_type.lower())
        for button in self.children:
            button.disabled = True  

        await interaction.message.edit(view=self)

    @discord.ui.button(label="Minor Warning", style=discord.ButtonStyle.danger)
    async def minor_warning(self, interaction: discord.Interaction, button: Button):
        await self.issue_warning(interaction, "Minor Warning")
    
    @discord.ui.button(label="Major Warning", style=discord.ButtonStyle.blurple)
    async def major_warning(self, interaction: discord.Interaction, button: Button):
        await self.issue_warning(interaction, "Major Warning")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Log entry deleted.", ephemeral=True)
        await interaction.message.delete()
        
        # Disable buttons directly here
        for button in self.children:
            button.disabled = True
        await interaction.message.edit(view=self)

class CustomMessageView(View):
    def __init__(self, bot, user, message, warning_type, count):
        super().__init__(timeout=60)
        self.bot = bot
        self.user = user
        self.message = message
        self.warning_type = warning_type
        self.count = count

    async def disable_buttons(self, interaction):
        """Disables buttons after a selection is made"""
        for button in self.children:
            button.disabled = True  
        try:
            await interaction.message.edit(view=self)
        except discord.errors.NotFound:
            # Handle the case where the message is not found (deleted)
            print("Message not found, skipping edit.")


    async def delete_message(self):
        """Deletes the user's message."""
        try:
            await self.message.delete()
        except discord.NotFound:
            print("Message already deleted.")  # Log or handle the case where the message is already gone
        except Exception as e:
            print(f"An error occurred while deleting the message: {e}")  # Catch any other exceptions


    async def log_warning_to_db(self, interaction, warning_text):
        """Logs the warning in the MySQL database"""
        moderator_id = str(interaction.user.id)  # Moderator issuing the warning
        user_id = str(self.user.id)
        action_type = self.warning_type.lower().replace(" ", "_")  # Format: minor_warning, major_warning
        
        success = add_mod_log(user_id, warning_text, moderator_id, action_type)
        if not success:
            print(f"⚠️ Failed to log warning for {user_id} in the database.")

    async def send_warning_log(self, interaction, warning_text):
        """Sends the warning to the log channel"""
        warning_log_channel = self.bot.get_channel(WARNING_LOG_CHANNEL_ID)
        if not warning_log_channel:
            print("Error: Warning log channel is not set!")
            return

        embed = discord.Embed(title="🚨 User Warned", color=discord.Color.orange())
        embed.set_author(name=self.user.name, icon_url=self.user.display_avatar.url)
        embed.add_field(name="User ID", value=self.user.id, inline=True)
        embed.add_field(name="Warning Type", value=self.warning_type, inline=True)
        embed.add_field(name="Total Warnings", value=self.count, inline=True)
        embed.add_field(name="Message Content", value=self.message.content[:1024], inline=False)
        embed.set_footer(text=f"Warning issued by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await warning_log_channel.send(embed=embed)

    @discord.ui.button(label="Automated Message", style=discord.ButtonStyle.success)
    async def automated_message(self, interaction: discord.Interaction, button: Button):
        warning_text = f"Your message was deleted because at least one of your listed prices was below the $15 minimum budget requirement.\nThis is your {self.count} {self.warning_type.lower()} warning."
        warning_embed = discord.Embed(
            title=f"⚠️ {self.warning_type} Issued", 
            description=warning_text, 
            color=discord.Color.red()
        )
        warning_embed.add_field(name="Your Message", value=f"{self.message.content}", inline=False)
        warning_embed.set_footer(text="Please comply with the pricing rules to avoid further action.")

        try:
            await self.user.send(embed=warning_embed)
            await interaction.response.send_message("Automated warning sent.", ephemeral=True)
            await self.delete_message()  # Delete the user's message after sending the warning
        except discord.Forbidden:
            await interaction.response.send_message("Could not send DM to user.", ephemeral=True)

        await self.send_warning_log(interaction, warning_text)
        await self.log_warning_to_db(interaction, warning_text) 
        await self.disable_buttons(interaction) 
    
    @discord.ui.button(label="Custom Message", style=discord.ButtonStyle.primary)
    async def custom_message(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Please type your custom warning message:", ephemeral=True)

        def check(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            custom_embed = discord.Embed(
                title="⚠️ Custom Warning Issued",
                description=msg.content,
                color=discord.Color.orange()
            )
            custom_embed.set_footer(text="Please follow the server rules.")

            try:
                await self.user.send(embed=custom_embed)
                await interaction.followup.send("Custom warning sent.", ephemeral=True)
                await self.delete_message()  # Delete the user's message after sending the custom warning
            except discord.Forbidden:
                await interaction.followup.send("Could not send DM to user.", ephemeral=True)

            await self.send_warning_log(interaction, msg.content)
            await self.log_warning_to_db(interaction, msg.content)  # ✅ Log to DB
            await self.disable_buttons(interaction)  # 🚀 Disable buttons after use!

        except asyncio.TimeoutError:
            await interaction.followup.send("Custom message timed out.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Budget(bot))