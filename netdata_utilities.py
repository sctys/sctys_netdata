import time
import logging
import os
import json
import asyncio
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from netdata_setting import WebScrapperSetting


def set_logger(logger_path, logger_file_name, logger_level, logger_name):
    logger_file = os.path.join(logger_path, logger_file_name)
    logging.basicConfig(level=getattr(logging, logger_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        handlers=[logging.FileHandler(filename=logger_file), logging.StreamHandler()])
    logger = logging.getLogger(logger_name)
    return logger


def retry(func, *params, checker, html_checker, num_retry, sleep_time, logger, **kwargs):
    count = 0
    run_success = False
    while count < num_retry and not run_success:
        response = func(*params, **kwargs)
        if not checker(response, html_checker)['status']:
            logger.error('Fail attempt {} for function {}: {}'.format(count + 1, func.__name__,
                                                                      checker(response, html_checker)['message']))
            time.sleep(sleep_time)
            count += 1
        else:
            run_success = True
    if not run_success and response['ok']:
        response = {'ok': False, 'error': checker(response, html_checker)['message'], 'url': response['url']}
    return response


async def async_retry(func, *params, checker, html_checker, num_retry, sleep_time, logger, **kwargs):
    count = 0
    run_success = False
    while count < num_retry and not run_success:
        response = await func(*params, **kwargs)
        if not checker(response, html_checker)['status']:
            logger.error('Fail attempt {} for function {}: {}'.format(count + 1, func.__name__,
                                                                      checker(response, html_checker)['message']))
            await asyncio.sleep(sleep_time)
            count += 1
        else:
            run_success = True
    if not run_success and response['ok']:
        response = {'ok': False, 'error': checker(response, html_checker)['message'], 'url': response['url']}
    return response


def extract_text_from_html(html, element=None, index=0):
    soup = BeautifulSoup(html, 'html.parser')
    if element is None:
        text = soup.get_text()
    else:
        text = soup.select(element)[index].get_text()
    return text


def check_api_element_exist(data, key, value=None):
    if isinstance(data, str):
        data = json.loads(data)
    elif isinstance(data, bytes):
        data = json.load(data)
    if key in data and (value is None or data[key] == value):
        return {'status': True}
    else:
        if key not in data:
            return {'status': False, 'message': 'Key {} not exist'.format(key)}
        elif data[key] != value:
            return {'status': False, 'message': 'Key {} does not have value {}'.format(key, value)}


def check_api_text_exist(data, text):
    if text in data:
        return {'status': True}
    else:
        return {'status': False, 'message': 'Text {} does not exist'.format(text)}

def check_html_element_exist(html, element, min_times=1):
    soup = BeautifulSoup(html, 'html.parser')
    if len(soup.select(element)) >= min_times:
        return {'status': True}
    else:
        return {'status': False, 'message': 'Element {} not appearing at least {} times'.format(element, min_times)}


def check_html_text_exist(html, text, min_times=1):
    soup = BeautifulSoup(html, 'html.parser')
    txt = soup.get_text()
    if text in txt:
        return {'status': True}
    else:
        return {'status': False, 'message': 'Text {} not appearing at least {} times'.format(text, min_times)}

def wait_for_element(driver, load_element):
    WebDriverWait(driver, WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, load_element)))
    return driver

def select_dropdown_box(driver, dropdown_box_element, option_index, option_type, load_element):
    WebDriverWait(driver, WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT).until(
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


async def async_wait_for_element(session, load_element):
    await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, load_element)
    return session

async def async_wait(session):
    await session.wait(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT)
    return session

async def async_select_dropdown_box(session, dropdown_box_element, option_tag, load_element):
    await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, dropdown_box_element)
    dropdown_box = await session.get_element(dropdown_box_element)
    await dropdown_box.click()
    selection = await dropdown_box.get_element(option_tag)
    await selection.click()
    await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, load_element)
    return session