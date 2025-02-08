# SneakerSnagger
Sneakers Buying app that allows a bot to purchase from https://www.nike.com when a shoe goes on sale

## Instillation and configuration
*This probably will need to be updated frequently, last updated 2/8/25*
- Make sure that you have python 3.11+ installed on your local PC
  - **Windows** 
    - Grab any version greater than 3.10 and install it for your instillation(probably 64 bit)
    - Run the installer and MAKE SURE YOU SELECT "add python.exe to PATH", "pip", "Add Python to environment variables", "Precompile standard library"
    - navigate to where this project is installed in file browser, hold shift and right click and select "Open powershell window here"
    - type 'pip install -r requirements.txt' *This will grab all the files that are required to run this application. These are python libraries*
  - **Mac/Unix**
    - use w/e package manager to install python3 `brew install python3`
  
## Steps to run
0. Follow the 
1. Enter account information you wish to use to try and snag them sneakers in the data_folder/accounts.json folder. If you are having trouble running google json format checker and make sure your format is valid Json
2. Enter what purchases you want to make, this will need to have AN ENTRY PER PURCHASE you wish to make. If you want to try and make 2 purchases of the same shoe with different accounts simply make two json objects and change the account email address.
3. First run the application and for each window follow instructions that will be written on the webpage. At some point you may be asked to decide to close and run again, or just continue running. **The option to close is trying to save the cookie information so you wont need to keep logging in every time you run this app. This should work but may not**
4. 