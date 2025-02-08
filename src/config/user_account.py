import json
from pathlib import Path

from selenium.webdriver.remote.webdriver import WebDriver
from src.config.local_logging import LocalLogging

class UserAccount():
    '''
    A simple data object meant to save and load cookies so that a driver can "act" as though it was an individual,
    allowing X seperate accounts to be snagging sneakers at a time
    '''
    base_directory = Path(__file__).resolve().parent.parent.parent

    def __init__(self, user_email: str, user_password: str):
        self.user_email = user_email
        self.user_password = user_password
        self.cookie_file_name = UserAccount.base_directory / "data_folder" / "cookies" / (self.user_email.split("@")[0] + ".json")
        self.logger = LocalLogging.get_local_logger(f"user_account_{self.user_email}")

    def to_json(self):
        return {
            "user_email": self.user_email,
            "user_password": self.user_password
        }

    @staticmethod
    def load_from_json(json_data):
        return UserAccount(json_data['user_email'], json_data["user_password"])

    def load_cookies(self, driver):
        '''
        Utility method that will apply cookies that were saved in previous session
        '''
        try:
            with open(self.cookie_file_name, "r") as file:
                cookies = json.load(file)
                for cookie in cookies:
                    no_null_cookies = {key : value for key, value in cookie.items() if value is not None}
                    if "expiry" in no_null_cookies:
                        cookie["expiry"] = int(no_null_cookies["expiry"])
                    try:
                        driver.add_cookie(no_null_cookies)
                    except Exception as e:
                        self.logger.error(e)

                driver.refresh()
        except Exception as e:
            self.logger.error(e)
            self.logger.info("Could not apply cookies as no cookies files found from previous run.")
            return

    def save_cookies(self, driver: WebDriver):
        '''
        Called automatically before closing so each time the user runs on a job board their previous cookies are saved
        :param board_name: the name of the board that the cookies are for
        :return:
        '''
        cookies = driver.get_cookies()
        cookies_file = self.cookie_file_name

        # Save cookies to a file
        with open(cookies_file, "w") as file:
            json.dump(cookies, file)

