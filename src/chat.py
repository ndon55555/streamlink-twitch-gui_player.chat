import os
import pathlib

import requests
from twitchio.ext import commands

from constants import PROJECT_DATA_DIR, TWITCH_CLIENT_ID
from src.oauth import with_oauth_redirect_server, get_twitch_oauth_token_implicit_flow

INVALID_OAUTH_TOKEN = 401
CACHE_DIR = os.path.join(PROJECT_DATA_DIR, "cache")


def user_data_request(token):
    return requests.get(
        "https://api.twitch.tv/helix/users",
        headers={"Authorization": f"Bearer {token}", "Client-Id": TWITCH_CLIENT_ID},
    )


def get_token(from_cache):
    home_dir = pathlib.Path.home()
    cache_dir = home_dir.joinpath(CACHE_DIR)
    token_cache_file_path = cache_dir.joinpath("oauth-token")

    os.makedirs(cache_dir, exist_ok=True)
    token_cache_file_path.touch()

    with token_cache_file_path.open(mode="r+") as token_file:
        if from_cache:
            return token_file.read()
        else:
            new_token = with_oauth_redirect_server(get_twitch_oauth_token_implicit_flow)
            token_file.truncate(0)
            token_file.write(new_token)
            return new_token


class TwitchChatReader(commands.Bot):
    def __init__(self, oauth_token, nickname, channel, chat_handler=None):
        super().__init__(
            irc_token=f"oauth:{oauth_token}",
            nick=nickname,
            prefix="!",
            initial_channels=[channel],
        )

        self._chat_handler = chat_handler or (lambda _: None)

    async def event_message(self, message):
        self._chat_handler(message)


def main():
    token = get_token(from_cache=True)
    user_data_response = user_data_request(token)

    if user_data_response.status_code == INVALID_OAUTH_TOKEN:
        token = get_token(from_cache=False)

    user_data_response = user_data_request(token)
    (user_data,) = user_data_response.json()["data"]
    nickname = user_data["display_name"]

    def print_msg(msg):
        print(f"{msg.author.name}: {msg.content}")

    t = TwitchChatReader(
        oauth_token=token, nickname=nickname, channel="harddrop", chat_handler=print_msg
    )
    t.run()


if __name__ == "__main__":
    main()
