# ModMail Bot

## Overview
The ModMail Bot is a Discord bot designed to facilitate communication between users and staff members through a ticketing system. Users can message the bot to create private channels in a designated "Contact Staff" category, allowing for private discussions and support.

## Features
- **Ticket Creation**: Users can initiate a ticket by messaging the bot, which creates a private channel for communication.
- **Staff Commands**: Staff members can manage tickets using specific commands, including moving tickets between categories and replying to users.
- **Category Management**: The bot supports multiple categories for ticket handling, allowing for organized management of user inquiries.

## Installation
1. Clone the repository:
   ```
   git clone https://github.com/yourusername/Modmail-master.git
   ```
2. Navigate to the project directory:
   ```
   cd Modmail-master
   ```
3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Configuration
Before running the bot, ensure that you have configured the `config/config.json` file with the necessary settings, including your Discord bot token, server IDs, and category IDs.

## Usage
1. Run the bot:
   ```
   python bot.py
   ```
2. Users can create a ticket by messaging the bot directly.
3. Staff can use the following commands to manage tickets:
   - `!move <category>`: Move the current ticket to a different category.
   - `!r <message>`: Reply to the user in the ticket.
   - `!re <message>`: Edit the previous reply to the user.
   - `!dx`: Access pre-made replies for common inquiries.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.