import logging
import os

logger = logging.getLogger("modmail")

def configure_logging(bot):
    logging.basicConfig(level=logging.INFO)

class ConfigManager:
    def __init__(self, bot):
        self.bot = bot
        self.cache = {}

    def populate_cache(self):
        pass

    def __getitem__(self, key):
        if key == "token":
            return os.getenv('DISCORD_TOKEN')  # <-- PUT YOUR TOKEN HERE
        return self.cache.get(key)


class ThreadManager:
    def __init__(self, bot):
        self.bot = bot

    async def create(self, user, message=None):
        # Dummy thread object for testing
        class DummyThread:
            async def send(self, msg):
                pass
        return DummyThread()