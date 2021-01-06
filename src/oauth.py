import multiprocessing
import os

import geckodriver_autoinstaller
from authlib.integrations.requests_client import OAuth2Session
from flask import Flask
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from src.constants import *

_oauth_redirect_app = Flask(__name__)


@_oauth_redirect_app.route("/")
def _handle_oauth_redirect():
    return "All set! You can now head back to the app."


def with_oauth_redirect_server(do_something):
    server_proc = multiprocessing.Process(
        target=lambda: _oauth_redirect_app.run(port=TWITCH_OAUTH_REDIRECT_PORT)
    )
    server_proc.start()

    result = None
    exception = None

    try:
        result = do_something()
    except Exception as ex:
        exception = ex

    server_proc.terminate()

    if exception is not None:
        raise exception
    else:
        return result


def get_twitch_oauth_token_implicit_flow():
    os.environ["AUTHLIB_INSECURE_TRANSPORT"] = "1"
    oauth_client = OAuth2Session(
        TWITCH_CLIENT_ID, scope="chat:read", redirect_uri=TWITCH_OAUTH_REDIRECT_URL
    )
    oauth_approve_url, _ = oauth_client.create_authorization_url(
        TWITCH_OAUTH_URL, response_type="token"
    )

    geckodriver_autoinstaller.install()
    with webdriver.Firefox() as driver:
        driver.get(oauth_approve_url)

        try:
            WebDriverWait(driver, 600).until(
                lambda d: d.current_url.startswith(TWITCH_OAUTH_REDIRECT_URL)
            )
        except TimeoutException as ex:
            raise RuntimeError("Could not get Twitch OAuth access token.") from ex

        oauth_response = oauth_client.fetch_token(
            authorization_response=driver.current_url
        )
        return oauth_response["access_token"]


if __name__ == "__main__":
    with_oauth_redirect_server(get_twitch_oauth_token_implicit_flow)
