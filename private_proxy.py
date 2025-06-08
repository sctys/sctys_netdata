from webshare_token import webshare_token
from urllib.parse import urlparse
import json
import requests
import random
import time
import datetime


class WebSharePrivateProxy:

    PROXY_LIST_URL = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&valid=true&page_size=100"  # format
    PLAN_URL = "https://proxy.webshare.io/api/v2/subscription/plan/"
    PROXY_HEADER = {"Authorization": f"Token {webshare_token}"}
    RESULTS = "results"
    USER_NAME = "username"
    PASSWORD = "password"
    ADDRESS = "proxy_address"
    VALID = "valid"
    PORT = "port"
    HTTP = "http://"
    HTTPS = "https://"
    ID = 'id'
    COUNT = 'count'
    NEXT = 'next'
    AUTOMATIC_REFRESH_NEXT_AT = "automatic_refresh_next_at"
    NUM_RETRY = 30
    REFRESH_PERIOD_MINUTE = 30
    BLOCK_COUNT = 3

    def __init__(self, logger):
        self.logger = logger
        self.full_list = []
        self.active_list = []
        self.block_proxy_dict = {}
        self.last_update = None
        self.next_refresh_time = None
        self.get_proxy_list()

    def _parse_proxy_data(self, proxy_data):
        user_name = proxy_data[self.USER_NAME]
        password = proxy_data[self.PASSWORD]
        address = proxy_data[self.ADDRESS]
        port = proxy_data[self.PORT]
        proxies = {self.HTTP.split(':')[0]: f"{self.HTTP}{user_name}:{password}@{address}:{port}",
                   self.HTTPS.split(':')[0]: f"{self.HTTP}{user_name}:{password}@{address}:{port}"}
        return proxies

    def parse_proxy(self, proxy):
        parsed_proxy = urlparse(proxy[self.HTTP.split(':')[0]])
        proxy_dict = {
            "server": f"{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port}",
            "username": parsed_proxy.username,
            "password": parsed_proxy.password
        }
        return proxy_dict
    
    def add_proxy_block_count(self, proxies):
        proxy = proxies[self.HTTP.split(':')[0]]
        block_count = self.block_proxy_dict.get(proxy, 0)
        self.block_proxy_dict[proxy] = block_count + 1
    
    def check_if_proxy_is_blocked(self, proxies):
        proxy = proxies[self.HTTP.split(':')[0]]
        block_count = self.block_proxy_dict.get(proxy, 0)
        return block_count >= self.BLOCK_COUNT

    def get_proxy_list(self):
        count = 0
        proxy_list = None
        full_proxy_list = []
        while count < self.NUM_RETRY:
            try:
                proxy_list = requests.get(self.PROXY_LIST_URL, headers=self.PROXY_HEADER, timeout=30).json()
                if self.RESULTS in proxy_list:
                    next_url = proxy_list[self.NEXT]
                    proxy_list = proxy_list[self.RESULTS]
                    full_proxy_list += proxy_list
                    inner_count = 0
                    while next_url is not None and inner_count < self.NUM_RETRY:
                        try:
                            proxy_list = requests.get(next_url, headers=self.PROXY_HEADER, timeout=30).json()
                            if self.RESULTS in proxy_list:
                                next_url = proxy_list[self.NEXT]
                                proxy_list = proxy_list[self.RESULTS]
                                full_proxy_list += proxy_list
                            else:
                                next_url = None
                        except Exception as e:
                            self.logger.error("Unable to get proxy list: {}".format(e))
                            time.sleep(1)
                            inner_count += 1
                    count = self.NUM_RETRY
                    self.logger.debug("Proxy list updated")
            except Exception as e:
                self.logger.error("Unable to get proxy list: {}".format(e))
                time.sleep(1)
                count += 1
        if len(full_proxy_list) > 0:
            full_list = [self._parse_proxy_data(proxy_data) for proxy_data in full_proxy_list if proxy_data[self.VALID]]
            self.full_list = [proxies for proxies in full_list if not self.check_if_proxy_is_blocked(proxies)]
            self.last_update = time.time()
            self.reset_active_list()
            self.logger.debug("blocked_proxy_list: {}".format(json.dumps(self.block_proxy_dict)))
            self.logger.debug("Number of proxy: {}".format(len(self.full_list)))
            self.logger.debug("Next update time: {}".format(self.next_refresh_time))

    def _parse_plan_id(self, plan_data):
        plan_id = plan_data[self.ID]
        return plan_id

    def _parse_next_auto_refresh(self, plan_data):
        next_refresh = plan_data.get(self.AUTOMATIC_REFRESH_NEXT_AT)
        if next_refresh is not None:
            next_refresh = datetime.datetime.fromisoformat(next_refresh).timestamp()
        return next_refresh

    def get_next_rotate_time(self):
        count = 0
        plan_list = None
        while count < self.NUM_RETRY:
            try:
                plan_list = requests.get(self.PLAN_URL, headers=self.PROXY_HEADER, timeout=30).json()
                if self.RESULTS in plan_list:
                    count = self.NUM_RETRY
                    self.logger.debug("Plan data loaded")
            except Exception as e:
                self.logger.error("Unable to get plan data. {}".format(e))
                time.sleep(1)
                count += 1
        if plan_list is not None and self.RESULTS in plan_list:
            plan_list = plan_list[self.RESULTS]
            plan_id_list = [self._parse_plan_id(plan_data) for plan_data in plan_list]
            plan_url_list = [self.PLAN_URL + str(plan_id) + '/' for plan_id in plan_id_list]
            next_refresh_time = 0
            for plan_url in plan_url_list:
                count = 0
                plan_data = None
                while count < self.NUM_RETRY:
                    try:
                        plan_data = requests.get(plan_url, headers=self.PROXY_HEADER, timeout=30).json()
                        count = self.NUM_RETRY
                        self.logger.debug("Next update time loaded")
                    except Exception as e:
                        self.logger.error("Unable to get next update time. {}".format(e))
                        time.sleep(1)
                        count += 1
                if plan_data is not None:
                    next_refresh = self._parse_next_auto_refresh(plan_data)
                    if next_refresh is not None and next_refresh > next_refresh_time and next_refresh > self.last_update:
                        next_refresh_time = next_refresh
            if next_refresh_time == 0:
                next_refresh_time = None
        else:
            next_refresh_time = None
        self.next_refresh_time = next_refresh_time

    def reset_active_list(self):
        self.active_list = self.full_list.copy()

    def check_if_refresh_list(self):
        if len(self.full_list) == 0:
            self.get_proxy_list()
        current_time = time.time()
        if self.last_update is None or current_time - self.last_update > self.REFRESH_PERIOD_MINUTE * 60:
            self.logger.debug("Refresh proxy list because last update is older than {} minutes".format(self.REFRESH_PERIOD_MINUTE))
            self.get_proxy_list()
        if self.next_refresh_time is not None:
            if current_time > self.next_refresh_time:
                self.logger.debug("Refresh proxy because next refresh time is expired")
                time.sleep(60)
                self.get_proxy_list()
        if self.next_refresh_time is None or self.last_update > self.next_refresh_time:
            self.get_next_rotate_time()

    def generate_proxy(self, rand=True):
        self.check_if_refresh_list()
        blocked = True
        while blocked:
            if len(self.active_list) == 0:
                self.reset_active_list()
            if rand:
                proxy = random.choice(self.active_list)
            else:
                proxy = self.active_list[0]
            blocked = self.check_if_proxy_is_blocked(proxy)
            self.active_list.remove(proxy)
        return proxy

