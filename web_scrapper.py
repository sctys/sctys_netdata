from requests_html import HTMLSession, AsyncHTMLSession
from selenium import webdriver
import asyncio
from arsenic import browsers, services, get_session
from bs4 import BeautifulSoup
import urllib
import json
import os
from netdata_setting import NOTIFIER_PATH, IO_PATH, TEMP_PATH, WebScrapperSetting
from netdata_utilities import set_logger, retry, async_retry, check_html_element_exist, select_dropdown_box, \
    async_select_dropdown_box, check_api_element_exist
import sys
import time
sys.path.append(NOTIFIER_PATH)
sys.path.append(IO_PATH)
from notifiers import send_message
from file_io import FileIO


class WebScrapper(WebScrapperSetting):

    def __init__(self):
        self.logger = None
        self.set_logger()
        self.session = HTMLSession()
        self.asession = AsyncHTMLSession()
        self.driver = None
        self.service = None
        self.browser = None
        self.loop = asyncio.get_event_loop()
        self.sema = asyncio.Semaphore(self.WEB_SCRAPPER_SEMAPHORE)
        self.io = FileIO()
        self.fail_load_html = []
        self.get_browser()
        self.get_browser(True)

    def set_logger(self):
        self.logger = set_logger(self.WEB_SCRAPPER_LOGGER_PATH, self.WEB_SCRAPPER_LOGGER_FILE,
                                 self.WEB_SCRAPPER_LOGGER_LEVEL, __name__)

    def get_browser(self, asyn=False):
        BROWSER = self.WEB_SCRAPPER_BROWSER
        if not asyn:
            options = getattr(webdriver, '{}Options'.format(BROWSER.capitalize()))()
            options.add_argument('--headless')
            self.driver = getattr(webdriver, BROWSER.capitalize())(**{'{}_options'.format(BROWSER): options})
        else:
            self.service = getattr(services, self.WEB_SCRAPPER_SERVICE_REF[BROWSER])()
            args = ['--headless']
            if BROWSER == 'chrome':
                args.append('--disable-gpu')
            args = {'args': args}
            self.browser = getattr(browsers, BROWSER.capitalize())(**{'{}Options'.format(BROWSER): args})

    def _load_html(self, url, static=True):
        try:
            html = self.session.get(url)
            if html.status_code == 200:
                if not static:
                    html.html.render()
                response = {'ok': True, 'message': html.html.html, 'url': url}
            else:
                response = {'ok': False, 'error': html.reason, 'url': url}
        except Exception as e:
            response = {'ok': False, 'error': e, 'url': url}
        return response

    async def _async_load_html(self, url, static=True):
        try:
            async with self.sema:
                html = await self.asession.get(url)
            if html.status_code == 200:
                if not static:
                    await html.html.arender()
                response = {'ok': True, 'message': html.html.html, 'url': url}
            else:
                response = {'ok': False, 'error': html.reason, 'url': url}
        except Exception as e:
            response = {'ok': False, 'error': e, 'url': url}
        return response

    def _browse_html(self, url, extra_action=None, *args):
        if extra_action is None:
            extra_action = self._dummy_action
        try:
            self.driver.get(url)
            self.driver = extra_action(self.driver, *args)
            response = {'ok': True, 'message': self.driver.page_source, 'url': url}
        except Exception as e:
            response = {'ok': False, 'error': e, 'url': url}
        return response

    async def _async_browse_html(self, url, async_extra_action=None, *args):
        if async_extra_action is None:
            async_extra_action = self._async_dummy_action
        try:
            async with self.sema, get_session(self.service, self.browser) as session:
                await session.get(url)
                session = await async_extra_action(session, *args)
                html = await session.get_page_source()
            response = {'ok': True, 'message': html, 'url': url}
        except Exception as e:
            response = {'ok': False, 'error': e, 'url': url}
        return response

    @ staticmethod
    def _extend_url(url, params):
        if params is None or params == {} or not isinstance(params, dict):
            return url
        else:
            return '?'.join([url, urllib.parse.urlencode(params)])

    def _api_get(self, url, params=None):
        if params is None:
            params = {}
        try:
            data = self.session.get(url, params=params)
            if data.status_code == 200:
                response = {'ok': True, 'message': data.html.html, 'url': self._extend_url(url, params)}
            else:
                response = {'ok': False, 'error': data.reason, 'url': self._extend_url(url, params)}
        except Exception as e:
            response = {'ok': False, 'error': e, 'url': self._extend_url(url, params)}
        return response

    async def _async_api_get(self, url, params=None):
        if params is None:
            params = {}
        try:
            data = await self.asession.get(url, params=params)
            if data.status_code == 200:
                response = {'ok': True, 'message': data.html.html, 'url': self._extend_url(url, params)}
            else:
                response = {'ok': False, 'error': data.reason, 'url': self._extend_url(url, params)}
        except Exception as e:
            response = {'ok': False, 'error': e, 'url': self._extend_url(url, params)}
        return response

    def _message_checker(self, response, html_checker=None):
        if html_checker is None:
            html_checker = self._dummy_checker
        if not response['ok']:
            result = {'status': False, 'message': response['error']}
        else:
            html_check = html_checker(response['message'])
            if html_check['status']:
                result = {'status': True, 'message': None}
            else:
                result = {'status': False, 'message': html_check['message']}
        return result

    @ staticmethod
    def _dummy_checker(html):
        return {'status': True}

    @ staticmethod
    def _dummy_action(driver, *args):
        return driver

    @ staticmethod
    async def _async_dummy_action(session, *args):
        return session

    def clear_fail_load_list(self):
        self.fail_load_html = []

    def save_fail_load_list(self):
        if len(self.fail_load_html) > 0:
            file_name = 'web_scrapper_fail_load_list_{}.pkl'.format(int(time.time()))
            self.io.save_file(self.fail_load_html, TEMP_PATH, file_name, 'joblib')

    def load_fail_load_list(self, file_name):
        self.fail_load_html = self.io.load_file(TEMP_PATH, file_name, 'joblib')

    def notify_fail_html(self, load):
        if load:
            operation = 'loaded'
        else:
            operation = 'browsed'
        fail_list_html = [json.dumps(fail) for fail in self.fail_load_html]
        fail_list_str = '\n'.join(fail_list_html)
        if len(fail_list_str) > 0:
            message = 'The following html were not {} successfully:\n\n'.format(operation) + fail_list_str
            send_message(message, self.WEB_SCRAPPER_NOTIFIER)

    def load_html(self, url, static=True, html_checker=None, verbose=False):
        # if html_checker is None:
        #     html_checker = self._dummy_checker
        response = retry(self._load_html, url, static, checker=self._message_checker, html_checker=html_checker,
                         num_retry=self.WEB_SCRAPPER_NUM_RETRY, sleep_time=self.WEB_SCRAPPER_SLEEP, logger=self.logger)
        if verbose:
            self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response['url'], response['error']))
            self.fail_load_html.append({'url': url, 'static': static})
        return response

    async def async_load_html(self, url, static=True, html_checker=None, verbose=False):
        # if html_checker is None:
        #     html_checker = self._dummy_checker
        response = await async_retry(self._async_load_html, url, static, checker=self._message_checker,
                                     html_checker=html_checker, num_retry=self.WEB_SCRAPPER_NUM_RETRY,
                                     sleep_time=self.WEB_SCRAPPER_SLEEP, logger=self.logger)
        if verbose:
            self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response['url'], response['error']))
            self.fail_load_html.append({'url': url, 'static': static})
        return response

    def browser_simulator(self, url, extra_action=None, *args, html_checker=None, verbose=False):
        # if extra_action is None:
        #     extra_action = self._dummy_action
        # if html_checker is None:
        #     html_checker = self._dummy_checker
        response = retry(self._browse_html, url, extra_action, *args, checker=self._message_checker,
                         html_checker=html_checker,
                         num_retry=self.WEB_SCRAPPER_NUM_RETRY, sleep_time=self.WEB_SCRAPPER_SLEEP, logger=self.logger)
        if verbose:
            self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response['url'], response['error']))
            self.fail_load_html.append({'url': url, 'args': args})
        return response

    async def async_browser_simulator(self, url, async_extra_action=None, *args, html_checker=None, verbose=False):
        # if async_extra_action is None:
        #     async_extra_action = self._async_dummy_action
        # if html_checker is None:
        #     html_checker = self._dummy_checker
        response = await async_retry(self._async_browse_html, url, async_extra_action, *args,
                                     checker=self._message_checker, html_checker=html_checker,
                                     num_retry=self.WEB_SCRAPPER_NUM_RETRY, sleep_time=self.WEB_SCRAPPER_SLEEP,
                                     logger=self.logger)
        if verbose:
            self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response['url'], response['error']))
            self.fail_load_html.append({'url': url, 'args': args})
        return response

    def api_get(self, url, params=None, api_checker=None, verbose=False):
        response = retry(self._api_get, url, params, checker=self._message_checker, html_checker=api_checker,
                         num_retry=self.WEB_SCRAPPER_NUM_RETRY, sleep_time=self.WEB_SCRAPPER_SLEEP, logger=self.logger)
        if verbose:
            self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response['url'], response['error']))
            self.fail_load_html.append({'url': url, 'params': params})
        return response

    async def async_api_get(self, url, params=None, api_checker=None, verbose=False):
        response = await async_retry(self._async_api_get, url, params, checker=self._message_checker,
                                     html_checker=api_checker, num_retry=self.WEB_SCRAPPER_NUM_RETRY,
                                     sleep_time=self.WEB_SCRAPPER_SLEEP, logger=self.logger)
        if verbose:
            self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response['url'], response['error']))
            self.fail_load_html.append({'url': url, 'params': params})
        return response

    def save_html(self, html, file_path, file_name, verbose=False, **kwargs):
        self.io.save_file(html, file_path, file_name, 'html', verbose, **kwargs)

    def save_api(self, data, file_path, file_name, verbose=False, **kwargs):
        self.io.save_file(data, file_path, file_name, 'txt', verbose, **kwargs)

    @ staticmethod
    def match_url_file_name(url_list, file_name_list):
        return {url: file_name for url, file_name in zip(url_list, file_name_list)}

    def save_multiple_html(self, mode, response, file_path, file_name_dict, verbose=False, **kwargs):
        data_list = [(rep['url'], rep['message']) for rep in response if rep['ok']]
        url_list, html_list = ([data[index] for data in data_list] for index in range(2))
        file_name_list = [file_name_dict[url] for url in url_list]
        self.io.save_multiple_files(mode, html_list, file_path, file_name_list, 'html', verbose, **kwargs)

    def save_multiple_api(self, mode, response, file_path, file_name_dict, verbose=False, **kwargs):
        data_list = [(rep['url'], rep['message']) for rep in response if rep['ok']]
        url_list, api_list = ([data[index] for data in data_list] for index in range(2))
        file_name_list = [file_name_dict[url] for url in url_list]
        self.io.save_multiple_files(mode, api_list, file_path, file_name_list, 'txt', verbose, **kwargs)

    def load_multiple_html(self, url_list, static=True, html_checker=None, asyn=True, verbose=False):
        self.clear_fail_load_list()
        if asyn:
            if not isinstance(static, list):
                tasks = [asyncio.ensure_future(self.async_load_html(url, static, html_checker, verbose))
                         for url in url_list]
            else:
                tasks = [asyncio.ensure_future(self.async_load_html(url, stat, html_checker, verbose)) for url, stat
                         in zip(url_list, static)]
            response = self.loop.run_until_complete(asyncio.gather(*tasks))
        else:
            if not isinstance(static, list):
                response = list(map(lambda url: self.load_html(url, static, html_checker, verbose), url_list))
            else:
                response = list(map(lambda url, stat: self.load_html(url, stat, html_checker, verbose),
                                    url_list, static))
        self.notify_fail_html(True)
        self.save_fail_load_list()
        return response

    def browse_multiple_html(self, url_list, extra_action=None, *args, html_checker=None, asyn=True, verbose=False):
        self.clear_fail_load_list()
        if asyn:
            tasks = [asyncio.ensure_future(self.async_browser_simulator(url, extra_action, *args,
                                                                        html_checker=html_checker, verbose=verbose))
                     for url in url_list]
            response = self.loop.run_until_complete(asyncio.gather(*tasks))
        else:
            response = list(map(lambda url: self.browser_simulator(url, extra_action, *args,
                                                                   html_checker=html_checker, verbose=verbose),
                                url_list))
        self.notify_fail_html(False)
        self.save_fail_load_list()
        return response

    def load_multiple_api(self, url_list, params=None, api_checker=None, asyn=True, verbose=False):
        self.clear_fail_load_list()
        if asyn:
            if not isinstance(params, list):
                tasks = [asyncio.ensure_future(self.async_api_get(url, params, api_checker, verbose))
                         for url in url_list]
            else:
                tasks = [asyncio.ensure_future(self.async_api_get(url, param, api_checker, verbose)) for url, param
                         in zip(url_list, params)]
            response = self.loop.run_until_complete(asyncio.gather(*tasks))
        else:
            if not isinstance(params, list):
                response = list(map(lambda url: self.api_get(url, params, api_checker, verbose), url_list))
            else:
                response = list(map(lambda url, param: self.api_get(url, param, api_checker, verbose),
                                    url_list, params))
        self.notify_fail_html(True)
        self.save_fail_load_list()
        return response

    def retry_load_multiple_html(self, html_checker=None, file_name=None, asyn=True, verbose=False):
        if file_name is not None:
            self.load_fail_load_list(file_name)
        fail_load_html = [(fail['url'], fail['static']) for fail in self.fail_load_html]
        url_list, static = ([fail[index] for fail in fail_load_html] for index in range(2))
        response = self.load_multiple_html(url_list, static, html_checker, asyn, verbose)
        return response

    def retry_browse_multiple_html(self, extra_action=None, html_checker=None, file_name=None, asyn=True,
                                   verbose=False):
        if file_name is not None:
            self.load_fail_load_list(file_name)
        fail_load_html = [(fail['url'], fail['args']) for fail in self.fail_load_html]
        url_list, args = ([fail[index] for fail in fail_load_html] for index in range(2))
        args = args[0]
        response = self.browse_multiple_html(url_list, extra_action, *args, html_checker=html_checker, asyn=asyn,
                                             verbose=verbose)
        return response

    def retry_load_multiple_api(self, api_checker=None, file_name=None, asyn=True, verbose=False):
        if file_name is not None:
            self.load_fail_load_list(file_name)
        fail_load_html = [(fail['url'], fail['params']) for fail in self.fail_load_html]
        url_list, params = ([fail[index] for fail in fail_load_html] for index in range(2))
        response = self.load_multiple_api(url_list, params, api_checker, asyn, verbose)
        return response

    def clear_temp_fail_html(self):
        file_key = 'web_scrapper_fail_load_list_'
        fail_file_list = os.listdir(TEMP_PATH)
        fail_file_list = [os.path.join(TEMP_PATH, fail_file) for fail_file in fail_file_list
                          if file_key in fail_file]
        [os.remove(fail_file) for fail_file in fail_file_list]


def static_html_checker(html):
    return check_html_element_exist(html, 'table.color_white')


def dynamic_html_checker(html):
    return check_html_element_exist(html, 'table.tableBorderBlue.tdAlignC')


def test_api_checker(data):
    return check_api_element_exist(data, 'state', 'success')


def static_html_checker_multiple(html):
    return check_html_element_exist(html, 'table.arttext_black')


def browser_drop_down(driver, option_text):
    return select_dropdown_box(driver, 'select#dropScoreTeam', option_text, 'text', 'table#Table3.tdlink')


async def async_browser_drop_down(session, option_value):
    option_tag = 'option[value="{}"]'.format(option_value)
    session = await async_select_dropdown_box(session, 'select#dropScoreTeam', option_tag, 'table#Table3.tdlink')
    return session


def browser_drop_down_multiple(driver, option_text):
    return select_dropdown_box(driver, 'select#seasonList', option_text, 'text', 'table#Table3.tdlink')


async def async_browser_drop_down_multiple(session, option_value):
    option_tag = 'option[value="{}"]'.format(option_value)
    session = await async_select_dropdown_box(session, 'select#seasonList', option_tag, 'table#Table3.tdlink')
    return session


def browser_html_checker(html):
    soup = BeautifulSoup(html, 'html.parser')
    if len(soup.select('table#Table3.tdlink')) > 0:
        return {'status': True}
    else:
        return {'status': False, 'message': 'table#Table3.tdlink not exist'}


def test_load_html(url, file_name, static=True, html_checker=None, asyn=False):
    ws = WebScrapper()
    if asyn:
        response = ws.loop.run_until_complete(ws.async_load_html(url, static, html_checker))
    else:
        response = ws.load_html(url, static, html_checker)
    if response['ok']:
        ws.save_html(response['message'], os.getcwd(), file_name)
    else:
        print('Unable to load {}. {}'.format(url, response['error']))


def test_browse_html(url, file_name, extra_action=None, *args, html_checker=None, asyn=False):
    ws = WebScrapper()
    if asyn:
        response = ws.loop.run_until_complete(ws.async_browser_simulator(url, extra_action, *args,
                                                                         html_checker=html_checker))
    else:
        response = ws.browser_simulator(url, extra_action, *args, html_checker=html_checker)
    if response['ok']:
        ws.save_html(response['message'], os.getcwd(), file_name)
    else:
        print('Unable to browse {}. {}'.format(url, response['error']))


def test_call_api(url, file_name, params=None, api_checker=None, asyn=False):
    ws = WebScrapper()
    if asyn:
        response = ws.loop.run_until_complete(ws.async_api_get(url, params, api_checker))
    else:
        response = ws.api_get(url, params, api_checker)
    if response['ok']:
        ws.save_api(response['message'], os.getcwd(), file_name)
    else:
        print('Unable to call {}. {}'.format(url, response['error']))


def test_load_multiple_html(url_list, file_name_list, static=True, html_checker=None, asyn=False):
    ws = WebScrapper()
    response = ws.load_multiple_html(url_list, static, html_checker, asyn)
    file_name_dict = ws.match_url_file_name(url_list, file_name_list)
    ws.save_multiple_html(ws.WEB_SCRAPPER_FILE_SAVE_MODE, response, os.getcwd(), file_name_dict)


def test_browse_multiple_html(url_list, file_name_list, extra_action=None, *args, html_checker=None, asyn=False):
    ws = WebScrapper()
    response = ws.browse_multiple_html(url_list, extra_action, *args, html_checker=html_checker, asyn=asyn)
    file_name_dict = ws.match_url_file_name(url_list, file_name_list)
    ws.save_multiple_html(ws.WEB_SCRAPPER_FILE_SAVE_MODE, response, os.getcwd(), file_name_dict)


def test_load_multiple_api(url_list, file_name_list, params=None, api_checker=None, asyn=False):
    ws = WebScrapper()
    response = ws.load_multiple_api(url_list, params, api_checker, asyn)
    url_list = [res['url'] for res in response]
    file_name_dict = ws.match_url_file_name(url_list, file_name_list)
    ws.save_multiple_api(ws.WEB_SCRAPPER_FILE_SAVE_MODE, response, os.getcwd(), file_name_dict)


def test_fail_load(fail_url_list, fail_file_name_list, html_checker=None):
    ws = WebScrapper()
    ws.fail_load_html = [{'url': fail_url, 'static': False} for fail_url in fail_url_list]
    print('fail_load_html: {}'.format(ws.fail_load_html))
    ws.save_fail_load_list()
    print('Clear fail_load_list:')
    ws.clear_fail_load_list()
    print('fail_load_html: {}'.format(ws.fail_load_html))
    fail_file_name = os.listdir(TEMP_PATH)
    fail_file_name = [file_name for file_name in fail_file_name if 'web_scrapper_fail_load_list_' in file_name][-1]
    print('fail_load_file_name: {}'.format(fail_file_name))
    ws.load_fail_load_list(fail_file_name)
    print('fail_load_html: {}'.format(ws.fail_load_html))
    ws.notify_fail_html(True)
    response = ws.retry_load_multiple_html(html_checker)
    fail_file_name_dict = ws.match_url_file_name(fail_url_list, fail_file_name_list)
    ws.save_multiple_html(ws.WEB_SCRAPPER_FILE_SAVE_MODE, response, os.getcwd(), fail_file_name_dict)
    ws.clear_temp_fail_html()


def test_fail_browse(fail_url_list, *args, fail_file_name_list, extra_action=None, html_checker=None):
    ws = WebScrapper()
    ws.fail_load_html = [{'url': fail_url, 'args': args} for fail_url in fail_url_list]
    print('fail_load_html: {}'.format(ws.fail_load_html))
    ws.save_fail_load_list()
    print('Clear fail_load_list:')
    ws.clear_fail_load_list()
    print('fail_load_html: {}'.format(ws.fail_load_html))
    fail_file_name = os.listdir(TEMP_PATH)
    fail_file_name = [file_name for file_name in fail_file_name if 'web_scrapper_fail_load_list_' in file_name][-1]
    print('fail_load_file_name: {}'.format(fail_file_name))
    ws.load_fail_load_list(fail_file_name)
    print('fail_load_html: {}'.format(ws.fail_load_html))
    ws.notify_fail_html(False)
    response = ws.retry_browse_multiple_html(extra_action, html_checker)
    fail_file_name_dict = ws.match_url_file_name(fail_url_list, fail_file_name_list)
    ws.save_multiple_html(ws.WEB_SCRAPPER_FILE_SAVE_MODE, response, os.getcwd(), fail_file_name_dict)
    ws.clear_temp_fail_html()


def test_fail_api(fail_url_list, fail_params_list, fail_file_name_list, api_checker=None):
    ws = WebScrapper()
    ws.fail_load_html = [{'url': fail_url, 'params': fail_param} for fail_url, fail_param
                         in zip(fail_url_list, fail_params_list)]
    print('fail_load_api: {}'.format(ws.fail_load_html))
    ws.save_fail_load_list()
    print('Clear fail_load_list:')
    ws.clear_fail_load_list()
    print('fail_load_api: {}'.format(ws.fail_load_html))
    fail_file_name = os.listdir(TEMP_PATH)
    fail_file_name = [file_name for file_name in fail_file_name if 'web_scrapper_fail_load_list_' in file_name][-1]
    print('fail_load_file_name: {}'.format(fail_file_name))
    ws.load_fail_load_list(fail_file_name)
    print('fail_load_api: {}'.format(ws.fail_load_html))
    ws.notify_fail_html(True)
    response = ws.retry_load_multiple_api(api_checker)
    fail_url_list = [res['url'] for res in response]
    fail_file_name_dict = ws.match_url_file_name(fail_url_list, fail_file_name_list)
    ws.save_multiple_api(ws.WEB_SCRAPPER_FILE_SAVE_MODE, response, os.getcwd(), fail_file_name_dict)
    ws.clear_temp_fail_html()


if __name__ == '__main__':
    run_test_load_html = False
    run_test_browse_html = False
    run_test_call_api = False
    run_test_load_multiple_html = False
    run_test_browse_multiple_html = False
    run_test_load_multiple_api = False
    run_test_fail_load = False
    run_test_fail_browse = False
    run_test_fail_api = True
    if run_test_load_html:
        dynamic_url = 'https://racing.hkjc.com/racing/Info/meeting/RaceCard/english/Local/20190317/ST/1'
        static_url = 'https://racing.hkjc.com/racing/Info/meeting/Draw/english/Local/'
        test_load_html(static_url, 'sync_static.html', html_checker=static_html_checker)
        test_load_html(static_url, 'async_static.html', html_checker=static_html_checker, asyn=True)
        test_load_html(dynamic_url, 'sync_dynamic.html', static=False, html_checker=dynamic_html_checker)
        test_load_html(dynamic_url, 'async_dynamic.html', static=False, html_checker=dynamic_html_checker, asyn=True)
    elif run_test_browse_html:
        browser_url = 'http://info.nowgoal.com/en/League/36.html'
        test_browse_html(browser_url, 'sync_browse.html', browser_drop_down, 'Arsenal',
                         html_checker=browser_html_checker)
        test_browse_html(browser_url, 'async_browse.html', async_browser_drop_down, 19,
                         html_checker=browser_html_checker, asyn=True)
    elif run_test_call_api:
        api_url = 'http://racing-cw.api.atnext.com/race/game/one/date'
        test_call_api(api_url, 'sync_api_call.json',
                      params={'date': '2015-11-01', 'day_night': 'day', 'type': '3pick1'},
                      api_checker=test_api_checker)
        test_call_api(api_url, 'async_api_call.json',
                      params={'date': '2015-11-01', 'day_night': 'day', 'type': '3pick1'},
                      api_checker=test_api_checker, asyn=True)
    elif run_test_load_multiple_html:
        dynamic_url_list = [
            'https://racing.hkjc.com/racing/Info/meeting/RaceCard/english/Local/20190317/ST/{}'.format(index)
            for index in range(1, 4)]
        dynamic_file_name_list = ['sync_dynamic_{}.html'.format(index) for index in range(1, 4)]
        static_url_list = [
            'http://hk.racing.nextmedia.com/fullresult.php?date=20190313&page=0{}'.format(index)
            for index in range(1, 4)]
        static_file_name_list = ['sync_static_{}.html'.format(index) for index in range(1, 4)]
        test_load_multiple_html(static_url_list, static_file_name_list, True, static_html_checker_multiple)
        test_load_multiple_html(dynamic_url_list, dynamic_file_name_list, False, dynamic_html_checker)
        dynamic_file_name_list = ['async_dynamic_{}.html'.format(index) for index in range(1, 4)]
        static_file_name_list = ['async_static_{}.html'.format(index) for index in range(1, 4)]
        test_load_multiple_html(static_url_list, static_file_name_list, True, static_html_checker_multiple, True)
        test_load_multiple_html(dynamic_url_list, dynamic_file_name_list, False, dynamic_html_checker, True)
    elif run_test_browse_multiple_html:
        url_list = ['http://info.nowgoal.com/en/SubLeague/{}.html'.format(index) for index in (35, 37, 39)]
        file_name_list = ['sync_browse_{}.html'.format(index) for index in (35, 37, 39)]
        test_browse_multiple_html(url_list, file_name_list, browser_drop_down_multiple, '2017-2018',
                                  html_checker=browser_html_checker)
        file_name_list = ['async_browse_{}.html'.format(index) for index in (35, 37, 39)]
        test_browse_multiple_html(url_list, file_name_list, async_browser_drop_down_multiple, '2017-2018',
                                  html_checker=browser_html_checker, asyn=True)
    elif run_test_load_multiple_api:
        url_list = ['http://racing-cw.api.atnext.com/race/game/one/date'] * 3
        params_list = [{'date': '2018-4-25', 'day_night': 'night', 'type': '3pick1'},
                       {'date': '2018-11-7', 'day_night': 'night', 'type': '3pick1'},
                       {'date': '2019-3-2', 'day_night': 'day', 'type': '3pick1'}]
        file_name_list = ['sync_api_call_{}.json'.format(index) for index in range(1, 4)]
        test_load_multiple_api(url_list, file_name_list, params_list, test_api_checker)
        file_name_list = ['async_api_call_{}.json'.format(index) for index in range(1, 4)]
        test_load_multiple_api(url_list, file_name_list, params_list, test_api_checker, True)
    elif run_test_fail_load:
        url_list = [
            'https://racing.hkjc.com/racing/Info/meeting/RaceCard/english/Local/20190317/ST/{}'.format(index)
            for index in range(5, 7)]
        file_name_list = ['reload_{}.html'.format(index) for index in range(5, 7)]
        test_fail_load(url_list, file_name_list, dynamic_html_checker)
    elif run_test_fail_browse:
        url_list = ['http://info.nowgoal.com/en/League/{}.html'.format(index) for index in (34, 36)]
        file_name_list = ['rebrowse_{}.html'.format(index) for index in (34, 36)]
        test_fail_browse(url_list, '2017-2018', fail_file_name_list=file_name_list,
                         extra_action=async_browser_drop_down_multiple, html_checker=browser_html_checker)
    elif run_test_fail_api:
        url_list = ['http://racing-cw.api.atnext.com/race/game/one/date'] * 3
        params_list = [{'date': '2018-4-25', 'day_night': 'night', 'type': '3pick1'},
                       {'date': '2018-11-7', 'day_night': 'night', 'type': '3pick1'},
                       {'date': '2019-3-2', 'day_night': 'day', 'type': '3pick1'}]
        file_name_list = ['recall_api_{}.json'.format(index) for index in range(1, 4)]
        test_fail_api(url_list, params_list, file_name_list, test_api_checker)







