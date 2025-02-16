import threading
import traceback

from pathlib import Path
from typing import Tuple

from src.config.local_logging import LocalLogging
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
        shoes_to_snag_file = data_folder / "shoes_to_snag.json"

        return (shoes_to_snag_file)

    except FileNotFoundError as fnf:
        main_logger.error(f"File not found: {fnf}")
        main_logger.error("Ensure all required files are present in the data folder.")
    except RuntimeError as re:
        main_logger.error(f"Runtime error: {re}")
        main_logger.debug(traceback.format_exc())
    except Exception as e:
        main_logger.exception(f"An unexpected error occurred: {e}")

def main():
    shoes_file_path = load_config()
    account_snagging_threads = []
    webFactor = WebDriverFactory()

    try:
        web_driver = webFactor.get_chrome_web_driver()
        purchaser = NikePurchaser(web_driver, shoes_file_path)
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
