NOTIFIER_PATH = '/media/sctys/Seagate Expansion Drive/Projects/sctys_notify'
IO_PATH = '/media/sctys/Seagate Expansion Drive/Projects/sctys_io'
TEMP_PATH = '/media/sctys/Seagate Expansion Drive/Projects/tmp'


class WebScrapperSetting(object):
    WEB_SCRAPPER_LOGGER_PATH = '/media/sctys/Seagate Expansion Drive/Projects/Log/log_sctys_netdata'
    WEB_SCRAPPER_LOGGER_FILE = 'web_scrapper.log'
    WEB_SCRAPPER_LOGGER_LEVEL = 'DEBUG'
    WEB_SCRAPPER_SEMAPHORE = 1000
    WEB_SCRAPPER_BROWSER = 'chrome'
    WEB_SCRAPPER_NOTIFIER = 'slack'
    WEB_SCRAPPER_FILE_SAVE_MODE = 'thread'
    WEB_SCRAPPER_NUM_RETRY = 5
    WEB_SCRAPPER_SLEEP = 10
    WEB_SCRAPPER_BROWSER_WAIT = 60
    WEB_SCRAPPER_SERVICE_REF = {'chrome': 'Chromedriver', 'firefox': 'Geckodriver'}

