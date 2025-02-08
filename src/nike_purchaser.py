import traceback

from bs4 import BeautifulSoup

from selenium.webdriver.remote.webdriver import BaseWebDriver
from selenium.webdriver.common.by import By
import time

from selenium.webdriver.support import wait, expected_conditions as EC

from src.config.local_logging import LocalLogging
from src.config.user_account import UserAccount


class NikePurchaser():
    '''
    This class represents a user account, and the driver that maintains the fake user and their tabs, specifically
    a tab for each shoe to snag configured per account
    '''

    base_url = "https://www.nike.com"
    payment_account_url = "https://www.nike.com/member/settings/payment-methods"
    display_element_id = "nike-helper-custom-message-box"
    desktop_nav_list_xpath = "//ul[@class='desktop-list']"


    # JavaScript to track clicks with Shift key pressed
    __messanger_script = """
        if (!document.getElementById('{elem_id}')) {{
            // Create status container
            const statusDiv = document.createElement('div');
            statusDiv.id = '{elem_id}'
            statusDiv.style.position = 'fixed';
            statusDiv.style.top = '50%';
            statusDiv.style.left = '50%';
            statusDiv.style.backgroundColor = '{color}';
            statusDiv.style.transform = 'translate(-50%, -50%)';
            statusDiv.style.padding = '10px';
            statusDiv.style.zIndex = '9999';
            statusDiv.innerHTML = '{msg}';
            document.body.appendChild(statusDiv);
        }}
   """

    # Inject JavaScript to monitor button clicks
    monitoring_script = """
    // Global array to store key presses
    window.keyEvents = [];
    
    // Function to log key presses
    function logKeyPress(event) {
        window.keyEvents.push({
            key: event.key,
            code: event.code,
            shift: event.shiftKey,
            ctrl: event.ctrlKey,
            alt: event.altKey,
            meta: event.metaKey
        });
    }
    
    // Attach event listener to the document
    document.addEventListener('keydown', logKeyPress, true); // Use capturing phase
    """

    def __init__(self, driver: BaseWebDriver, user_account: UserAccount):
        self.driver = driver
        self.user_account = user_account
        self.driver.get(NikePurchaser.base_url)
        self.logger = LocalLogging.get_local_logger("Nike_Purchaser")
        self.original_tab = self.driver.current_window_handle

        self.user_account.load_cookies(self.driver)


    def setup_for_monitoring(self):
        '''
        Method that will get the driver into a state which has the user logged in, with a default payment method,
        and shipping address.

        If the user account is not able to be created then display a big yellow box telling the user to fill it out
        :except: if an un-handleable excpetion occurs that wont let this purchase to be able to achieve monitoring
        '''
        starting_tabs = self.driver.window_handles

        # Make sure were logged in
        if self._requires_login():
            self._show_user_message("You need to Open a new tab, and log in. Then return to this page for more instructions!" )
            # Wait for the new window or tab
            while len(self.driver.window_handles) == len(starting_tabs):
                time.sleep(.5)

            self.user_tab = self.driver.window_handles[-1]
            self._wait_for_user_input()


    def _wait_for_user_input(self):
        '''
        Utility method that will allow us to watch for the user to return to the inital tab and press input.
        The initial use of the input will be to check for
            : Login and save cookies for future login
            : Once logged in and payment has been set runs the actual purchasing of items
        :return:
        '''
        bad_attempts = 0
        max_bad_attempts = 5
        updated_display_msg = False
        while True or bad_attempts < max_bad_attempts:
            current_tab = self.driver.current_window_handle
            #Make sure we only check when they return to the initial window
            if current_tab == self.original_tab:

                # If it is the first time display to the user
                if not updated_display_msg:
                    self._show_user_message("If you are having trouble logging in, open a new tab and try again.\n Once you are logged in leave only this tab and the other tab open. \nA:Press Backspace to save your login \nB: Enter to run monitoring to snag sneakers")
                    updated_display_msg = True

                try:
                    key_events = self.driver.execute_script("return window.keyEvents;")
                    if key_events == None:
                        try:
                            self.driver.execute_script(NikePurchaser.monitoring_script)
                        except Exception as scriptException:
                            self.logger.error(f"Unable to execute script which tracks input! Defaulting to just running snagging! - {scriptException}")
                            bad_attempts += 1
                    elif len(key_events) > 0:
                        key_code_pressed = key_events[0]['code']

                        if key_code_pressed == 'Backspace': # Save cookies
                            self.driver.switch_to.window(self.driver.window_handles[-1])
                            self.user_account.save_cookies(self.driver)
                        elif key_code_pressed == 'Enter': # run monitoring
                            print("TODO build out the monitoring section")

                        # clear the key events.
                        self.driver.execute_script("window.keyEvents = [];")
                except Exception as scriptException:
                    self.logger.error(f"Unable to execute script which tracks input! Defaulting to just running snagging! - {scriptException}")


            time.sleep(1)  # Check every 500ms


    def _requires_login(self):
        '''
        Checks that if there is a login element and if soo notifies the user to login
        '''
        self.driver.switch_to.window(self.original_tab)
        try:
            desktop_nav = self.driver.find_element(By.XPATH, self.desktop_nav_list_xpath)
            list_elements = desktop_nav.find_elements(By.XPATH, "./li")
            # 3 elements means they have logged in
            if len(list_elements) == 3:
                self.logger.info("Found that the user is logged in!")
                return False
            elif len(list_elements) == 4:
                self.logger.info("Found that the user is NOT logged in!")
                return True
            else:
                self.logger.error(f"Unable to determine if the user is logged in or not! Found {len(list_elements)} elements in the nav elememnt")
        except Exception as e:
            self.logger.error("Script is broken, unable to find login element, maybe we dont need to be checking at this point?")
            return True

        return True

    def _require_default_payment_method(self):
        '''
        goes to the user setting after they have been logged in, and makes sure that there is BS4 Tag that reads
        "Default Payment Method", if not displays a message to the user that one must be set
        :return: the the user account has had its default payment method set on the session
        '''
        # Janky but not checking login
        self.driver().get(NikePurchaser.payment_account_url)
        page_html = self.driver().page_source
        soup = BeautifulSoup(page_html, 'html.parser')

        # Remove all the heavy strings that likely load with javascript
        try:
            default_payment_method_tag = soup.find(lambda tag: tag and tag.get_text().casefold() == "Default Payment Method".casefold())
            if default_payment_method_tag:
                return True
        except Exception as e:
            self.logger(e)
            self.logger.error(traceback.format_exc())
            return False

    def _show_user_message(self, user_msg: str, color="yellow"):
        '''
        Updates a div that will be shown to the user so they know what they need to do

        :param user_msg:
        :return:
        '''
        try:
            display_element = self.driver.find_element(By.ID, NikePurchaser.display_element_id)
        except Exception:
            display_element = None

        try:
            if not display_element: #If the page doesnt have the element yet, add it
                self.driver.execute_script(NikePurchaser.__messanger_script.format(elem_id=NikePurchaser.display_element_id, color=color, msg=user_msg))
            else: # The page has the element, so grab it and update its color and message
                self.driver.execute_script(f"statusDiv.innerHTML = '{user_msg}';")
                self.driver.execute_script(f"statusDiv.style.backgroundColor = '{user_msg}';")
        except Exception as display_exception:
            self.logger.error(display_exception)
            self.logger.error(traceback.format_exc())
            return None

    def _open_new_tab(self):
        try:
            self.driver.switch_to.new_window('tab')
            return self.driver.current_window_handle
        except Exception as e:
            self.logger.error("Unable to open new tab for driver..." + e)
            return None

        return None