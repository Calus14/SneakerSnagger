import json
import os
import threading
import traceback

from pathlib import Path
from typing import Tuple

from src.config.local_logging import LocalLogging
from src.config.user_account import UserAccount
from src.nike_purchaser import NikePurchaser
from src.utils.web_driver_factory import WebDriverFactory

main_logger = LocalLogging.get_local_logger("main_script.py")

def load_config() -> Tuple:
    '''
    returns a tuple of info needed for running this app
    '''

    try:
        # Define and validate the data folder
        data_folder = Path("data_folder")
        user_accounts_files = data_folder / "accounts.json"
        shoes_to_snag_file = data_folder / "shoes_to_snag.json"

        with open(user_accounts_files, "r", encoding="utf-8") as file:
            account_data = json.load(file)
            script_user_accounts = [UserAccount.load_from_json(data) for data in account_data]

        return (script_user_accounts)

    except FileNotFoundError as fnf:
        main_logger.error(f"File not found: {fnf}")
        main_logger.error("Ensure all required files are present in the data folder.")
    except RuntimeError as re:
        main_logger.error(f"Runtime error: {re}")
        main_logger.debug(traceback.format_exc())
    except Exception as e:
        main_logger.exception(f"An unexpected error occurred: {e}")

def main():
    user_accounts = load_config()
    account_snagging_threads = []
    webFactor = WebDriverFactory()

    try:
        for user_account in user_accounts:
            web_driver = webFactor.get_chrome_web_driver()
            purchaser = NikePurchaser(web_driver, user_account)
            thread = threading.Thread(target=purchaser.setup_for_monitoring)
            thread.start()
            account_snagging_threads.append(thread)

        for thread in account_snagging_threads:
            thread.join()
    except Exception as e:
        print(e)
        print(traceback.format_exc())

if __name__ == "__main__":
    main()
