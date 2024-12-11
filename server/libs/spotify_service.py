import logging
from typing import Any
from spotapi import (
    Login,
    EventManager,
    Config,
    LoggerProtocol
)

class SpotifyLogger(LoggerProtocol):
    def __init__(self, logger):
        self.logger = logger
        super().__init__()

    @staticmethod
    def error(s: str, **extra: Any) -> None:
        print(s)

    @staticmethod
    def info(s: str, **extra: Any) -> None:
        print(s)

    @staticmethod
    def fatal(s: str, **extra: Any) -> None:
        print(s)

    @staticmethod
    def attempt(s: str, **extra: Any) -> None:
        print(s)
    


class SpotifyService():
    def start(self, config):
        self.logger = logging.getLogger(__name__)

        self._config = config
        
        if self._config["general_settings"]["spotify_color_override_enabled"]:
            self._login_email = self._config["general_settings"]["spotify_email"]
            self._login_cookies = self._config["general_settings"]["spotify_cookies"]
            self.create_spotify_client()
        else:
            self.logger.info("Spotify color override disabled.")
        

    def create_spotify_client(self):
        self.logger.info("Creating Spotify client.")
        self.logger.debug("email=%s, cookies=%s", self._login_email, self._login_cookies)

        spotify_logger = SpotifyLogger(self.logger)
        config = Config(
            logger=spotify_logger
        )

        self._spotify_client = Login.from_cookies({
            "identifier": self._login_email,
            "cookies": self._login_cookies
        }, config)

        self._websocket_client = EventManager()

        @self._websocket_client.subscribe("DEVICE_STATE_CHANGED")
        def callback(*args, **kwargs):
            trackMetadata = args[0]["cluster"]["player_state"]["track"]["metadata"]
            self.logger.info("Currently playing track: %s", trackMetadata["title"])



