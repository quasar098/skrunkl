from typing import Optional, Any
import yt_dlp


class Track:
    def __init__(self, title: Optional[str] = None):
        self.title = title
        self.file_path: Optional[str] = None

        # from online only
        self.url: Optional[str] = None

    def __repr__(self):
        return f"<Track({self.title})>"

    async def download(self, server_id):
        pass


class YoutubeTrack(Track):
    def __init__(self, url: str):
        super().__init__()
        self.title = "Untitled video"
        self.file_path = None
        self.url = url

    async def download(self, server_id):
        with yt_dlp.YoutubeDL(
                {'format': 'm4a/bestaudio/best',
                 'source_address': '0.0.0.0',
                 'default_search': 'ytsearch',
                 'outtmpl': '%(id)s.%(ext)s',
                 'noplaylist': True,
                 'allow_playlist_files': False,
                 'paths': {'home': f'./dl/{server_id.n}'}}) as ydl:

            # get the info for a track
            ydl.download([self.url])


class SkrunklyThemeTrack(Track):
    def __init__(self):
        super().__init__()
        self.title = "Skrunkly Theme Song"
        self.file_path = "./skrunkly.mp3"

    async def download(self, server_id):
        pass
