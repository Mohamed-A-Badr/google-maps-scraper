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

    def loading_search_results(self, search_query, lat, lng):
        """
        Loads search results for a given query and coordinates in Google Maps.
        Args:
            search_query (str): search keywords for searching
            lat (float): latitude for the search location
            lng (float): longitude for the search location
        """
        encoded_query = quote_plus(search_query)
        url = f"https://www.google.com/maps/search/{encoded_query}/@{lat},{lng},16z"

        self.open_url(url)

        try:
            zoom_out_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "widget-zoom-out"))
            )
        except Exception as e:
            print(f"Error finding zoom out button: {e}")
            return
        zoom_out_button.click()
        print("Zoom out button clicked.")

        try:
            search_area_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@jsaction='search.refresh']")
                )
            )
        except Exception as e:
            print(f"Error finding search area button: {e}")
            return
        search_area_button.click()
        print("Search area button clicked.")


run_scraper = Scraper()
run_scraper.loading_search_results(
    "مركز أشعة OR أشعة OR سينية OR radiology", 29.9827167, 31.23571
)
