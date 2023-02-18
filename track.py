from typing import Optional, Any


class Track:
    def __init__(self, title: Optional[str] = None):
        self.title = title
        self.file_path: Optional[str] = None

        # from online only
        self.url: Optional[str] = None

    def __repr__(self):
        return f"<Track({self.title})>"


class YoutubeTrack(Track):
    def __init__(self, path: str, info: dict[str, Any]):
        super().__init__()
        self.title = info.get("title", "Untitled video")
        self.file_path = path
        self.url = info.get("webpage_url", "https://quasar.name")


class SkrunklyTheme(Track):
    def __init__(self):
        super().__init__()
        self.title = "Skrunkly Theme Song"
        self.file_path = "./skrunkly.mp3"
