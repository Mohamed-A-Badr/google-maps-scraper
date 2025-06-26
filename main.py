import time
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    WebDriverException,
)
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
        except WebDriverException as e:
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
        except NoSuchElementException as e:
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
        except NoSuchElementException as e:
            print(f"Error finding search area button: {e}")
            return
        search_area_button.click()
        print("Search area button clicked.")

    def scrolling_search_results(self):
        try:
            feed = self.driver.find_element(By.XPATH, '//div[@role="feed"]')
        except NoSuchElementException:
            print("Error: Could not find results feed")
            return

        scroll_pause_time = 1
        scroll_attempts = 0
        max_scroll_attempts = 10
        last_height = self.driver.execute_script(
            "return arguments[0].scrollHeight", feed
        )
        while scroll_attempts < max_scroll_attempts:
            self.driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight", feed
            )
            time.sleep(scroll_pause_time)

            new_height = self.driver.execute_script(
                "return arguments[0].scrollHeight", feed
            )

            if new_height == last_height:
                scroll_attempts += 1
                if scroll_attempts >= 3:
                    break
            else:
                scroll_attempts = 0

            last_height = new_height

            current_results = len(
                feed.find_elements(By.XPATH, './/a[contains(@href, "/maps/place")]')
            )
            if current_results == 0:
                break

            print(f"Scrolling... Found {current_results} results so far")


if __name__ == "__main__":
    scraper = Scraper()
    search_query = "أشعة OR radiology OR سينية"
    lat = 30.9632309
    lng = 32.2477777

    scraper.loading_search_results(search_query, lat, lng)
    scraper.scrolling_search_results()

    scraper.driver.quit()
