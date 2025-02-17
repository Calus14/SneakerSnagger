
class LocalConfig():
    '''
    Utility class that is meant to be a place where we can hang global variables and settings so we can "turn things
    on and off" without having a lot of dead code/commented out code etc.
    '''

    # DO NOT CHANGE THESE
    CHROME_USER_DATA_PATH = "C:\\Users\\chbla\\AppData\\Local\\Google\\Chrome\\Projects"

    # FEEL FREE TO CHANGE THESE
    USE_STEALTH = False
    BLOCK_NEW_RELIC = True
    CHROME_PROFILE = "BobBurger"

    CVV_NUMBER = "900"

