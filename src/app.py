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
    def __init__(self, channel_name, stream_loc):
        super().__init__(title="Twitch Player")
        self._player = TwitchPlayer(stream_loc)
        self._hbox = Gtk.HBox()
        self._scrolled_window = Gtk.ScrolledWindow()
        self._chat = Gtk.TextView()

        self._scrolled_window.set_border_width(5)
        self._scrolled_window.set_min_content_width(300)
        self._scrolled_window.set_vexpand(True)
        self._chat.set_editable(False)
        self._chat.set_cursor_visible(False)
        self._chat.set_wrap_mode(Gtk.WrapMode.WORD)

        self._scrolled_window.add(self._chat)
        self.add(self._hbox)
        self._hbox.add(self._player)
        self._hbox.add(self._scrolled_window)

        self._player.play()
        self._run_chat_thread(channel_name)

    def _run_chat_thread(self, channel_name):
        def target():
            asyncio.set_event_loop(asyncio.new_event_loop())
            self._read_chat(channel_name)

        chat_thread = threading.Thread(target=target, daemon=True)
        chat_thread.setDaemon(True)
        chat_thread.start()

    def _read_chat(self, channel_name):
        token = get_token(from_cache=True)
        user_data_response = user_data_request(token)

        if user_data_response.status_code == INVALID_OAUTH_TOKEN:
            token = get_token(from_cache=False)

        user_data_response = user_data_request(token)
        (user_data,) = user_data_response.json()["data"]
        nickname = user_data["display_name"]

        def append_msg_to_chat(text):
            buf: Gtk.TextBuffer = self._chat.get_buffer()
            buf.insert(buf.get_end_iter(), text)

        def update_chat(text):
            vertical_scroll: Gtk.Adjustment = self._scrolled_window.get_vadjustment()

            def chat_vertical_scroll_max():
                return vertical_scroll.get_upper() - vertical_scroll.get_page_size()

            # If True, Indicates the user hasn't manually scrolled up, so autoscroll down after text is appended
            should_autoscroll = vertical_scroll.get_value() == chat_vertical_scroll_max()

            append_msg_to_chat(text)

            # Wait for the TextView to resize after its TextBuffer was just modified to get the most up-to-date
            while Gtk.events_pending():
                Gtk.main_iteration()

            if should_autoscroll:
                vertical_scroll.set_value(chat_vertical_scroll_max())

        def show_chat_msg(msg):
            text = f"{msg.author.name}: {msg.content}\n"
            GLib.idle_add(update_chat, text)

        reader = TwitchChatReader(
            oauth_token=token,
            nickname=nickname,
            channel=channel_name,
            chat_handler=show_chat_msg,
        )
        reader.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--channel-name",
        help="The name of the Twitch channel that the stream is playing from.",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--stream-location",
        help="The location of the Twitch stream to play.",
        required=True,
        type=str,
    )
    args = parser.parse_args()

    # Would be nice if there were a way to initialize X11 threads without using ctypes
    x11_name = ctypes.util.find_library("X11")
    x11 = ctypes.cdll.LoadLibrary(x11_name)
    x11.XInitThreads()

    win = App(args.channel_name, args.stream_location)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
