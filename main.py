import time
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class Scraper:
    def __init__(self):
        """
        Initializes the Scraper class and sets up the Edge WebDriver.
        """
        self.driver = None
        self.setup_driver()

    def setup_driver(self):
        """
        Initializes the Edge WebDriver with specific options.
        Sets the driver to start maximized, disables extensions, and sets the log level.
        Wraps driver initialization in try/except to provide clearer error messages.
        """
        options = webdriver.EdgeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-extensions")

        service = Service(log_path="msedgedriver.log")

        try:
            self.driver = webdriver.Edge(options=options, service=service)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Edge WebDriver: {e}")

    def open_url(self, url):
        """
        Opens the specified URL in the Edge browser.
        Args:
            url (str): URL to open in the browser.
        """
        if self.driver is not None:
            self.driver.get(url)
        else:
            raise RuntimeError("Driver not initialized.")
