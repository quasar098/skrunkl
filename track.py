from typing import Optional, Any


class Track:
    def __init__(self, title: Optional[str] = None):
        self.title = title
        self.file_path: Optional[str] = None

        # from online only
        self.url: Optional[str] = None

    def __repr__(self):
        return f"<Track({self.title})>"

    async def download(self):
        pass


class YoutubeTrack(Track):
    def __init__(self, url: str):
        super().__init__()
        self.title = "Untitled video"
        self.file_path = None
        self.url = url

    async def download(self):
        pass


class SkrunklyTheme(Track):
    def __init__(self):
        super().__init__()
        self.title = "Skrunkly Theme Song"
        self.file_path = "./skrunkly.mp3"

    async def download(self):
        pass
