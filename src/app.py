import argparse
import asyncio
import ctypes
import sys
import threading

import gi
import vlc

from src.chat import TwitchChatReader, get_token, user_data_request, INVALID_OAUTH_TOKEN

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk
from src.oauth import with_oauth_redirect_server, get_twitch_oauth_token_implicit_flow


class TwitchPlayer(Gtk.DrawingArea):
    def __init__(self, media):
        super().__init__()
        self._player = vlc.MediaPlayer(media)

        def handle_embed(_):
            if sys.platform == "win32":
                self._player.set_hwnd(self.get_window().get_handle())
            else:
                self._player.set_xwindow(self.get_window().get_xid())
            return True

        self.connect("map", handle_embed)
        self.set_size_request(1300, 800)

    def play(self):
        self._player.play()


class App(Gtk.Window):
    def __init__(self, media):
        super().__init__(title="Twitch Player")
        self._player = TwitchPlayer(media)

        self.add(self._player)
        self._player.play()

        self._run_chat_thread()

    def _run_chat_thread(self):
        def target():
            asyncio.set_event_loop(asyncio.new_event_loop())
            self._read_chat()

        chat_thread = threading.Thread(target=target, daemon=True)
        chat_thread.setDaemon(True)
        chat_thread.start()

    def _read_chat(self):
        token = get_token(from_cache=True)
        user_data_response = user_data_request(token)

        if user_data_response.status_code == INVALID_OAUTH_TOKEN:
            token = get_token(from_cache=False)

        user_data_response = user_data_request(token)
        (user_data,) = user_data_response.json()["data"]
        nickname = user_data["display_name"]

        def print_msg(msg):
            print(f"{msg.author.name}: {msg.content}")

        reader = TwitchChatReader(
            oauth_token=token,
            nickname=nickname,
            channel="gamesdonequick",
            chat_handler=print_msg,
        )
        reader.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "media", type=str, help="The location or data of the media to play."
    )
    args = parser.parse_args()

    # Would be nice if there were a way to initialize X11 threads without using ctypes
    x11_name = ctypes.util.find_library("X11")
    x11 = ctypes.cdll.LoadLibrary(x11_name)
    x11.XInitThreads()

    win = App(args.media)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
