import aiomysql
import logging
from datetime import datetime

logger = logging.getLogger("modmail.db")

class DatabaseManager:
    def __init__(self, bot):
        self.bot = bot
        self.pool = None

    async def setup(self):
        self.pool = await aiomysql.create_pool(
            host="gameswaw1.bisecthosting.com",
            port=3306,
            user="u404394_zmjisvvtS8",
            password="M7hB3OutjkNCIPHl7DM6dyhF",
            db="s404394_DixieMessenger",
            autocommit=True
        )
        logger.info("Database connection pool established.")

    async def get_open_ticket_channel_id(self, user_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT channel_id FROM active_tickets WHERE user_id=%s AND status='open'",
                    (user_id,)
                )
                result = await cur.fetchone()
                return int(result[0]) if result else None

    async def create_ticket_entry(self, user, channel, category_id, ticket_type: str):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO active_tickets 
                    (channel_id, user_id, member_username, mod_username, category_id, channel_name, created_at, closed_at, status, ticket_type, mod_id)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NULL, %s, %s, %s)
                    """,
                    (
                        channel.id,
                        user.id,
                        str(user),
                        None,
                        category_id,
                        channel.name,
                        "open",
                        ticket_type,
                        None  # mod_id initially unassigned (NULL)
                    )
                )

    async def close_ticket(self, user_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE active_tickets 
                    SET status='closed', closed_at=NOW() 
                    WHERE user_id=%s AND status='open'
                    """,
                    (user_id,)
                )

    async def assign_mod_to_ticket(self, channel_id: int, mod_id: int, mod_username: str):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE active_tickets
                    SET mod_id = %s, mod_username = %s
                    WHERE channel_id = %s AND status = 'open'
                    """,
                    (mod_id, mod_username, channel_id)
                )

    async def get_ticket_by_channel(self, channel_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM active_tickets WHERE channel_id=%s AND status='open'",
                    (channel_id,)
                )
                return await cur.fetchone()
            
    async def close_ticket(self, channel_id: int, closed_at: datetime):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE active_tickets
                    SET status = 'closed',
                        closed_at = %s
                    WHERE channel_id = %s
                    """,
                    (closed_at, channel_id)
                )

    async def get_dx_response(self, key: str):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT response FROM dx_responses WHERE `key`=%s", (key,))
                row = await cur.fetchone()
                if row:
                    return row[0]  # response column
                return None

    async def add_dx_response(self, key: str, response: str):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO dx_responses (`key`, `response`) VALUES (%s, %s)", (key, response)
                )
                await conn.commit()

    async def remove_dx_response(self, key: str):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM dx_responses WHERE `key`=%s", (key,))
                await conn.commit()

    async def get_all_dx_responses(self):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT `key`, response FROM dx_responses")
                rows = await cur.fetchall()
                return [{"key": row[0], "response": row[1]} for row in rows]

    async def add_ticket_timer(self, channel_id: int, user_id: int, action: str, execute_at: datetime):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO ticket_timers (channel_id, user_id, action, execute_at)
                    VALUES (%s, %s, %s, %s)
                """, (channel_id, user_id, action, execute_at))

    async def cancel_ticket_timer(self, channel_id: int, action: str):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    DELETE FROM ticket_timers
                    WHERE channel_id=%s AND action=%s
                """, (channel_id, action))

    async def get_pending_timers(self):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM ticket_timers
                    WHERE canceled=FALSE AND execute_at <= NOW()
                """)
                return await cur.fetchall()

    async def add_watcher(self, channel_id: int, mod_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT IGNORE INTO ticket_watchers (channel_id, mod_id)
                    VALUES (%s, %s)
                """, (channel_id, mod_id))

    async def get_watchers(self, channel_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT mod_id FROM ticket_watchers WHERE channel_id=%s", (channel_id,))
                rows = await cur.fetchall()
                return [r[0] for r in rows]
    async def remove_watcher(self, channel_id: int, mod_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM ticket_watchers WHERE channel_id=%s AND mod_id=%s",
                    (channel_id, mod_id)
                )


