import json
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

    base_url = "https://www.nike.com/"
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
        self.logger = LocalLogging.get_local_logger("Nike_Purchaser")
        self.message_tab = self.driver.current_window_handle
        self.execution_tab = None # this is the tab that the user will login too and we will use to snag
        self.failed_login = False
        self.driver.get(self.base_url)
        self.last_message = ""

        #self.user_account.load_cookies(self.driver)
        self.states = ["INIT", "LOGGING_IN", "PAYMENT_REQUIRED", "READY_TO_SNAG"]
        self.state = self.states[0]


    def setup_for_monitoring(self):
        '''
        Method that will get the driver into a state which has the user logged in, with a default payment method,
        and shipping address.
        '''

        # Wait for the user to open a tab, do things, and come back to the message tab to interact
        self._wait_for_user_input()



    def _wait_for_user_input(self):
        '''
        Utility method that will allow us to watch for the user to return to the inital tab and press input.
        The initial use of the input will be to check for
            : Login and save cookies for future login
            : Once logged in and payment has been set runs the actual purchasing of items
        :return:
        '''
        self.state = "LOGGING_IN"
        bad_attempts = 0
        max_bad_attempts = 5

        while bad_attempts < max_bad_attempts:
            current_tab = self.driver.current_window_handle

            # Handle the user returning to the original message tab
            if current_tab == self.message_tab:
                self._display_state_message()
                try:
                    # Allow the user to tell the program things via entering keys on the message tab
                    key_events = self.driver.execute_script("return window.keyEvents;")
                    if key_events == None:
                        try:
                            self.driver.execute_script(NikePurchaser.monitoring_script)
                        except Exception as scriptException:
                            self.logger.error(f"Unable to execute script which tracks input! Defaulting to just running snagging! - {scriptException}")
                            bad_attempts += 1
                    elif len(key_events) > 0:
                        key_code_pressed = key_events[0]['code']
                        self._handle_user_interaction(key_code_pressed)
                        # clear the key events.
                        self.driver.execute_script("window.keyEvents = [];")
                except Exception as scriptException:
                    self.logger.error(f"Unable to execute script which tracks input! Defaulting to just running snagging! - {scriptException}")

            time.sleep(1)  # Check every 500ms

    def _display_state_message(self, error_msg=None):
        if self.state == "LOGGING_IN":
            if self.failed_login:
                self._show_user_message("You indicated that you have logged in on another tab, however we couldnt see any tab where you were logged in! Make sure you see your account name like \"Hi Caleb\" in the top right on one tab other than this one and try again!", "red")
            else:
                if len(self.driver.window_handles) <= 1:
                    self._show_user_message("You need to Open a new tab, and log in. Then return to this page for more instructions!" )
                else:
                    self._show_user_message("If you are having trouble logging in, open a new tab and try again. Once you are logged in on a tab, leave it open and return to this tab. A:Press Enter to tell the program you have finished logging in.", "blue")
        if self.state == "PAYMENT_REQUIRED":
            self._show_user_message("I checked the logged in tab and i found that there is not a default payment set, please set it and come back", "red")
        if self.state == "READY_TO_SNAG":
            self._show_user_message("Looks like you are already to go. press enter to have the app switch to snagging mode.")
        if self.state == "ERROR" and error_msg:
            self._show_user_message(f"Error Occured, Probably need to restart the app! {error_msg}", "red")

    def _handle_user_interaction(self, key_code: str):
        # User indicated that they are done with the current step
        if 'Enter' in key_code: # run monitoring
            if self.state == "LOGGING_IN":
                # check to see if we need to login anymore
                self._requires_login()
                if self.failed_login:
                    return

                # IF the user logged in, their account can either be setup with payment or still need to do that
                self.state = "PAYMENT_REQUIRED" if self._require_default_payment_method() else "READY_TO_SNAG"
            elif self.state == "PAYMENT_REQUIRED":
                self.state = "PAYMENT_REQUIRED" if self._require_default_payment_method() else "READY_TO_SNAG"
            elif self.state == "READY_TO_SNAG":
                # TODO GO PERFORM THE ACTUAL SNAGGING MONITORING
                pass


    def _requires_login(self):
        '''
        Cycles through all tabs but our "message Tab" and checks if they are on the nike domain, if so checks if any of them
        are logged in. When one is finally logged in, it will attempt to store that tab as the "execution tab"
        '''

        # cycle through all the tabs only considering ones that
        for tab in self.driver.window_handles:
            try:
                self.driver.switch_to.window(tab)
                if "nike.com" in self.driver.current_url: #only consider tabs that the user went too.
                    desktop_nav = self.driver.find_element(By.XPATH, self.desktop_nav_list_xpath)
                    list_elements = desktop_nav.find_elements(By.XPATH, "./li")
                # 3 elements means they have logged in
                if len(list_elements) == 3:
                    self.logger.info("Found that the user is logged in!")
                    self.execution_tab = tab
                    self.failed_login = False
                    # Break early, we dont need to consider the other tabs
                    break
                elif len(list_elements) == 4:
                    self.logger.info("Found that the user is NOT logged in!")
                    self.failed_login = True
                else:
                    self.logger.error(f"Unable to determine if the user is logged in or not! Found {len(list_elements)} elements in the nav elememnt")
                    self.failed_login = True
            except Exception as e:
                self.logger.error("Script is broken, unable to find login element, maybe we dont need to be checking at this point?")
                self.failed_login = True


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

    def _show_user_message(self, user_msg: str, color="green"):
        '''
        Updates a div that will be shown to the user so they know what they need to do

        :param user_msg:
        :return:
        '''


        try:
            display_element = self.driver.find_element(By.ID, NikePurchaser.display_element_id)
            # Avoid trying to display the same message over and over again
            if display_element.text == user_msg:
                return
        except Exception:
            display_element = None

        try:
            if not display_element: #If the page doesnt have the element yet, add it
                escaped_msg = json.dumps(user_msg)
                self.driver.execute_script(
                    NikePurchaser.__messanger_script.format(
                        elem_id=NikePurchaser.display_element_id,
                        color=color,
                        msg=escaped_msg
                    )
                )
                self.driver.execute_script(NikePurchaser.__messanger_script.format(elem_id=NikePurchaser.display_element_id, color=color, msg=user_msg))
                self.last_message = user_msg
            else: # The page has the element, so grab it and update its color and message
                escaped_msg = json.dumps(user_msg)
                self.driver.execute_script(f"document.getElementById('{NikePurchaser.display_element_id}').innerHTML = {escaped_msg};")
                self.driver.execute_script(f"document.getElementById('{NikePurchaser.display_element_id}').style.backgroundColor = '{color}';")
                self.last_message = user_msg
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