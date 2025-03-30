import time
import logging
import os
import json
import random
import asyncio
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from netdata_setting import WebScrapperSetting
#from fake_useragent import UserAgent


def message_checker(response, html_checker=None):
    if html_checker is None:
        html_checker = ResponseChecker.dummy_checker
    if not response['ok']:
        result = {'status': False, 'message': response['error'], 'code': response['error_code']}
        if response['error_code'] >= 500:
            result['terminate'] = False
        else:
            result['terminate'] = True
    else:
        html_check = html_checker(response['message'])
        if html_check['status']:
            result = {'status': True}
        else:
            result = {'status': False, 'message': html_check['message'], 'code': None,
                      'terminate': html_check.get('terminate', True)}
    return result


def html_checker_wrapper(html_checker=None):
    def message_checker_with_html_checker(response):
        return message_checker(response, html_checker)
    return message_checker_with_html_checker


def randomize_consecutive_sleep(lower_bound, upper_bound):
    return random.randint(lower_bound, upper_bound)


def extract_text_from_html(html, element=None, index=0):
    soup = BeautifulSoup(html, 'html.parser')
    if element is None:
        text = soup.get_text()
    else:
        text = soup.select(element)[index].get_text()
    return text


#def get_random_user_agent():
#    ua = UserAgent()
#    return ua.random


async def no_auth(websocket):
    return websocket


def print_websocket_response(response, *args, **kwargs):
    print(response)


def dummy_response_processor(response):
    return json.loads(response)


class ResponseChecker(object):

    @ staticmethod
    def dummy_checker(html):
        return {'status': True}

    @ staticmethod
    def check_api_element_exist(data, key, value=None):
        try:
            if isinstance(data, str):
                data = json.loads(data)
            elif isinstance(data, bytes):
                data = json.load(data)
        except json.decoder.JSONDecodeError:
            return {'status': False, 'message': 'Improper json text {}'.format(data), 'terminate': False}
        if data is None:
            return {'status': False, 'message': 'The data is null'}
        if key in data and (value is None or data[key] == value):
            return {'status': True}
        else:
            if key not in data:
                return {'status': False, 'message': 'Key {} not exist'.format(key)}
            elif data[key] != value:
                return {'status': False, 'message': 'Key {} does not have value {}'.format(key, value)}

    @ staticmethod
    def check_api_result_has_content(data, key_list):
        try:
            if isinstance(data, str):
                data = json.loads(data)
            elif isinstance(data, bytes):
                data = json.load(data)
        except json.decoder.JSONDecodeError:
            return {'status': False, 'message': 'Improper json text {}'.format(data), 'terminate': False}
        if data is None:
            return {'status': False, 'message': 'The data is null'}
        if key_list[0] not in data:
            return {'status': False, 'message': 'Key {} not exist'.format(key_list[0])}
        for ind, key in enumerate(key_list[:-1]):
            outer_key = key_list[ind]
            inner_key = key_list[ind + 1]
            if inner_key not in data[outer_key]:
                return {'status': False, 'message': 'Key {} not exist'.format(inner_key)}
            data = data[outer_key]
        data = data[key_list[-1]]
        if data and data is not None and len(data) > 0:
            return {'status': True}
        else:
            return {'status': False, 'message': 'Key {} has no content'.format(key_list[-1])}

    @ staticmethod
    def check_api_text_exist(data, text):
        if text in data:
            return {'status': True}
        else:
            return {'status': False, 'message': 'Text {} does not exist'.format(text)}

    @staticmethod
    def check_api_text_exist_by_count(data, text, min_times=1):
        if len(data.split(text)) > min_times:
            return {'status': True}
        else:
            return {'status': False, 'message': 'Text {} does not exist'.format(text)}

    @staticmethod
    def check_api_text_not_exist(data, text):
        if text not in data:
            return {'status': True}
        else:
            return {'status': False, 'message': 'Text {} exist'.format(text)}

    @ staticmethod
    def check_either_api_text_exist(data, text_list):
        for text in text_list:
            if text in data:
                return {'status': True}
        return {'status': False, 'message': 'None of {} exist'.format(','.join(text_list))}

    @ staticmethod
    def check_api_text_not_empty(data):
        if len(data) > 0:
            return {'status': True}
        return {'status': False, 'message': 'data is empty'}

    @staticmethod
    def check_api_data_not_empty(data):
        try:
            if isinstance(data, str):
                data = json.loads(data)
            elif isinstance(data, bytes):
                data = json.load(data)
        except json.decoder.JSONDecodeError:
            return {'status': False, 'message': 'Improper json text {}'.format(data), 'terminate': False}
        if data is None:
            return {'status': False, 'message': 'The data is null'}
        if len(data) > 0:
            return {'status': True}
        return {'status': False, 'message': 'data is empty'}

    @ staticmethod
    def check_html_element_exist(html, element, min_times=1):
        soup = BeautifulSoup(html, 'html.parser')
        if len(soup.select(element)) >= min_times:
            return {'status': True}
        else:
            return {'status': False, 'message': 'Element {} not appearing at least {} times'.format(element, min_times)}

    @ staticmethod
    def check_html_element_text_not_exist(html, element, txt):
        soup = BeautifulSoup(html, 'html.parser')
        if txt in soup.select(element)[0].text:
            return {'status': False, 'message': '{} exist in element {}'.format(txt, element)}
        else:
            return {'status': True}

    @ staticmethod
    def check_html_element_text_exist(html, element, txt):
        soup = BeautifulSoup(html, 'html.parser')
        if soup.find(element, text=lambda t: t and txt in t):
            return {'status': True}
        else:
            return {'status': False, 'message': '{} not exist in {}'.format(txt, element)}

    @ staticmethod
    def check_multiple_html_elements_exist(html, element_list, min_times=1):
        soup = BeautifulSoup(html, 'html.parser')
        if isinstance(min_times, list):
            assert len(element_list) == len(min_times)
            for element, min_t in zip(element_list, min_times):
                if len(soup.select(element)) < min_t:
                    return {'status': False,
                            'message': 'Element {} not appearing at least {} times'.format(element, min_t)}
        else:
            for element in element_list:
                if len(soup.select(element)) < min_times:
                    return {'status': False,
                            'message': 'Element {} not appearing at least {} times'.format(element, min_times)}
        return {'status': True}


    @staticmethod
    def check_html_element_not_exist(html, element):
        soup = BeautifulSoup(html, 'html.parser')
        if len(soup.select(element)) == 0:
            return {'status': True}
        else:
            return {'status': False, 'message': 'Element {} appearing'.format(element)}

    @ staticmethod
    def check_either_html_element_exist(html, element_list):
        soup = BeautifulSoup(html, 'html.parser')
        if sum([len(soup.select(element)) for element in element_list]) > 0:
            return {'status': True}
        else:
            return {'status': False, 'message': 'None of Element {} appearing'.format(','.join(element_list))}

    @ staticmethod
    def check_html_text_exist(html, text, min_times=1):
        soup = BeautifulSoup(html, 'html.parser')
        txt = soup.get_text()
        if text in txt:
            return {'status': True}
        else:
            return {'status': False, 'message': 'Text {} not appearing at least {} times'.format(text, min_times)}


class BrowserAction(object):

    @ staticmethod
    def dummy_action(driver, *args):
        return driver

    @ staticmethod
    async def async_dummy_action(session, *args):
        return session

    @ staticmethod
    def wait_for_element(driver, load_element, browser_wait):
        WebDriverWait(driver, browser_wait).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, load_element)))
        return driver

    @staticmethod
    def wait_for_text(driver, element, text, browser_wait):
        WebDriverWait(driver, browser_wait).until(
            EC.text_to_be_present_in_element((By.CSS_SELECTOR, element), text))
        return driver

    @ staticmethod
    def wait(driver, browser_wait):
        driver.implicitly_wait(browser_wait)
        return driver

    @ staticmethod
    def select_dropdown_box(driver, dropdown_box_element, option_index, option_type, load_element, browser_wait):
        WebDriverWait(driver, browser_wait).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, dropdown_box_element)))
        dropdown_box = Select(driver.find_element_by_css_selector(dropdown_box_element))
        if option_type == 'text':
            selector = dropdown_box.select_by_visible_text
        elif option_type == 'value':
            selector = dropdown_box.select_by_value
        else:
            selector = dropdown_box.select_by_index
        selector(option_index)
        WebDriverWait(driver, WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, load_element)))
        return driver

    @ staticmethod
    async def async_wait_for_element(session, load_element, browser_wait):
        await session.wait_for_element(browser_wait, load_element)
        return session

    @ staticmethod
    async def async_wait(session):
        await session.wait(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT)
        return session

    @ staticmethod
    async def async_select_dropdown_box(session, dropdown_box_element, option_tag, load_element):
        await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, dropdown_box_element)
        dropdown_box = await session.get_element(dropdown_box_element)
        await dropdown_box.click()
        selection = await dropdown_box.get_element(option_tag)
        await selection.click()
        await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, load_element)
        return session

    @ staticmethod
    async def async_click_option(session, option_element, load_element):
        await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, option_element)
        option_button = await session.get_element(option_element)
        await option_button.click()
        await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, load_element)
        return session

class PlaywrightAction:
    @staticmethod
    def dummy_action(page, *args):
        return page