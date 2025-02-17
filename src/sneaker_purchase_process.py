import datetime
import json
import re
import threading
import time
from enum import Enum
from pathlib import Path

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from local_config import LocalConfig
from src.config.local_logging import LocalLogging

class SneakerPurchaseProcess():
    '''
    Class which wraps the processing logic for how we will monitor a sneaker that is scheduled to go on sale.
    Basic idea is that initially it will spin up a seperate process (and possibly a seperate driver that has a logged in account)
    then it will check when the shoe releases. It will then "go to sleep" until X amount of minutes before the shoe goes on sale.
    Finally it will start refreshing adn checking with greater frequency, but still varied timing to avoid bot detection
    until the actual drop time, then it will attempt to re-load the page, and execute a purchase through the UI so that it seems to be
    completely legit.
    '''

    # Meant to be replicating what a real person would do, go to the site before the shoe goes on sale and start refreshing
    __MINUTES_BEFORE_SALE_WAKEUP = 2
    # How much to vary our refreshes by
    __SECONDS_VARIATION_ON_REFRESH = 2
    # What is the fastest that we limit ourself to on refresh
    __FASTEST_REFRESH_SECONDS = 1

    # Maximum amount of times
    __MAXIMUM_PURCHASE_RETRIES = 3

    # This regex expects "Available <M/D> at <H:MM AM/PM>"
    availability_pattern = r'Available\s+(\d{1,2}/\d{1,2})\s+at\s+(\d{1,2}:\d{2}\s+(?:AM|PM))'

    # XPATHS BELOW
    availability_xpath = "//div[@class='available-date-component']" # there is a list, but the first one is all we care about
    sizes_xpath = "//li[@data-qa='size-available']"
    purchase_button_xpath = "//button[contains(@class, 'buying-tools-cta-button')]"
    checkout_botton_xpath = "//button[@data-qa='checkout-link']"

    # The checkout process uses SOP and IFRAMEs
    cvv_iframe_xpath = "//iframe[@data-attr='credit-card-iframe-cvv']"
    cvv_input_xpath = "//form[@id='creditCardForm']//input[@id='cvNumber']"
    order_review_btn_xpath = "//button[@data-attr='continueToOrderReviewBtn']"
    general_btn_xpath = "//button[@type='button']"
    payment_error_xpath = "//h1[@id='modal-error']"
    payment_error_reason_xpath = "//p[contains(@class, 'error-code-msg')]"

    class PurchaseState(Enum):
        NOT_STARTED = 1
        PRE_RELEASE = 2
        NEAR_RELEASE = 3
        RELEASED = 4
        PURCHASED = 5
        ERROR = 6

    class TabTimingThread():
        '''
        Utility class that will let us know when a tab is ready to be refreshed
        '''
        def __init__(self, time_to_wait):
            self.time_to_wait = time_to_wait
            self.finished_at = None
            self.thread = threading.Thread(target=self._run)
            self.thread.start()

        def _run(self):
            time.sleep(self.time_to_wait)
            self.finished_at = time.time()

        def has_finished_waiting(self):
            return self.finished_at is not None

        def how_long_ago_did_it_finish(self):
            if not self.has_finished_waiting():
                return None
            return time.time() - self.finished_at

    def __init__(self, driver, sneaker_file: Path):
        self.driver = driver
        self.logger = LocalLogging.get_local_logger("sneaker_purchase_process")

        try:
            with open(sneaker_file, "r") as f:
                sneakers = json.load(f)
                self.sneaker_urls = [sneaker["shoe_url"] for sneaker in sneakers]
                self.sneaker_sizes = {sneaker["shoe_url"]: sneaker["size"] for sneaker in sneakers}
        except Exception as e:
            raise Exception("Cannot create Sneaker Purchaser Process, exception occured while extracting sneaker file")

        # Holds list of strings for the logs
        self.sneaker_events = {sneaker_url : [] for sneaker_url in self.sneaker_urls}
        # Holds a list of each sneaker and its purchase state
        self.sneaker_purchase_states = {sneaker_url : self.PurchaseState.NOT_STARTED for sneaker_url in self.sneaker_urls}
        # Holds a list of each sneaker and its tab to switch too
        self.sneaker_tabs = {sneaker_url : None for sneaker_url in self.sneaker_urls}
        # Holds a list of each sneaker and its timer for when to move to the next state
        self.sneaker_timing_threads = {sneaker_url : None for sneaker_url in self.sneaker_urls}
        # Allow for up to 3 attempts on each sneaker to be purchased
        self.sneaker_purchase_attempts = {sneaker_url : 0 for sneaker_url in self.sneaker_urls}

    def start_monitoring_sneakers(self):
        '''
        Method will attempt to launch a tab for each sneaker_url and an internal thread that times when to go check that
        that tab again to attempt to purchase the sneaker.
        '''
        self.logger.info("Starting process!")
        # Open a tab and go to it for each sneaker_URL
        for url, tab in self.sneaker_tabs.items():
            # If it is a new tab, then create a tab and go to it
            if tab == None:
                tab_handle = self._open_new_tab(url)
                self.sneaker_tabs[url] = tab_handle

                if tab_handle == None:
                    self.sneaker_events[url].append(f"Could not create tab for sneaker at : {url}")
                    self.sneaker_purchase_states[url] = self.PurchaseState.ERROR
                else:
                    self.sneaker_events[url].append(f"Created Tab for sneaker at : {url}")
                    self.sneaker_purchase_states[url] = self.PurchaseState.NOT_STARTED

        # Extract the start times for each URL. If there is not a release date on it mark it as error
        any_not_processed_or_error = self.__have_all_been_purchased()

        while any_not_processed_or_error:
            for url, state in self.sneaker_purchase_states.items():
                # we only set up timers if the url started
                if state == self.PurchaseState.ERROR or state == self.PurchaseState.PURCHASED:
                    continue
                else:
                    self._handle_sneaker_tab_state(url)

            # end if all of them error out or are purchased
            any_not_processed_or_error = self.__have_all_been_purchased()
            # wait half a second then check on timers again
            time.sleep(.5)

    def get_purchase_logs(self):
        return self.sneaker_events

    def _open_new_tab(self, url :str):
        try:
            self.driver.execute_script("window.open();")
            time.sleep(self.__FASTEST_REFRESH_SECONDS)
            tab_handle = self.driver.window_handles[-1]
            self.driver.switch_to.window(tab_handle)
            self.driver.get(url)
        except Exception as e:
            self.logger.error("Unable to open new tab for driver..." + e)
            return None

        return tab_handle

    def _handle_sneaker_tab_state(self, sneaker_url: str):
        '''
        Given a sneaker URL, attempt to grab its state, and do the following:
        - Check if the given timer is null or should be processed yet, if so exits
        - Refresh the page/go to the url
        - extract the value of when it will be released
        - Update the state of the thread based on how much time is left
        - Attempt to purchase if it is now available
        - create new timer if it has moved state
        :param sneaker_url: url of the sneaker we are looking at
        '''
        if (sneaker_url not in self.sneaker_timing_threads or
            sneaker_url not in self.sneaker_tabs or
            sneaker_url not in self.sneaker_purchase_states or
            sneaker_url not in self.sneaker_events):
            raise Exception("Unknown sneaker urls that was not present at instantiation of purchaser process!")

        if self.sneaker_purchase_states[sneaker_url] == self.PurchaseState.ERROR or self.sneaker_purchase_states[sneaker_url] == self.PurchaseState.PURCHASED:
            return

        # Handle the first time (when there is no timer)
        sneaker_timer = self.sneaker_timing_threads[sneaker_url]
        sneaker_state = self.sneaker_purchase_states[sneaker_url]

        if not sneaker_timer:
            if sneaker_state == self.PurchaseState.NOT_STARTED:
                try:
                    # extract when it says it will be available from the nike website
                    availability_dt = self._extract_tab_availablity_date(sneaker_url)

                    # from not started, we will wait until minutes until before sale
                    wakeup_dt = availability_dt - datetime.timedelta(minutes=self.__MINUTES_BEFORE_SALE_WAKEUP)
                    now = datetime.datetime.now()
                    wait_seconds = (wakeup_dt - now).total_seconds()

                    # Create a timer, so that we can wait and start trying to grab it
                    self.sneaker_timing_threads[sneaker_url] = self.TabTimingThread(wait_seconds)
                    self.sneaker_events[sneaker_url].append(f"Created timer that will wake up in {wait_seconds} for url: {sneaker_url} and moved state to Pre Release")
                    self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.PRE_RELEASE
                except Exception as e:
                    # If the url given is for a shoe that is already purchasa-able we will try to purchase it still
                    self.logger.info(f"Attempting to purchase shoe one time.")
                    purchase_worked = self._purchase_sneaker(sneaker_url)
                    if purchase_worked:
                        self.sneaker_events[sneaker_url].append(f"Sucessfully purchased sneaker!")
                        self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.PURCHASED
                    else:
                        self.sneaker_events[sneaker_url].append(f"Could not process the state for sneaker at : {sneaker_url}. Given error is {e}")
                        self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.ERROR

            else:
                self.logger(f"Somehowe had a sneaker url at : {sneaker_url} and it has no timer and is past a started state!")
        elif sneaker_timer.has_finished_waiting(): # only consider the tab if the timer has finished waiting
            self.sneaker_events[sneaker_url].append(f"Timer for sneaker at : {sneaker_url} is in {sneaker_state} state and has finished and it has been {sneaker_timer.how_long_ago_did_it_finish()} since it finished!")
            try:
                # extract when it says it will be available from the nike website
                availability_dt = self._extract_tab_availablity_date()

                # If it is pre-release then double check and set a timer to try reload right as it releases
                if sneaker_state == self.PurchaseState.PRE_RELEASE:
                    # wait until exactly the time it releases then try and buy.
                    now = datetime.datetime.now()
                    wait_seconds = (availability_dt - now).total_seconds()

                    # NOTE: Might want to have it load 1 seconds before because there might be like 1 second of lag on selenium
                    self.sneaker_timing_threads[sneaker_url] = self.TabTimingThread(wait_seconds)
                    self.sneaker_events[sneaker_url].append(f"Created timer that will wake up in {wait_seconds} for url: {sneaker_url} and moved state to NEAR_RELEASE")
                    self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.NEAR_RELEASE
                # If we found that there is still an availability_dt element then our timer is just super slightly off so create a really small timer to go again
                elif sneaker_state == self.PurchaseState.NEAR_RELEASE:
                    self.sneaker_timing_threads[sneaker_url] = self.TabTimingThread(self.__FASTEST_REFRESH_SECONDS)
                    self.sneaker_events[sneaker_url].append(f"Created timer that will wake up in {self.__FASTEST_REFRESH_SECONDS} for url: {sneaker_url} and moved state to NEAR_RELEASE")
                    self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.NEAR_RELEASE
            except Exception as e:
                self.logger.info(f"Sneaker with url - {sneaker_url} cannot find availability element! Might now be purchasable!")
                # If it was near release, and it cant find its element, it is now considered released
                if sneaker_state == self.PurchaseState.NEAR_RELEASE:
                    self.sneaker_events[sneaker_url].append(f"Sneaker cannot find availability element! Might now be purchasable!")
                    self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.RELEASED

                # anything that is released we can try to purchase
                if self.sneaker_purchase_states[sneaker_url] == self.PurchaseState.RELEASED:
                    self.logger.info(f"Attempting to purchase shoe!")
                    purchase_worked = self._purchase_sneaker(sneaker_url)
                    if purchase_worked:
                        self.sneaker_events[sneaker_url].append(f"Sucessfully purchased sneaker!")
                        self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.PURCHASED
                    else:
                        self.sneaker_events[sneaker_url].append(f"Failed to purchase sneaker!")
                        if self.sneaker_purchase_attempts[sneaker_url] < self.__MAXIMUM_PURCHASE_RETRIES:
                            self.sneaker_purchase_attempts[sneaker_url] += 1
                        else:
                            self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.ERROR

    def _extract_tab_availablity_date(self, sneaker_url):
        '''
        Attempts to get a sneakers availablity.
        :return: the datetime that this sneaker should be available.
        '''
        try:
            # Switch to the window for the sneaker itself
            self.driver.switch_to.window(self.sneaker_tabs[sneaker_url])
            availability_element = self.driver.find_element(By.XPATH, self.availability_xpath)
            availability_text = availability_element.text
        except Exception as e:
            raise Exception("Was not able to find availability element!")

        # make sure it has a string
        if not availability_text:
            raise Exception("First found availability element found to not have any availability text!")

        # make sure that it is valid
        match = re.search(self.availability_pattern, availability_text)
        if not match:
            raise Exception(f"First found availability element has text of {availability_text} which does not match our expected format of Available <M/D> at <H:MM AM/PM>")

        # I love AI generated code! This regex and all this stupid formatting BS im having it handle
        date_str = match.group(1)  # e.g., "2/22"
        time_str = match.group(2)  # e.g., "9:00 AM"

        # Assume current year; construct a datetime object.
        current_year = datetime.datetime.now().year
        target_time_str = f"{current_year}/{date_str} {time_str}"
        try:
            target_dt = datetime.datetime.strptime(target_time_str, "%Y/%m/%d %I:%M %p")
        except Exception as e:
            raise Exception("Error parsing target datetime:", e)

        # I added this in for if its december and they drop on january
        now = datetime.datetime.now()
        if target_dt < now:
            target_dt = target_dt.replace(year=current_year + 1)

        return target_dt

    def _purchase_sneaker(self, sneaker_url):
        '''
        Attempts to get a sneakers availablity.
        :return: the datetime that this sneaker should be available.
        '''
        try:
            # Switch to the window for the sneaker itself
            self.driver.switch_to.window(self.sneaker_tabs[sneaker_url])
            sizes_elements = self.driver.find_elements(By.XPATH, self.sizes_xpath)
            purchase_button_element = self.driver.find_element(By.XPATH, self.purchase_button_xpath)
        except Exception as e:
            raise Exception("Was not able to find sizes or purchase elements!")

        purchase_size = self.sneaker_sizes[sneaker_url]

        # Find the size for shoe
        for size_element in sizes_elements:
            try:
                button = size_element.find_element(By.TAG_NAME, "button")  # Find the button inside the <li>
                size_text = button.text
                # the size txt will be M # / F # so search for our specific size as a substring
                if purchase_size in size_text:
                    button.click()
                    purchase_button_element.click()
                    return self.__checkout(sneaker_url)
            except Exception as e:
                self.logger.error("Failed to find a size button on the size list element! Xpath schema broken!")
                continue

        return False

    def __checkout(self, sneaker_url):
        '''
        Attempts to flow through the checkout process
        :return: true if it was able to log out, false if an exception or error occured.
        '''
        # Try to click the checkout button that should have appeared
        try:
            checkout_element = self.driver.find_element(By.XPATH, self.checkout_botton_xpath)
            checkout_element.click()
        except Exception as e:
            self.sneaker_events[sneaker_url].append("Was not able to find and click the checkout element!")
            self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.ERROR
            return False

        if "nike.com/checkout" not in self.driver.current_url:
            self.sneaker_events[sneaker_url].append(f"Clicked checkout button but was not able to navigate to checkout page!")
            self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.ERROR
            return False

        #Input the cvv number
        try:
            # the payment ui changes based on what is selected so we need to grab the iframe and switch to that.
            cvv_iframe = self.driver.find_element(By.XPATH, self.cvv_iframe_xpath)
            self.driver.switch_to.frame(cvv_iframe)

            # Remove all the heavy strings that likely load with javascript
            cvv_element = self.driver.find_element(By.XPATH, self.cvv_input_xpath)
            cvv_element.send_keys(LocalConfig.CVV_NUMBER)
            time.sleep(.25)
            self.driver.switch_to.default_content()

            order_review_btn = self.driver.find_element(By.XPATH, self.order_review_btn_xpath)
            order_review_btn.click()
        except Exception as e:
            self.sneaker_events[sneaker_url].append("Could not find cvv element or order review button to checkout!")
            self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.ERROR
            return False

        # Finally click the submit payment button and make sure it went through!
        try:
            btn_elements = self.driver.find_elements(By.XPATH, self.general_btn_xpath)
            submit_btn_element = None
            for e in btn_elements:
                if e.text and "Submit Payment" in e.text:
                    submit_btn_element = e
                    break

            if submit_btn_element:
                submit_btn_element.click()
            else:
                # raise an exception here so we can do the logging and state change in the catch
                raise Exception()
        except Exception as e:
            self.sneaker_events[sneaker_url].append("Could not find and click the submit payment button!")
            self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.ERROR
            return False

        # Make sure there isnt a payment error modal
        try:
            payment_error_element = self.driver.find_element(By.XPATH, self.payment_error_xpath)
            if payment_error_element:
                payment_error_reason_element = self.driver.find_element(By.XPATH, self.payment_error_reason_xpath)
                error_text = payment_error_reason_element.text
                self.sneaker_events[sneaker_url].append(f"Payment was submitted but rejected by website for some error - {error_text}")
                self.sneaker_purchase_states[sneaker_url] = self.PurchaseState.ERROR
                return False
        except Exception as e:
            # An error occured while looking for an error, The enemy of my enemy is my friend
            pass
        
        return True

    def __have_all_been_purchased(self):
        any_not_processed_or_error = False
        for state in self.sneaker_purchase_states.values():
            if state != self.PurchaseState.ERROR and state != self.PurchaseState.PURCHASED:
                any_not_processed_or_error = True
        return any_not_processed_or_error