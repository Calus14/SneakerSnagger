from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FireFoxService
from selenium.webdriver.remote.webdriver import BaseWebDriver
import undetected_chromedriver as uc
from src.config.local_logging import LocalLogging


class WebDriverFactory():
    '''
    Factory class that allows us to specify drivers that will be used for specific functions
    (Visual if need be, non-visual, etc.)
    '''

    logger = LocalLogging.get_local_logger("web_driver_factory")

    def chrome_browser_options(self) -> Options:
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        return options

    def firefox_browser_options(self) -> Options:
        options = webdriver.FirefoxOptions()
        return options

    def get_chrome_web_driver(self) -> BaseWebDriver:
        '''
        :return: web-driver for chrome
        '''
        try:
            # Use webdriver_manager to handle ChromeDriver
            driver = uc.Chrome(use_subprocess=False)
            self.logger.debug("Chrome Browser initialized successfully.")
            return driver

        except Exception as e:
            self.logger.error(f"Failed to initialize chrome browser: {e}")
            raise RuntimeError(f"Failed to initialize chrome browser: {e}")

    def get_fire_fox_web_browser(self):
        '''
        :return: web-driver for fire fox
        '''
        try:
            # Use webdriver_manager to handle ChromeDriver
            driver = webdriver.Firefox(service=FireFoxService(GeckoDriverManager().install()),
                                       options=self.firefox_browser_options())
            self.logger.debug("FireFox Browser initialized successfully.")
            return driver
        except Exception as e:
            self.logger.error(f"Failed to initialize firefox browser: {str(e)}")
            raise RuntimeError(f"Failed to initialize firefox browser: {str(e)}")
