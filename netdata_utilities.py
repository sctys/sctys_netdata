import time
import logging
import os
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


def retry(func, *params, checker, html_checker, num_retry, sleep_time, logger):
    count = 0
    run_success = False
    while count < num_retry and not run_success:
        response = func(*params)
        if not checker(response, html_checker)['status']:
            logger.error('Fail attempt {} for function {}: {}'.format(count + 1, func.__name__,
                                                                      checker(response, html_checker)['message']))
            time.sleep(sleep_time)
            count += 1
        else:
            run_success = True
    return response


async def async_retry(func, *params, checker, html_checker, num_retry, sleep_time, logger):
    count = 0
    run_success = False
    while count < num_retry and not run_success:
        response = await func(*params)
        if not checker(response, html_checker)['status']:
            logger.error('Fail attempt {} for function {}: {}'.format(count + 1, func.__name__,
                                                                      checker(response, html_checker)['message']))
            await asyncio.sleep(sleep_time)
            count += 1
        else:
            run_success = True
    return response


def check_html_element_exist(html, element, min_times=1):
    soup = BeautifulSoup(html, 'html.parser')
    if len(soup.select(element)) >= min_times:
        return {'status': True}
    else:
        return {'status': False, 'message': 'Element {} not appearing at least {} times'.format(element, min_times)}


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


async def async_select_dropdown_box(session, dropdown_box_element, option_tag, load_element):
    await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, dropdown_box_element)
    dropdown_box = await session.get_element(dropdown_box_element)
    await dropdown_box.click()
    selection = await dropdown_box.get_element(option_tag)
    await selection.click()
    await session.wait_for_element(WebScrapperSetting.WEB_SCRAPPER_BROWSER_WAIT, load_element)
    return session