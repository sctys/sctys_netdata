from requests_html import HTMLSession
import subprocess
import time
from password import nordvpn_token


class PrivateVPN:

    NUM_RETRY = 3
    TIMEOUT = 120
    VPN_GROUP = [
        "Africa_The_Middle_East_And_India",
        "Europe",
        "Standard_VPN_Servers",
        "Asia_Pacific",
        "Onion_Over_VPN",
        "The_Americas",
        # "Double_VPN",
        # "P2P"
    ]

    def __init__(self):
        self.__token = nordvpn_token
        self.group_index = 0
        self.num_scraped = None
        self.last_rotate = None

    def login_vpn(self):
        return self._retry_operation(["nordvpn", "login", "--token", self.__token])

    def rotate_group(self):
        self.group_index += 1
        if self.group_index >= len(self.VPN_GROUP):
            self.group_index = 0

    def connect_vpn(self):
        return self._retry_operation(
            ["nordvpn", "connect", self.VPN_GROUP[self.group_index]]
        )

    def disconnect_vpn(self):
        return self._retry_operation(["nordvpn", "disconnect"])

    def logout_vpn(self):
        return self._retry_operation(["nordvpn", "logout"])

    def check_to_rotate(self, num_to_rotate=None, time_to_rotate=None):
        if num_to_rotate is not None:
            if self.num_scraped is None:
                return True
            if self.num_scraped >= num_to_rotate:
                return True
        if time_to_rotate is not None:
            if self.last_rotate is None:
                return True
            if time.time() - self.last_rotate > time_to_rotate:
                return True
        return False

    def rotate_vpn(self, num_to_rotate=None, time_to_rotate=None):
        if self.check_to_rotate(num_to_rotate, time_to_rotate):
            self.disconnect_vpn()
            self.rotate_group()
            is_success = self.connect_vpn()
            if is_success:
                self.num_scraped = 0
                self.last_rotate = time.time()
            return is_success
        else:
            if self.num_scraped is not None:
                self.num_scraped += 1
            return True

    def _retry_operation(self, command_list):
        counter = 0
        while counter < self.NUM_RETRY:
            try:
                subprocess.run(
                    command_list,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=self.TIMEOUT,
                )
                return True
            except Exception as e:
                command_str = " ".join(command_list)
                print(
                    f"Unable to run the operation after trial {counter}. {command_str}. {e}"
                )
                counter += 1
        return False


if __name__ == "__main__":
    private_vpn = PrivateVPN()
    if private_vpn.login_vpn():
        try:
            for i in range(10):
                if private_vpn.rotate_vpn(time_to_rotate=60):
                    session = HTMLSession()
                    result = session.get("http://httpbin.org/ip")
                    print(result.text)
                    time.sleep(60)
        finally:
            private_vpn.disconnect_vpn()
            private_vpn.logout_vpn()
