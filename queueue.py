from track import *
import yt_dlp


class Queue:
    def __init__(self):
        self.tracks: list[Track] = []

    def clear(self):
        self.tracks.clear()

    @property
    def first(self):
        return self.tracks[0] if len(self.tracks) else None

    @property
    def last(self):
        return self.tracks[len(self.tracks) - 1] if len(self.tracks) else None

    def remove_first(self):
        if self.first is None:
            return False
        self.tracks.remove(self.first)
        return True

    def __getitem__(self, item):
        return self.tracks[item]

    def __len__(self):
        return len(self.tracks)

    def __contains__(self, item):
        return item in self.tracks

    def add(self, song: Track):
        self.tracks.append(song)

    def pop(self, index: int = None):
        if index is None:
            self.tracks.pop()
            return
        self.tracks.pop(index)

    def add_youtube(self, server_id, query: str) -> YoutubeTrack:
        with yt_dlp.YoutubeDL(
                {'format': 'worstaudio',
                 'source_address': '0.0.0.0',
                 'default_search': 'ytsearch',
                 'outtmpl': '%(id)s.%(ext)s',
                 'noplaylist': True,
                 'allow_playlist_files': False
                 }) as ydl:

            # get the info for a track
            info = ydl.extract_info(query, download=False)

            # make sure only one track
            if 'entries' in info:
                info = info['entries'][0]

            yt_track = YoutubeTrack(info['webpage_url'])
            yt_track.title = info.get("title", "Untitled Video")
            yt_track.url = f'./dl/{server_id}/{info["id"]}.{info["ext"]}'
            self.tracks.append(yt_track)

            return yt_track

    def remove(self, remove: Track):
        self.tracks = [song for song in self.tracks if song != remove]

    def __repr__(self):
        return f"<Queue(tracks={self.tracks})>"
