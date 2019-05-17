import websockets
import asyncio
import json
import threading
from netdata_setting import NOTIFIER_PATH, WebsocketSetting
from netdata_utilities import set_logger, async_retry, no_auth, message_checker, print_websocket_response
import sys
sys.path.append(NOTIFIER_PATH)
from notifiers import send_message


class Websocket(WebsocketSetting):

    def __init__(self):
        self.logger = None
        self.set_logger()
        self.loop = None
        self.auth_ws = None
        self.response = {}
        self.thread = None
        self.lock = threading.Lock()

    def set_logger(self):
        self.logger = set_logger(self.WEBSOCKET_LOGGER_PATH, self.WEBSOCKET_LOGGER_FILE,
                                 self.WEBSOCKET_LOGGER_LEVEL, __name__)

    async def _one_off_api_call(self, url, message, auth=None):
        if auth is None:
            auth = no_auth
        try:
            async with websockets.connect(url) as websocket:
                websocket = await auth(websocket)
                await websocket.send(message)
                response = await websocket.recv()
                response = {'ok': True, 'message': response, 'input': message}
        except Exception as e:
            response = {'ok': False, 'error': e, 'input': message}
        return response

    async def one_off_api_call(self, url, message, auth=None, html_checker=None, time_sleep=0, verbose=False):
        response = await async_retry(self._one_off_api_call, url, message, auth, checker=message_checker,
                                     html_checker=html_checker, num_retry=self.WEBSOCKET_NUM_RETRY,
                                     sleep_time=self.WEBSOCKET_RETRY_SLEEP, logger=self.logger)
        if verbose:
            self.logger.debug('{} loaded'.format(response['input']))
        if not response['ok']:
            self.logger.error('Fail to load {}. {}'.format(response['input'], response['error']))
        await asyncio.sleep(time_sleep)
        return response

    async def long_live_api_call(self, url, message, action, auth=None, *args, **kwargs):
        if auth is None:
            auth = no_auth
        try:
            async with websockets.connect(url) as websocket:
                websocket = await auth(websocket)
                await websocket.send(message)
                while websocket.open:
                    response = await websocket.recv()
                    action(response, *args, **kwargs)
        except Exception as e:
            self.logger.error('Error in connecting to websocket {}. {}'.format(message, e))

    def loop_api_call(self, func, url, message, action, auth=None, *args, **kwargs):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(func(url, message, action, auth, *args, **kwargs))

    def thread_api_call(self, thread_name, func, url, message, action, auth=None, *args, **kwargs):
        self.thread = threading.Thread(target=lambda: self.loop_api_call(func, url, message, action, auth, *args,
                                                                         **kwargs), daemon=True, name=thread_name)

    def restart_if_disconnect(self):
        if self.thread is not None and not self.thread.is_alive():
            self.logger.error('Websocket {} disconnected'.format(self.thread.name))
            self.thread.start()

def test_one_off_api_call(url, message):
    ws = Websocket()
    ws.loop = asyncio.get_event_loop()
    response = ws.loop.run_until_complete(ws.one_off_api_call(url, message))
    return response

def test_long_live_api_call(url, message, action):
    ws = Websocket()
    ws.loop_api_call(ws.long_live_api_call, url, message, action)


def test_multiple_long_live_api_call(thread_name_list, url_list, message_list, action):
    no_connection = len(message_list)
    wss = [Websocket() for _ in range(no_connection)]
    [ws.thread_api_call(thread_name, ws.long_live_api_call, url, json.dumps(msg), action)
     for thread_name, url, ws, msg in zip(thread_name_list, url_list, wss, message_list)]
    while True:
        [ws.restart_if_disconnect() for ws in wss]

if __name__ == '__main__':
    run_test_one_off_api_call = False
    run_test_long_live_api_call = True
    run_test_multiple_long_live_api_call = False
    if run_test_one_off_api_call:
        url = 'wss://test.deribit.com/ws/api/v2'
        message = {"jsonrpc": "2.0", "id": 8772, "method": "public/get_order_book", "params": {
            "instrument_name": "BTC-PERPETUAL", "depth": 5}}
        print(test_one_off_api_call(url, json.dumps(message)))
    elif run_test_long_live_api_call:
        url = 'wss://test.deribit.com/ws/api/v2'
        message = {"jsonrpc": "2.0", "id": 7264, "method": "public/subscribe", "params": {
            "channels": ["quote.BTC-PERPETUAL"]}}
        action = print_websocket_response
        test_long_live_api_call(url, json.dumps(message), action)
    elif run_test_multiple_long_live_api_call:
        thread_name_list = ['deribit', 'bitmex']
        url_list = ['wss://test.deribit.com/ws/api/v2', 'wss://www.bitmex.com/realtime']
        message_list = [{"jsonrpc": "2.0", "id": 7260, "method": "public/subscribe", "params": {
            "channels": ["quote.BTC-PERPETUAL"]}}, {'op': 'subscribe', 'args': ['quote:XBTUSD']}]
        action = print_websocket_response
        test_multiple_long_live_api_call(thread_name_list, url_list, message_list, action)