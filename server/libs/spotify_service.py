import json
import logging
import traceback
from typing import Any
from urllib.request import urlopen
from spotapi import (
    Login,
    EventManager,
    Config,
    LoggerProtocol,
    User,
    solver_clients,
    Logger,
    Song
)
from spotapi.http.request import TLSClient
from colorthief import ColorThief

from libs.config_service import ConfigService
from libs.notification_enum import NotificationEnum
from libs.webserver.executer import Executer
from libs.queue_wrapper import QueueWrapper
from libs.notification_item import NotificationItem



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
    def start(self, config_service: ConfigService, tls: TLSClient, notifications):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Starting Spotify service")

        self._notifications = QueueWrapper(notifications)
        self._config_service = config_service
        self.tls_client = tls
        self._current_track_id = None
        
        if self._config_service.config["general_settings"]["spotify_color_override_enabled"]:
            self._login_email = self._config_service.config["general_settings"]["spotify_email"]
            self._login_cookies = self._config_service.config["general_settings"]["spotify_cookies"]
            self.create_spotify_client()
        else:
            self.logger.info("Spotify color override disabled.")
        

    def create_spotify_client(self):
        self.logger.info("Creating Spotify client.")
        self.logger.debug("email=%s, cookies=%s", self._login_email, self._login_cookies)

        spotify_logger = SpotifyLogger(self.logger)
        
        config = Config(
            solver=solver_clients.Capsolver("N/A", proxy="N/A"),
            logger=spotify_logger,
            client=self.tls_client
        )

        try:
            self.logger.info("Attempting log in")
            self._spotify_client = Login.from_cookies({
                "identifier": self._login_email,
                "cookies": json.loads(self._login_cookies)
            }, config)

            user = User(self._spotify_client)
            self.logger.info("Logged in as %s. has_premium=%s", user.username, user.has_premium)

            self._websocket_client = EventManager(self._spotify_client)

            @self._websocket_client.subscribe("DEVICE_STATE_CHANGED")
            def callback(*args, **kwargs):
                track_json = args[0]["cluster"]["player_state"]["track"]
                track_id = track_json["uri"]

                if self._current_track_id == track_id:
                    return
                
                self.logger.debug("Current %s, New: %s", self._current_track_id, track_id)
                
                self._current_track_id = track_id

                tries = 3
                for i in range(tries):
                    try:
                        song_client = Song(client=self.tls_client)
                        track = song_client.get_track_info(str(track_id).split(":")[2])
                        track_meta = track["data"]["trackUnion"]

                        self.logger.info("Received new spotify track: %s", track_meta["name"])

                        album_image_sources = track_meta["albumOfTrack"]["coverArt"]["sources"]
                        largest_image = max(album_image_sources, key=lambda x: x["height"] * x["width"])
                        album_image_url = largest_image["url"]
                        album_image_stream = urlopen(album_image_url)

                        color_thief = ColorThief(album_image_stream)
                        color_palette = color_thief.get_palette(3, quality=1)
                        self.logger.debug("Generated new color palette. %s", color_palette)
                        
                        self._config_service.load_config()
                        self._config_service.config["gradients"]["spotify_palette"] = color_palette

                        singular_color = str(track_meta["albumOfTrack"]["coverArt"]["extractedColors"]["colorRaw"]["hex"]).strip("#")
                        color_tuple = list()
                        color_tuple.append(int(singular_color[1:2], 16))
                        color_tuple.append(int(singular_color[3:4], 16))
                        color_tuple.append(int(singular_color[5:6], 16))

                        self._config_service.config["colors"]["spotify_color"] = color_tuple
                        self.logger.debug("Extracted main color: %s", color_tuple)

                        self._config_service.save_config()

                        notification = NotificationItem(NotificationEnum.config_refresh, "device_0")
                        self._notifications.put_blocking(notification)
                        break
                    except Exception as e:
                        self.logger.error("Gateway error: %s", traceback.format_exception(e))
                        if i < tries - 1:
                            self.logger.info("Retrying... (%s/3)", i + 1)
                            continue
                        break


        except Exception as e:
            self.logger.error("Failed to login. %s", traceback.format_exception(e))



