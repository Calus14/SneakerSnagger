import os.path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth
from selenium.webdriver.firefox.service import Service as FireFoxService
from selenium.webdriver.remote.webdriver import BaseWebDriver
import undetected_chromedriver as uc

from local_config import LocalConfig
from src.config.local_logging import LocalLogging

class WebDriverFactory():
    '''
    Factory class that allows us to specify drivers that will be used for specific functions
    (Visual if need be, non-visual, etc.)
    '''

    logger = LocalLogging.get_local_logger("web_driver_factory")

    def chrome_browser_options(self) -> Options:
        options = uc.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("--disable-extensions")
        options.add_argument('--disable-popup-blocking')
        self._apply_profile(options)
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
            driver = uc.Chrome(use_subprocess=False, options=self.chrome_browser_options())
            self.logger.debug("Chrome Browser initialized successfully.")
            self._apply_stealth(driver)
            self._apply_interceptors(driver)

            return driver

        except Exception as e:
            self.logger.error(f"Failed to initialize chrome browser: {e}")
            raise RuntimeError(f"Failed to initialize chrome browser: {e}")

    def _apply_stealth(self, driver):
        '''
        utility method to apply selenium stealth on a selinum driver
        '''
        if LocalConfig.USE_STEALTH:
            stealth(driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",

                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                )

    def _apply_interceptors(self, driver):
        '''
        Utiltity method that will apply interceptors on the driver that are triggering Kasada to catch the bot
        '''

        if LocalConfig.BLOCK_NEW_RELIC:
            driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": ["https://bam.nr-data.net/*"]})


    def _apply_profile(self, options):
        '''
        Utility method that will set the profile given in the Local Configs
        '''
        try:
            if LocalConfig.CHROME_PROFILE:
                profile_path = LocalConfig.CHROME_USER_DATA_PATH
                if not os.path.exists(profile_path):
                    self.logger.error(f"Cannot find chrome profile at {LocalConfig.CHROME_USER_DATA_PATH} in the profile directory {LocalConfig.CHROME_PROFILE}")
                options.user_data_dir = profile_path
                options.add_argument("--profile-directory="+LocalConfig.CHROME_PROFILE)
            else:
                self.logger.info("No given chrome profile, running without a chrome profile!")
        except Exception as e:
            self.logger.error("Error while trying to see if there was a chrome profile and set it on the options!")
            self.logger.error(e)