import os
from password import tor_password

NOTIFIER_PATH = os.environ["SCTYS_PROJECT"] + "/sctys_notify"
IO_PATH = os.environ["SCTYS_PROJECT"] + "/sctys_io"
TEMP_PATH = os.environ["SCTYS_PROJECT"] + "/tmp"


class WebScrapperSetting(object):
    WEB_SCRAPPER_LOGGER_PATH = os.environ["SCTYS_PROJECT"] + "/Log/log_sctys_netdata"
    WEB_SCRAPPER_LOGGER_FILE = "web_scrapper.log"
    WEB_SCRAPPER_LOGGER_LEVEL = "DEBUG"
    WEB_SCRAPPER_SEMAPHORE = 1000
    WEB_SCRAPPER_BROWSER = "chrome"
    WEB_SCRAPPER_NOTIFIER = "slack"
    WEB_SCRAPPER_FILE_SAVE_MODE = "thread"
    WEB_SCRAPPER_NUM_RETRY = 3
    WEB_SCRAPPER_RETRY_SLEEP = 10
    WEB_SCRAPPER_BROWSER_WAIT = 10
    WEB_SCRAPPER_SERVICE_REF = {"chrome": "Chromedriver", "firefox": "Geckodriver"}
    WEB_SCRAPPER_PROXIES = {
        "http": "socks5://127.0.0.1:9050",
        "https": "socks5://127.0.0.1:9050",
    }
    WEB_SCRAPPER_EXCEPTION_ERROR_CODE = 999
    TOR_PASSWORD = tor_password


class WebsocketSetting(object):
    WEBSOCKET_LOGGER_PATH = os.environ["SCTYS_PROJECT"] + "/Log/log_sctys_netdata"
    WEBSOCKET_LOGGER_FILE = "websocket.log"
    WEBSOCKET_LOGGER_LEVEL = "DEBUG"
    WEBSOCKET_NOTIFIER = "slack"
    WEBSOCKET_NUM_RETRY = 5
    WEBSOCKET_RETRY_SLEEP = 10
