from queue import Queue
from track import *
import json
import logging
from typing import Union


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

    def __init__(self):
        SkrunklData.INSTANCE = self

        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)-15s %(levelname)-5s %(msg)s"
        )
        self.logger = logging.Logger("skrunkl")

        self._queues: dict[ServerID, Queue] = {}
        self._cooldowns: dict[ServerID, float] = {}
        self._playlists: dict[ServerID, list[Playlist]] = {}

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

    def purge(self, server_id: ServerID):
        self.register_server_id(server_id)
        self._queues.pop(server_id)
        self._cooldowns.pop(server_id)

    def try_play(self):
        """Play a track if not currently playing a track"""
        pass

    def stop_playing(self):
        """Stop the playing of a track temporarily"""
        pass
