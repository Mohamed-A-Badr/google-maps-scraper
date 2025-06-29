import csv
import json
import logging
import os
import re
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from is_inside_country import find_near_location

log_file = "exception.log"
if not os.path.exists(log_file):
    with open(log_file, "w") as f:
        f.write("")

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

logger.handlers.clear()

file_handler = logging.FileHandler(filename=log_file, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)


class Scraper:
    def __init__(self):
        self.driver = None
        self.search_query = "أشعة OR سينية OR radiology"
        self.country = ["Egypt", "Saudi Arabia"]
        self.governorate_name = ""
        self.total_sectors = 0

        self.full_results = []
        self.searched = {}
        self.searched_governorate = {}

        self.current_lat = 0
        self.current_lng = 0

        # Flags to check if we just start the script from the beginning
        # after crash or close it or its an another coordinates in the same run
        self.first_coord_loop_lat = True
        self.first_coord_loop_lng = True

        self.setup_driver()
        self.load_searched_places(self.country[1])

    def setup_driver(self):
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
            self.log_crash(f"WebDriverException: {e}")
            raise RuntimeError(f"Failed to initialize Edge WebDriver: {e}")

    def open_url(self, url):
        if self.driver is not None:
            self.driver.get(url)
        else:
            self.log_crash("Driver not initialized.")
            raise RuntimeError("Driver not initialized.")

    def loading_search_results(self, lat, lng):
        encoded_query = quote_plus(self.search_query)
        url = f"https://www.google.com/maps/search/{encoded_query}/@{lat},{lng},17z"
        self.open_url(url)

        try:
            zoom_out_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "widget-zoom-out"))
            )
        except TimeoutException as e:
            print(f"Error finding zoom out button: {e}")
            self.log_crash(f"Error finding zoom out button at lat: {lat}, lng: {lng}")
            return
        zoom_out_button.click()
        time.sleep(0.5)

        try:
            search_area_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@jsaction='search.refresh']")
                )
            )
        except TimeoutException as e:
            print(f"Error finding search area button: {e}")
            self.log_crash(
                f"Error finding search area button at lat: {lat}, lng: {lng}"
            )
            return
        search_area_button.click()
        time.sleep(2)

    def scrolling_search_results(self):
        """
        Scroll through the search results feed to load more results.
        """
        try:
            feed = self.driver.find_element(By.XPATH, '//div[@role="feed"]')
        except NoSuchElementException:
            print("Error: Could not find results feed element")
            self.log_crash("Could not find results feed element.")
            return

        scroll_pause_time = 1.5
        last_height = self.driver.execute_script(
            "return arguments[0].scrollHeight", feed
        )
        scroll_attempts = 0
        max_scroll_attempts = 20

        while scroll_attempts < max_scroll_attempts:
            try:
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight", feed
                )
                time.sleep(scroll_pause_time)
                # Re-acquire the feed element to avoid stale reference
                feed = self.driver.find_element(By.XPATH, '//div[@role="feed"]')
                new_height = self.driver.execute_script(
                    "return arguments[0].scrollHeight", feed
                )
            except Exception as e:
                print(f"Error during scrolling: {e}")
                self.log_crash(f"Error during scrolling: {e}")
                break

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
            print(f"Scrolled to load {current_results} results.")

    def scrape_results(self):
        """
        Scrape the results from the place's page and store them in full_results.
        """
        places_data = []
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        results_feed = soup.find_all("a", class_="hfpxzc")

        for index, i in enumerate(results_feed):
            google_map_url = i.get("href")

            if (
                google_map_url in self.searched
                and self.searched[google_map_url] == "done"
            ):
                print(f"Place already searched ({index + 1}/{len(results_feed)})")
                continue
            print(f"Total number of searched places: {len(self.searched)}")
            self.searched[google_map_url] = "done"

            self.open_url(google_map_url)
            print(f"Processing place {index + 1}/{len(results_feed)}")

            card_data = BeautifulSoup(self.driver.page_source, "html.parser")

            title = card_data.find("h1", class_="DUwDvf lfPIob")
            address = card_data.find(
                "div", class_="Io6YTe fontBodyMedium kR99db fdkmkc"
            )
            phone_button = card_data.find(
                "button", attrs={"data-item-id": re.compile(r"phone:tel:")}
            )
            category_button = card_data.find(
                "button", {"jsaction": "pane.wfvdle17.category"}
            )
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
            except TimeoutException:
                pass

            reviews_elements = card_data.find_all("span", {"dir": "ltr"})
            if len(reviews_elements) > 1:
                for element in reviews_elements:
                    match = re.match(r"^\(\d+\)$", element.get_text())
                    if match:
                        number_of_reviews = element.get_text().strip("()")
                        break

            website = booking_link = "N/A"
            links = card_data.find_all("a", class_="CsEnBe")
            for link in links:
                if link.attrs.get("data-item-id") == "authority":
                    website = link.attrs.get("href")
                if link.attrs.get("data-item-id") == "action:3":
                    booking_link = link.attrs.get("href")

            if not any(
                place["google_map_url"] == google_map_url for place in self.full_results
            ):
                places_data.append(
                    {
                        "title": title.get_text() if title else "N/A",
                        "address": address.get_text() if address else "N/A",
                        "phone": (
                            phone_button.attrs.get("aria-label")
                            if phone_button
                            else "N/A"
                        ),
                        "governorate": self.governorate_name,
                        "category": (
                            category_button.get_text() if category_button else "N/A"
                        ),
                        "rating": rating,
                        "number_of_reviews": number_of_reviews,
                        "website": website,
                        "booking_link": booking_link,
                        "google_map_url": google_map_url,
                    }
                )

        self.full_results.extend(places_data)
        print(f"Scraped {len(places_data)} places.")

    def save_results(self):
        country_name = self.country[1].replace(" ", "_").lower()

        # Save Places' data in json file
        data = []
        existing_urls = set()
        if os.path.exists(f"places_data_{country_name}.json"):
            try:
                with open(
                    f"places_data_{country_name}.json", "r", encoding="utf-8"
                ) as json_file:
                    data = json.load(json_file)
                    existing_urls = {
                        entry["google_map_url"]
                        for entry in data
                        if "google_map_url" in entry
                    }
            except json.JSONDecodeError:
                print(
                    f"Error decoding JSON from places_data_{country_name}.json. Starting fresh."
                )
                self.log_crash(
                    f"Error decoding JSON from places_data_{country_name} file."
                )
                data = []

        unique_results = [
            res
            for res in self.full_results
            if res["google_map_url"] not in existing_urls
        ]
        data.extend(unique_results)

        with open(
            f"places_data_{country_name}.json", "w", encoding="utf-8"
        ) as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=4)

        # Save the data in csv file
        columns = [
            "title",
            "address",
            "phone",
            "governorate",
            "category",
            "rating",
            "number_of_reviews",
            "website",
            "booking_link",
            "google_map_url",
        ]
        if unique_results:
            with open(
                f"places_data_{country_name}.csv", "a", newline="", encoding="utf-8-sig"
            ) as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                if f.tell() == 0:
                    writer.writeheader()
                for result in unique_results:
                    writer.writerow(result)
            print(f"{len(unique_results)} new unique places saved to CSV and JSON.")
        else:
            print("No new unique results to save.")

        # Save Places' google url into json file to loaded when program start to avoid duplication
        searched_data = {}
        if os.path.exists(f"already_searched_{country_name}.json"):
            with open(
                f"already_searched_{country_name}.json", "r", encoding="utf-8"
            ) as f:
                try:
                    searched_data = json.load(f)
                except json.JSONDecodeError:
                    searched_data = {}
                    self.log_crash(
                        f"Error decoding JSON from already_searched_{country_name} file."
                    )

        searched_data.update(self.searched)
        with open(f"already_searched_{country_name}.json", "w", encoding="utf-8") as f:
            json.dump(searched_data, f, ensure_ascii=False, indent=4)

        # Save the searched governorate in json file to avoid looping over searched governorate
        governorate_data = {}
        if os.path.exists(f"searched_governorate_{country_name}.json"):
            with open(
                f"searched_governorate_{country_name}.json", "r", encoding="utf-8"
            ) as f:
                try:
                    governorate_data = json.load(f)
                except json.JSONDecodeError:
                    governorate_data = {}
                    self.log_crash(
                        f"Error decoding JSON from searched_governorate_{country_name} file."
                    )

        governorate_data.update(self.searched_governorate)
        with open(
            f"searched_governorate_{country_name}.json", "w", encoding="utf-8"
        ) as f:
            json.dump(governorate_data, f, ensure_ascii=False, indent=4)

        print(
            f"Already searched governorate saved to searched_governorate_{country_name}.json"
        )

        self.searched.clear()
        self.full_results.clear()
        self.searched_governorate.clear()

    def load_searched_places(self, country_name):
        print("*" * 50)
        country_name = country_name.replace(" ", "_").lower()
        print(
            f"Loading already searched places from already_searched_{country_name}.json"
        )
        try:
            with open(
                f"already_searched_{country_name}.json", "r", encoding="utf-8"
            ) as f:
                self.searched = json.load(f)
            print("Already searched places loaded successfully.")
        except (FileNotFoundError, json.JSONDecodeError):
            self.searched = {}
            print("No previously searched places found. Starting fresh.")
            self.log_crash("No previously searched places found. Starting fresh.")
        print(f"Total number of already searched places: {len(self.searched)}")
        print("*" * 50)

        try:
            with open(
                f"searched_governorate_{country_name}.json", "r", encoding="utf-8"
            ) as f:
                self.searched_governorate = json.load(f)
            print(f"Already searched governorate in {country_name} loaded successfully")
        except (FileNotFoundError, json.JSONDecodeError):
            self.searched_governorate = {}
            print(
                f"No previously searched governorates in {country_name}. Starting fresh."
            )
            self.log_crash(
                f"No previously searched governorates in {country_name}. Starting fresh."
            )
        print(
            f"Total searched governorate in {country_name}: {len(self.searched_governorate)}"
        )
        print("*" * 50)

    def restart_browser(self):
        if self.driver:
            self.driver.quit()
        self.save_results()
        self.setup_driver()
        self.load_searched_places(self.country[1])
        print("=" * 50)
        print("Browser restarted and searched places reloaded.")
        print("=" * 50)

    def move_over_sectors(
        self,
        governorate,
        min_lat,
        max_lat,
        min_lng,
        max_lng,
        start_lat,
        start_lng,
        lat_step=0.03,
        lng_step=0.05,
    ):
        self.governorate_name = governorate

        find_max_lng = False
        find_max_lat = False

        sectors = 0
        num_of_sectors_before_pause = 10
        num_of_sectors_before_restarting = 100

        # Start the lat where we end before close the script or got crashed
        if self.first_coord_loop_lat:
            lat = start_lat
            self.first_coord_loop_lat = False
        else:
            lat = min_lat

        while lat <= max_lat:

            # Start the lng where we end before close the script or got crashed
            if self.first_coord_loop_lng:
                lng = start_lng
                self.first_coord_loop_lng = False
            else:
                lng = min_lng

            while lng <= max_lng:
                self.current_lat = lat
                self.current_lng = lng

                print(
                    f"Searching sector {sectors + 1}: Lat {lat}, Lng {lng} ({self.governorate_name}, {self.country[1]})"
                )

                try:
                    try:
                        # Check if the sector is inside the country
                        inside, near_lat, near_long = find_near_location(
                            lat, lng, self.country[1]
                        )

                        # If the sector is not inside the country, find the nearest location
                        if not inside:
                            print(
                                f"Sector {sectors + 1} is outside the country. Moving to the nearest location: Lat {near_lat}, Lng {near_long}"
                            )
                            self.loading_search_results(near_lat, near_long)
                        else:
                            self.loading_search_results(lat, lng)
                    except Exception as e:
                        print(f"Error finding near location: {e}")
                        self.log_crash(
                            f"Error finding near location at lat: {lat}, lng: {lng} (Error message: {e})"
                        )

                    # Load the search results for the sector then Scrape the data
                    self.scrolling_search_results()
                    self.scrape_results()
                except Exception as e:
                    print("Error in scraping data")
                    self.log_crash(
                        f"Error in scraping data at lat: {lat}, lng: {lng} (Error message: {e})"
                    )

                lng += lng_step
                sectors += 1
                self.total_sectors += 1

                # check if we reached the max longitude
                epsilon = 1e-6
                if not find_max_lng:
                    if abs(lng - max_lng) < epsilon:
                        find_max_lng = True
                    elif lng > max_lng:
                        lng = max_lng
                        find_max_lng = True

                # Pause 5 seconds to avoid block
                if sectors % num_of_sectors_before_pause == 0:
                    print("Avoiding block...")
                    time.sleep(5)

                # After 100 sectors, restart the browser to avoid memory issues
                if self.total_sectors % num_of_sectors_before_restarting == 0:
                    print(f"Total sectors processed: {self.total_sectors}")
                    self.restart_browser()

            lat += lat_step

            epsilon = 1e-6
            if not find_max_lat:
                if abs(lat - max_lat) < epsilon:
                    find_max_lat = True
                elif lat > max_lat:
                    lat = max_lat
                    find_max_lat = True

    def get_governorates_data(self, country="Egypt"):
        """
        Get the governorates data for the specified country.

        Args:
            country (str, optional): Get the governorate depends on the country name. Defaults to "Egypt".

        Returns:
            dict: A dictionary containing the governorates and their bounds.
        """
        with open("governorates_bounds.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(country, [])

    def log_crash(self, message):
        logger.error(
            f"Crashed at lat: {self.current_lat}, lng: {self.current_lng} at {self.governorate_name}, {self.country[1]} (Error message: {message})"
        )


if __name__ == "__main__":
    start_time = time.perf_counter()
    scraper = Scraper()
    try:
        governorates = scraper.get_governorates_data(country=scraper.country[1])

        for governorate in governorates:
            if (
                governorate["governorate"] in scraper.searched_governorate
                and scraper.searched_governorate[governorate["governorate"]]
            ):
                print("*" * 50)
                print(
                    f"This governorate {governorate['governorate']} in {scraper.country[1]} already searched."
                )
                print("*" * 50)
                continue

            scraper.move_over_sectors(
                governorate=governorate["governorate"],
                min_lat=governorate["min_lat"],
                max_lat=governorate["max_lat"],
                min_lng=governorate["min_long"],
                max_lng=governorate["max_long"],
                # These two parameters value changes depend on the lat and long where we stop
                start_lat=governorate["min_lat"],
                start_lng=governorate["min_long"],
            )

            scraper.searched_governorate[governorate["governorate"]] = True
            scraper.save_results()

        print("total time taken:", time.perf_counter() - start_time)
        scraper.driver.quit()
        print("Scraping completed and browsers closed.")
    except (KeyboardInterrupt, Exception) as e:
        print("An error occurred:", e)
        scraper.log_crash(e)
        if scraper.driver:
            scraper.save_results()
            scraper.driver.quit()
