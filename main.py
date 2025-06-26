import re
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    WebDriverException,
    TimeoutException,
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

        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "geolocation": 2,
                "media_stream": 2,
            },
            "profile.default_content_settings.popups": 0,
        }
        options.add_experimental_option("prefs", prefs)

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
        except TimeoutException as e:
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
        except TimeoutException as e:
            print(f"Error finding search area button: {e}")
            return
        search_area_button.click()
        print("Search area button clicked.")

    def scrolling_search_results(self):
        """
        Scrolls through the search results feed to load more results.
        """
        try:
            feed = self.driver.find_element(By.XPATH, '//div[@role="feed"]')
        except NoSuchElementException:
            print("Error: Could not find results feed")
            return

        scroll_pause_time = 1
        last_height = self.driver.execute_script(
            "return arguments[0].scrollHeight", feed
        )
        scroll_attempts = 0
        max_scroll_attempts = 10

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
                print("No results found.")
                break
            print(f"Scrolling... Found {current_results} results so far")

    def scrape_results(self):
        """
        Scrape places data from the search results.

        returns:
            list: A list of dictionaries containing place data.
        """
        places_data = []

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        results_feed = soup.find_all("a", class_="hfpxzc")

        for index, i in enumerate(results_feed):
            title = ""
            address = ""
            phone = ""
            website = ""
            booking_link = ""
            category = ""
            rating = ""
            number_of_reviews = ""
            google_map_url = i.get("href")

            self.open_url(google_map_url)
            print(f"Processing place {index + 1}/{len(results_feed)}")

            card_data = BeautifulSoup(self.driver.page_source, "html.parser")

            # NOTE: title
            title = (
                card_data.find("h1", class_="DUwDvf lfPIob").get_text()
                if card_data.find("h1", class_="DUwDvf lfPIob")
                else "N/A"
            )

            # NOTE: address
            address = (
                card_data.find(
                    "div", class_="Io6YTe fontBodyMedium kR99db fdkmkc"
                ).get_text()
                if card_data.find("div", class_="Io6YTe fontBodyMedium kR99db fdkmkc")
                else "N/A"
            )
            # NOTE: phone number
            phone_button = card_data.find(
                "button", attrs={"data-item-id": re.compile(r"phone:tel:")}
            )
            phone = phone_button.attrs.get("aria-label") if phone_button else "N/A"

            # NOTE: category
            category = (
                card_data.find(
                    "button", {"jsaction": "pane.wfvdle17.category"}
                ).get_text()
                if card_data.find("button", {"jsaction": "pane.wfvdle17.category"})
                else "N/A"
            )

            # access place's card and get rating safely
            rating = "N/A"
            number_of_reviews = "N/A"
            try:
                card = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='main']"))
                )
                try:
                    rating_element = card.find_element(
                        By.XPATH, '//span[@class="ceNzKf"]'
                    )
                    rating = rating_element.get_attribute("aria-label").strip()
                except NoSuchElementException:
                    rating = "N/A"

            except TimeoutException as e:
                print(f"Error finding main card: {e}")
                rating = "N/A"
                number_of_reviews = "N/A"

            # NOTE: number of reviews
            number_of_reviews = (
                card_data.find_all("span", {"dir": "ltr"})[1].get_text()
                if len(card_data.find_all("span", {"dir": "ltr"})) > 1
                else "N/A"
            )
            if not re.match(r"^\(\d+\)$", number_of_reviews):
                number_of_reviews = "N/A"

            # NOTE: links
            links = card_data.find_all("a", class_="CsEnBe")
            for link in links:
                if link.attrs.get("data-item-id") == "authority":
                    website = link.attrs.get("href")
                if link.attrs.get("data-item-id") == "action:3":
                    booking_link = link.attrs.get("href")

            places_data.append(
                {
                    "title": title,
                    "address": address,
                    "phone": phone,
                    "category": category,
                    "rating": rating,
                    "number_of_reviews": number_of_reviews,
                    "website": website,
                    "booking_link": booking_link,
                    "google_map_url": google_map_url,
                }
            )

        return places_data


if __name__ == "__main__":
    start_time = time.perf_counter()
    scraper = Scraper()
    search_query = "أشعة OR radiology OR سينية"
    lat = 30.0923898
    lng = 31.3018828

    scraper.loading_search_results(search_query, lat, lng)
    scraper.scrolling_search_results()
    scraper.scrape_results()

    print("total time taken:", time.perf_counter() - start_time)
    scraper.driver.quit()
