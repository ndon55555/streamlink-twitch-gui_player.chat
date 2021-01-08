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
from gi.repository import GLib, Gtk


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


class ChatView(Gtk.TextView):
    def __init__(self, channel_name):
        super().__init__()
        self.set_editable(False)
        self.set_cursor_visible(False)
        self.set_wrap_mode(Gtk.WrapMode.WORD)

        self._pre_chat_update_handlers = []
        self._post_chat_update_handlers = []
        self._run_chat_thread(channel_name)

    def _append_msg(self, msg):
        for handler in self._pre_chat_update_handlers:
            handler()

        buf = self.get_buffer()
        buf.insert(buf.get_end_iter(), msg)

        while Gtk.events_pending():
            Gtk.main_iteration()

        for handler in self._post_chat_update_handlers:
            handler()

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

    def on_pre_chat_update(self, handler):
        self._pre_chat_update_handlers.append(handler)

    def on_post_chat_update(self, handler):
        self._post_chat_update_handlers.append(handler)


class ChatScrolledView(Gtk.ScrolledWindow):
    def __init__(self, channel_name):
        super().__init__()
        self.set_border_width(5)
        self.set_min_content_width(300)
        self.set_vexpand(True)
        self._should_autoscroll = True
        self._vadjustment_prev_val = self._vadjustment_cur_val()

        self._chat_view = ChatView(channel_name)
        self._chat_view.on_pre_chat_update(self._chat_view_pre_update)
        self._chat_view.on_post_chat_update(self._chat_view_post_update)
        self.add(self._chat_view)

    def _vadjustment_cur_val(self):
        return self.get_vadjustment().get_value()

    def _vadjustment_max_val(self):
        vadj = self.get_vadjustment()
        return vadj.get_upper() - vadj.get_page_size()

    def _chat_view_pre_update(self):
        self._should_autoscroll = self._vadjustment_cur_val() == self._vadjustment_max_val()
        self._vadjustment_prev_val = self._vadjustment_cur_val()

    def _chat_view_post_update(self):
        vadj_val = self._vadjustment_prev_val

        if self._should_autoscroll:
            vadj_val = self._vadjustment_max_val()

        self.get_vadjustment().set_value(vadj_val)


class App(Gtk.Window):
    def __init__(self, channel_name, stream_loc):
        super().__init__(title="Twitch Player")
        self._player = TwitchPlayer(stream_loc)
        self._hbox = Gtk.HBox()

        self.add(self._hbox)
        self._hbox.add(self._player)
        self._hbox.add(ChatScrolledView(channel_name))

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
