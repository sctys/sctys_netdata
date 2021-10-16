from requests_html import HTMLSession, AsyncHTMLSession
from selenium import webdriver
import asyncio
from arsenic import browsers, services, get_session
import urllib
import json
import os
import sys
import time
sys.path.append(os.environ['SCTYS_PROJECT'] + '/sctys_global_parameters')
from global_parameters import Path
sys.path.append(Path.UTILITIES_PROJECT)
from utilities_functions import set_logger, run_time_wrapper, retry_wrapper, async_retry_wrapper
sys.path.append(Path.NOTIFIER_PROJECT)
from notifiers import get_notifier
sys.path.append(Path.IO_PROJECT)
from file_io import FileIO
from stem import Signal
from stem.control import Controller
from netdata_utilities import html_checker_wrapper, randomize_consecutive_sleep, ResponseChecker, BrowserAction


class WebScrapper(object):

    SEMAPHORE = 1000
    BROWSER = 'chrome'
    SERVICE_REF = {'chrome': 'Chromedriver', 'firefox': 'Geckodriver'}
    NOTIFIER = 'slack'
    NUM_RETRY = 3
    RETRY_SLEEP = 10
    CONSECUTIVE_SLEEP = (0, 30)
    BROWSER_WAIT = 10
    EXCEPTION_ERROR_CODE = 999
    PREFIX_FAIL_FILE = 'web_scrapper_fail_load_list_'

    def __init__(self, project, logger):
        self.project = project
        self.logger = logger
        self.session = HTMLSession()
        self.asession = AsyncHTMLSession()
        self.driver = None
        self.service = None
        self.browser = None
        self.notifier = None
        self.io = FileIO(project, logger)
        self.loop = asyncio.get_event_loop()
        self.sema = asyncio.Semaphore(self.SEMAPHORE)
        self.fail_load_html = []

    def set_num_retry(self, num_retry):
        self.NUM_RETRY = num_retry

    def set_retry_sleep(self, retry_sleep):
        self.RETRY_SLEEP = retry_sleep

    def set_browser_wait(self, browser_wait):
        self.BROWSER_WAIT = browser_wait

    def set_consecutive_sleep(self, lower_time, upper_time):
        self.CONSECUTIVE_SLEEP = (lower_time, upper_time)

    def get_browser(self, asyn=False):
        if not asyn:
            options = getattr(webdriver, '{}Options'.format(self.BROWSER.capitalize()))()
            options.add_argument('--headless')
            if self.BROWSER == 'chrome':
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-gpu')
                options.add_argument('--disable-dev-shm-usage')
            self.driver = getattr(webdriver, self.BROWSER.capitalize())(**{'{}_options'.format(self.BROWSER): options})
        else:
            self.service = getattr(services, self.SERVICE_REF[self.BROWSER])()
            args = ['--headless']
            if self.BROWSER == 'chrome':
                args.append('--disable-gpu')
                args.append('--no-sandbox')
                args.append('--disable-dev-shm-usage')
            args = {'args': args}
            self.browser = getattr(browsers, self.BROWSER.capitalize())(**{'{}Options'.format(self.BROWSER): args})

    def get_notifier(self):
        self.notifier = get_notifier(self.NOTIFIER, self.project, self.logger)


    '''
    def renew_ip(self, asyn=True):
        with Controller.from_port(port=9051) as controller:
            controller.authenticate(password=self.TOR_PASSWORD)
            controller.signal(Signal.NEWNYM)
        if asyn:
            self.asession = AsyncHTMLSession()
            self.asession.proxies = self.WEB_SCRAPPER_PROXIES
            self.asession.headers['User-Agent'] = get_random_user_agent()
        else:
            self.session = HTMLSession()
            self.session.proxies = self.WEB_SCRAPPER_PROXIES
            self.session.headers['User-Agent'] = get_random_user_agent()
    '''

    def _load_html(self, url, static=True):
        try:
            html = self.session.get(url)
            if html.status_code == 200:
                if not static:
                    html.html.render()
                response = {'ok': True, 'message': html.html.html, 'url': url}
            else:
                response = {'ok': False, 'error': html.reason, 'error_code': html.status_code, 'url': url}
        except Exception as e:
            response = {'ok': False, 'error': e, 'error_code': self.EXCEPTION_ERROR_CODE, 'url': url}
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
                response = {'ok': False, 'error': html.reason, 'error_code': html.status_code, 'url': url}
        except Exception as e:
            response = {'ok': False, 'error': e, 'error_code': self.EXCEPTION_ERROR_CODE, 'url': url}
        return response

    def _browse_html(self, url, extra_action=None, *args):
        if extra_action is None:
            extra_action = BrowserAction.dummy_action
        try:
            driver = self.driver
            driver.get(url)
            driver = extra_action(driver, *args)
            response = {'ok': True, 'message': driver.page_source, 'url': url}
        except Exception as e:
            response = {'ok': False, 'error': e, 'error_code': self.EXCEPTION_ERROR_CODE, 'url': url}
        return response

    async def _async_browse_html(self, url, async_extra_action=None, *args):
        if async_extra_action is None:
            async_extra_action = BrowserAction.async_dummy_action
        try:
            async with self.sema, get_session(self.service, self.browser) as session:
                await session.get(url)
                session = await async_extra_action(session, *args)
                html = await session.get_page_source()
            response = {'ok': True, 'message': html, 'url': url}
        except Exception as e:
            response = {'ok': False, 'error': e, 'error_code': self.EXCEPTION_ERROR_CODE, 'url': url}
        return response

    @ staticmethod
    def extend_url(url, params):
        if params is None or params == {} or not isinstance(params, dict):
            return url
        else:
            return '?'.join([url, urllib.parse.urlencode(params)])

    def _api_call(self, method, url, params=None, **kwargs):
        if params is None:
            params = {}
        try:
            data = getattr(self.session, method)(url, params=params, **kwargs)
            if data.status_code == 200:
                response = {'ok': True, 'message': data.html.html, 'url': self.extend_url(url, params)}
            else:
                response = {'ok': False, 'error': data.reason, 'error_code': data.status_code,
                            'url': self.extend_url(url, params)}
        except Exception as e:
            response = {'ok': False, 'error': e, 'error_code': self.EXCEPTION_ERROR_CODE,
                        'url': self.extend_url(url, params)}
        return response

    async def _async_api_call(self, method, url, params=None, **kwargs):
        if params is None:
            params = {}
        try:
            data = await getattr(self.asession, method)(url, params=params, **kwargs)
            if data.status_code == 200:
                response = {'ok': True, 'message': data.html.html, 'url': self.extend_url(url, params)}
            else:
                response = {'ok': False, 'error': data.reason, 'error_code': data.status_code,
                            'url': self.extend_url(url, params)}
        except Exception as e:
            response = {'ok': False, 'error': e, 'error_code': self.EXCEPTION_ERROR_CODE,
                        'url': self.extend_url(url, params)}
        return response

    def clear_fail_load_list(self):
        self.fail_load_html = []

    def save_fail_load_list(self):
        if len(self.fail_load_html) > 0:
            file_name = self.PREFIX_FAIL_FILE + '{}.txt'.format(int(time.time()))
            self.io.save_file(self.fail_load_html, Path.TEMP_FOLDER, file_name, 'txt')
            self.io.notify_fail_file(True)

    def clear_temp_fail_file(self):
        fail_file_list = os.listdir(Path.TEMP_FOLDER)
        fail_file_list = [os.path.join(Path.TEMP_FOLDER, fail_file) for fail_file in fail_file_list
                          if self.PREFIX_FAIL_FILE in fail_file]
        [os.remove(fail_file) for fail_file in fail_file_list]

    def notify_fail_html(self, load):
        if self.notifier is None:
            self.get_notifier()
        if load:
            operation = 'loaded'
        else:
            operation = 'browsed'
        fail_list_html = [json.dumps(fail) for fail in self.fail_load_html]
        fail_list_str = '\n'.join(fail_list_html)
        if len(fail_list_str) > 0:
            message = 'The following html were not {} successfully:\n\n'.format(operation) + fail_list_str
            self.notifier.retry_send_message(message)

    def load_html(self, url, static=True, html_checker=None):
        response = retry_wrapper(
            self._load_html, html_checker_wrapper(html_checker), self.NUM_RETRY, self.RETRY_SLEEP, self.logger)(
            url, static)
        self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response.get('url', url), response['error']))
            self.fail_load_html.append({'url': url, 'static': static})
        time.sleep(randomize_consecutive_sleep(self.CONSECUTIVE_SLEEP[0], self.CONSECUTIVE_SLEEP[-1]))
        return response

    async def async_load_html(self, url, static=True, html_checker=None):
        response = await async_retry_wrapper(
            self._async_load_html, html_checker_wrapper(html_checker), self.NUM_RETRY, self.RETRY_SLEEP, self.logger)(
            url, static)
        self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response.get('url', url), response['error']))
            self.fail_load_html.append({'url': url, 'static': static})
        await asyncio.sleep(randomize_consecutive_sleep(self.CONSECUTIVE_SLEEP[0], self.CONSECUTIVE_SLEEP[-1]))
        return response

    def browser_simulator(self, url, extra_action=None, *args, html_checker=None):
        if self.driver is None:
            self.get_browser()
        response = retry_wrapper(
            self._browse_html, html_checker_wrapper(html_checker), self.NUM_RETRY, self.RETRY_SLEEP, self.logger)(
            url, extra_action, *args)
        self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response.get('url', url), response['error']))
            self.fail_load_html.append({'url': url, 'args': args})
        self.driver.close()
        self.driver = None
        time.sleep(randomize_consecutive_sleep(self.CONSECUTIVE_SLEEP[0], self.CONSECUTIVE_SLEEP[-1]))
        return response

    async def async_browser_simulator(self, url, async_extra_action=None, *args, html_checker=None):
        if self.browser is None:
            self.get_browser(True)
        response = await async_retry_wrapper(
            self._browse_html, html_checker_wrapper(html_checker), self.NUM_RETRY, self.RETRY_SLEEP, self.logger)(
            url, async_extra_action, *args)
        self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response.get('url', url), response['error']))
            self.fail_load_html.append({'url': url, 'args': args})
        await asyncio.sleep(randomize_consecutive_sleep(self.CONSECUTIVE_SLEEP[0], self.CONSECUTIVE_SLEEP[-1]))
        return response

    def api_call(self, method, url, params=None, api_checker=None, **kwargs):
        response = retry_wrapper(
            self._api_call, html_checker_wrapper(api_checker), self.NUM_RETRY, self.RETRY_SLEEP, self.logger)(
            method, url, params, **kwargs)
        self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response.get('url', url), response['error']))
            self.fail_load_html.append({'url': url, 'params': params})
        time.sleep(randomize_consecutive_sleep(self.CONSECUTIVE_SLEEP[0], self.CONSECUTIVE_SLEEP[-1]))
        return response

    async def async_api_call(self, method, url, params=None, api_checker=None, **kwargs):
        response = await async_retry_wrapper(
            self._api_call, html_checker_wrapper(api_checker), self.NUM_RETRY, self.RETRY_SLEEP, self.logger)(
            method, url, params, **kwargs)
        self.logger.debug('{} loaded'.format(response['url']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response.get('url'), response['error']))
            self.fail_load_html.append({'url': url, 'params': params})
        await asyncio.sleep(randomize_consecutive_sleep(self.CONSECUTIVE_SLEEP[0], self.CONSECUTIVE_SLEEP[-1]))
        return response

    def save_html(self, html, file_path, file_name, **kwargs):
        self.io.save_file(html, file_path, file_name, 'html', **kwargs)
        self.io.notify_fail_file(True)

    def save_api(self, data, file_path, file_name, **kwargs):
        self.io.save_file(data, file_path, file_name, 'txt', **kwargs)
        self.io.notify_fail_file(True)

    @ staticmethod
    def match_url_file_name(url_list, file_name_list):
        return {url: file_name for url, file_name in zip(url_list, file_name_list)}

    def match_params_file_name(self, url, params, file_name_list):
        url_list = [self.extend_url(url, param) for param in params]
        return self.match_url_file_name(url_list, file_name_list)

    '''
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
    '''

    def load_multiple_html(self, url_list, file_name_list, file_path, static=True, html_checker=None, asyn=True):
        self.clear_fail_load_list()
        url_file_dict = self.match_url_file_name(url_list, file_name_list)
        if asyn:
            async def async_load_save_html(url):
                resp = await self.async_load_html(url, static, html_checker)
                if resp['ok']:
                    file_name = url_file_dict[url]
                    self.save_html(resp['message'], file_path, file_name)
            tasks = [asyncio.ensure_future(async_load_save_html(url)) for url in url_list]
            self.loop.run_until_complete(asyncio.gather(*tasks))
        else:
            def load_save_html(url):
                resp = self.load_html(url, static, html_checker)
                if resp['ok']:
                    file_name = url_file_dict[url]
                    self.save_html(resp['message'], file_path, file_name)
                list(map(load_save_html, url_list))
        self.notify_fail_html(True)
        self.save_fail_load_list()

    def browse_multiple_html(self, url_list, file_name_list, file_path, extra_action=None, *args, html_checker=None,
                             asyn=True):
        self.clear_fail_load_list()
        url_file_dict = self.match_url_file_name(url_list, file_name_list)
        if asyn:
            async def async_browse_save_html(url):
                resp = await self.async_browser_simulator(url, extra_action, *args, html_checker)
                if resp['ok']:
                    file_name = url_file_dict[url]
                    self.save_html(resp['message'], file_path, file_name)
            tasks = [asyncio.ensure_future(async_browse_save_html(url)) for url in url_list]
            self.loop.run_until_complete(asyncio.gather(*tasks))
        else:
            def browse_save_html(url):
                resp = self.browser_simulator(url, extra_action, *args, html_checker)
                if resp['ok']:
                    file_name = url_file_dict[url]
                    self.save_html(resp['message'], file_path, file_name)
            list(map(browse_save_html, url_list))
        self.notify_fail_html(False)
        self.save_fail_load_list()

    def load_multiple_api(self, method, url_list, file_name_list, file_path, params=None, api_checker=None, asyn=True,
                          **kwargs):
        self.clear_fail_load_list()
        url_file_dict = self.match_url_file_name(url_list, params, file_name_list)
        if asyn:
            async def async_api_call_save(url, param):
                resp = await self.async_api_call(method, url, param, api_checker, **kwargs)
                if resp['ok']:
                    file_name = url_file_dict[self.extend_url(url, param)]
                    self.save_api(resp['message'], file_path, file_name)
            if not isinstance(params, list):
                tasks = [asyncio.ensure_future(async_api_call_save(url, params)) for url in url_list]
            else:
                tasks = [asyncio.ensure_future(async_api_call_save(url, param)) for url, param in zip(url_list, params)]
            self.loop.run_until_complete(asyncio.gather(*tasks))
        else:
            def api_call_save(url, param):
                resp = self.api_call(method, url, param, api_checker, **kwargs)
                if resp['ok']:
                    file_name = url_file_dict[self.extend_url(url, param)]
                    self.save_api(resp['message'], file_path, file_name)
            if not isinstance(params, list):
                list(map(lambda u: api_call_save(u, params), url_list))
            else:
                list(map(api_call_save, url_list, params))
        self.notify_fail_html(True)
        self.save_fail_load_list()

    '''
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

    def retry_load_multiple_api(self, method, api_checker=None, file_name=None, asyn=True, verbose=False, **kwargs):
        if file_name is not None:
            self.load_fail_load_list(file_name)
        fail_load_html = [(fail['url'], fail['params']) for fail in self.fail_load_html]
        url_list, params = ([fail[index] for fail in fail_load_html] for index in range(2))
        response = self.load_multiple_api(method, url_list, params, api_checker, asyn, verbose, **kwargs)
        return response
    '''

'''
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


def test_call_api(url, method, file_name, params=None, api_checker=None, asyn=False):
    ws = WebScrapper()
    if asyn:
        response = ws.loop.run_until_complete(ws.async_api_call(method, url, params, api_checker))
    else:
        response = ws.api_call(method, url, params, api_checker)
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


def test_load_multiple_api(method, url_list, file_name_list, params=None, api_checker=None, asyn=False):
    ws = WebScrapper()
    response = ws.load_multiple_api(method, url_list, params, api_checker, asyn)
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


def test_fail_api(method, fail_url_list, fail_params_list, fail_file_name_list, api_checker=None):
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
    response = ws.retry_load_multiple_api(method, api_checker)
    fail_url_list = [res['url'] for res in response]
    fail_file_name_dict = ws.match_url_file_name(fail_url_list, fail_file_name_list)
    ws.save_multiple_api(ws.WEB_SCRAPPER_FILE_SAVE_MODE, response, os.getcwd(), fail_file_name_dict)
    ws.clear_temp_fail_html()


def test_renew_ip():
    ws = WebScrapper()
    while True:
        print(ws.session.get('http://icanhazip.com/').html.html)
        ws.renew_ip(False)
        time.sleep(10)




if __name__ == '__main__':
    run_test_load_html = False
    run_test_browse_html = False
    run_test_call_api = False
    run_test_load_multiple_html = False
    run_test_browse_multiple_html = False
    run_test_load_multiple_api = False
    run_test_fail_load = False
    run_test_fail_browse = False
    run_test_fail_api = False
    run_test_renew_ip = True
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
        test_call_api('get', api_url, 'sync_api_call.json',
                      params={'date': '2015-11-01', 'day_night': 'day', 'type': '3pick1'},
                      api_checker=test_api_checker)
        test_call_api('get', api_url, 'async_api_call.json',
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
        test_load_multiple_api('get', url_list, file_name_list, params_list, test_api_checker)
        file_name_list = ['async_api_call_{}.json'.format(index) for index in range(1, 4)]
        test_load_multiple_api('get', url_list, file_name_list, params_list, test_api_checker, True)
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
        test_fail_api('get', url_list, params_list, file_name_list, test_api_checker)
    elif run_test_renew_ip:
        test_renew_ip()
'''






