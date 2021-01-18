import argparse
import asyncio
import ctypes
import sys
import threading

import gi
import vlc

from src.chat import TwitchChatReader, get_token, user_data_request, INVALID_OAUTH_TOKEN

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.0")
from gi.repository import GLib, Gtk, WebKit2


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

    def play(self):
        self._player.play()


class TwitchChatWebView(WebKit2.WebView):
    def __init__(self, channel_name):
        super().__init__()
        self.get_settings().set_enable_javascript(True)
        self._run_chat_thread(channel_name)

    def _append_msg(self, msg):
        msg_newlines_escaped = msg.replace("\n", "\\n")
        content_visible_height = "document.body.clientHeight"
        content_full_height = "document.body.scrollHeight"
        content_scroll_position = "document.body.scrollTop"
        content_max_scroll_position = f"{content_full_height} - {content_visible_height}"

        append_msg_js = f"""
            var shouldAutoscroll = {content_scroll_position} >= {content_max_scroll_position};
            
            var p = document.createElement("P");
            var t = document.createTextNode("{msg_newlines_escaped}");
            p.appendChild(t);
            document.body.appendChild(p);
            
            if (shouldAutoscroll) {{
                {content_scroll_position} = {content_max_scroll_position};
            }}
        """

        self.run_javascript(append_msg_js)

    def _run_chat_thread(self, channel_name):
        def target():
            asyncio.set_event_loop(asyncio.new_event_loop())
            self._read_chat(channel_name)

        chat_thread = threading.Thread(target=target, daemon=True)
        chat_thread.start()

    def _read_chat(self, channel_name):
        token = get_token(from_cache=True)
        user_data_response = user_data_request(token)

        if user_data_response.status_code == INVALID_OAUTH_TOKEN:
            token = get_token(from_cache=False)

        user_data_response = user_data_request(token)
        (user_data,) = user_data_response.json()["data"]
        nickname = user_data["display_name"]

        def show_chat_msg(msg):
            text = f"{msg.author.name}: {msg.content}\n"
            GLib.idle_add(self._append_msg, text)

        reader = TwitchChatReader(
            oauth_token=token,
            nickname=nickname,
            channel=channel_name,
            chat_handler=show_chat_msg,
        )
        reader.run()


class App(Gtk.Window):
    def __init__(self, channel_name, stream_loc):
        super().__init__(title="Twitch Player")
        self.set_default_size(1300, 588)
        self._hpane = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self._video_frame = Gtk.Frame()
        self._chat_frame = Gtk.Frame()
        self._player = TwitchPlayer(stream_loc)

        self.add(self._hpane)
        self._hpane.pack1(self._video_frame, True, True)
        self._hpane.pack2(self._chat_frame, True, True)

        self._video_frame.add(self._player)
        self._video_frame.set_shadow_type(Gtk.ShadowType.IN)
        self._video_frame.set_size_request(8, -1)

        self._chat_frame.add(TwitchChatWebView(channel_name))
        self._chat_frame.set_shadow_type(Gtk.ShadowType.IN)
        self._chat_frame.set_size_request(1, -1)

        self._player.play()


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
