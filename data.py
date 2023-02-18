import discord

from queue import Queue
from track import *
import json
import logging
from typing import Union
from discord.ext import commands


class ServerID:
    def __init__(self, sid: Union[int, str]):
        self.n = int(sid)

    def __repr__(self):
        return f"<ServerID({self.n})>"

    def __hash__(self):
        return hash(self.n)


class Playlist:
    def __init__(self, name: str, tracks: list[str] = None):
        self.name = name
        self.tracks = tracks if tracks is not None else []


class SkrunklData:
    INSTANCE = None
    BOT = None

    def __init__(self, bot: commands.Bot):
        SkrunklData.INSTANCE = self
        SkrunklData.BOT = bot

        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)-15s %(levelname)-5s %(msg)s"
        )
        self.logger = logging.Logger("skrunkl")

        self._queues: dict[ServerID, Queue] = {}
        self._cooldowns: dict[ServerID, float] = {}
        self._playlists: dict[ServerID, list[Playlist]] = {}
        self._connections: dict[ServerID, Optional[discord.VoiceClient]] = {}

        self.load_playlists()

    def load_playlists(self):
        try:
            with open("saved.json") as f:
                pdata = json.load(f)
            self.logger.info("successfully loaded json playlists file")
        except json.JSONDecodeError:
            self.logger.error("invalid playlist json file")
            pdata = {}

        for server in pdata:
            sid = ServerID(int(server))
            self.register_server_id(sid)
            playlists = pdata[server]
            for playlist_name in playlists:
                self._playlists[sid].append(Playlist(playlist_name, playlists[playlist_name]))

    def save_playlists(self):
        pdata = {}
        for server_id in self._playlists:
            pdata[server_id.n] = {}
            for playlist in self.get_playlists(server_id):
                pdata[server_id.n][playlist.name] = playlist.tracks

        try:
            with open("saved.json", 'w') as f:
                f.write(json.dumps(pdata))
            self.logger.info("successfully saved playlist json file")
        except json.JSONDecodeError:
            self.logger.error("failed to save playlist json file")

    def register_server_id(self, server_id: ServerID):
        if server_id not in self._queues:
            self._queues[server_id] = Queue()
        if server_id not in self._cooldowns:
            self._cooldowns[server_id] = 0
        if server_id not in self._playlists:
            self._playlists[server_id] = []
        if server_id not in self._connections:
            self._connections[server_id] = None

    def get_queue(self, server_id: ServerID) -> Queue:
        self.register_server_id(server_id)
        return self._queues.get(server_id)

    def get_cooldown(self, server_id: ServerID) -> float:
        self.register_server_id(server_id)
        return self._cooldowns.get(server_id)

    def set_cooldown(self, server_id: ServerID, cooldown: float = 0):
        self._cooldowns[server_id] = cooldown

    def get_playlists(self, server_id: ServerID) -> list[Playlist]:
        self.register_server_id(server_id)
        return self._playlists.get(server_id)

    def get_connection(self, server_id: ServerID):
        self.register_server_id(server_id)
        return self._connections.get(server_id)

    def purge(self, server_id: ServerID):
        self.register_server_id(server_id)
        self._queues.pop(server_id)
        self._cooldowns.pop(server_id)

    def try_play(self, ctx: commands.Context, conn: discord.VoiceClient = None):
        """Play a track if not currently playing a track"""
        server_id = ServerID(ctx.guild.id)
        queue = self.get_queue(server_id)

        if not len(queue):
            self.disconnect(ctx)
            return

        conn = self.get_connection_from_context(ctx) if conn is None else conn

        conn.play(
            discord.FFmpegOpusAudio(
                source="./skrunkly.mp3"
            ),
            after=self.try_play
        )

        queue.pop(0)

    def stop_playing(self, ctx: commands.Context):
        """Stop the playing of a track temporarily"""
        server_id = ServerID(ctx.guild.id)

        conn = await self.get_connection_from_context(ctx)
        conn.stop()

    async def disconnect(self, ctx: commands.Context):
        server_id = ServerID(ctx.guild.id)

        self.stop_playing(ctx)
        conn = await self.get_connection_from_context(ctx)
        await conn.disconnect()
        self.get_queue(server_id).clear()

    async def register_connection(self, server_id: ServerID, voice_client: discord.VoiceClient):
        self._connections[server_id] = voice_client

    async def get_connection_from_context(self, ctx: commands.Context):
        voice_state = ctx.author.voice

        if voice_state is None:
            return None

        server_id = ServerID(ctx.guild.id)

        maybe_conn = self.get_connection(server_id)
        if maybe_conn is not None:
            return maybe_conn

        maybe_conn = get_voice_client_from_voice_state(voice_state)
        if maybe_conn is not None:
            await self.register_connection(server_id, maybe_conn)
            return maybe_conn

        new_conn = await voice_state.channel.connect()
        await self.register_connection(server_id, new_conn)


def get_voice_client_from_voice_state(voice_state):
    for voice_client in SkrunklData.BOT.voice_clients:
        if voice_client.channel.id == voice_state.channel.id:
            return voice_client
