import csv
import json
import logging
import multiprocessing
import os
import random
import re
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager
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

from is_inside_country import find_near_location, EGYPT_GOVERNORATE_AR_EN
from keywords import keywords_terms
from search_tracker import get_search_tracker

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

USER_AGENTS = [
    # Chrome Desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Firefox Desktop
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:99.0) Gecko/20100101 Firefox/99.0",
    # Edge Desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.2365.66",
]


class Scraper:
    def __init__(self, shared_data=None):
        self.driver = None
        # self.search_query = "أشعة OR radiology"
        self.country = ["Egypt", "Saudi Arabia"]
        self._governorate_name = ""
        self.total_sectors = 0

        # Shared data between processes
        self.manager = (
            shared_data["manager"] if shared_data and "manager" in shared_data else None
        )
        self.full_results = (
            shared_data["full_results"]
            if shared_data and "full_results" in shared_data
            else []
        )
        self.searched_governorate = (
            shared_data.get("searched_governorate", {}) if shared_data else {}
        )
        self.finished_keywords = (
            shared_data.get("finished_keywords", {}) if shared_data else {}
        )
        self.WRITE_LOCK = shared_data.get("WRITE_LOCK") if shared_data else None

        # Initialize search tracker as None, will be set when we have governorate name
        self.search_tracker = None
        self.searched = {}
        if shared_data and "searched" in shared_data:
            self.searched = shared_data["searched"]

        self.current_lat = 0
        self.current_lng = 0

        # Flags to check if we just start the script from the beginning
        # after crash or close it or its an another coordinates in the same run
        self.first_coord_loop_lat = True
        self.first_coord_loop_lng = True

        # Set up process-local data if not using shared data
        if not shared_data:
            self.manager = Manager()
            self.full_results = self.manager.list()
            self.searched = self.manager.dict()
            self.searched_governorate = self.manager.dict()
            self.finished_keywords = self.manager.dict()

        # self.setup_driver()
        self.load_previous_data(self.country[0])

    @property
    def governorate_name(self):
        return self._governorate_name

    @governorate_name.setter
    def governorate_name(self, value: str):
        if not isinstance(value, str):
            raise TypeError("Governorate name must be a string")
        self._governorate_name = value

    @classmethod
    def process_keyword(cls, args):
        """Class method to be called in a separate process"""
        keyword_list, lat, lng, country, process_id = args

        # Create a new scraper instance for this process

        output_file_list = []

        for keywords in keyword_list:
            scraper = cls()
            try:
                scraper.setup_driver()
                # print("*" * 50)
                # print(keywords)
                # print("*" * 50)
                for query in keywords:
                    print("*" * 50)
                    print(query)
                    print("*" * 50)
                    try:
                        print(
                            f"[Process {process_id}] Searching using keyword: {query}"
                        )

                        # Check if the location is inside the country
                        inside, near_lat, near_long = find_near_location(
                            lat, lng, country
                        )
                        if not inside:
                            lat, lng = near_lat, near_long

                        # Load the search results for the sector
                        scraper.loading_search_results(query, lat, lng)

                        # Scroll through and scrape the results
                        scraper.scrolling_search_results()

                        # Scrape results
                        scraper.scrape_results()

                        print(f"[Process {process_id}] Completed search for: {query}")

                        # Save the results to a JSON file
                        timestamp = int(time.time())
                        output_dir = "partial_results"
                        os.makedirs(output_dir, exist_ok=True)
                        output_file = os.path.join(
                            output_dir, f"results_{process_id}_{timestamp}.json"
                        )
                        with open(output_file, "w", encoding="utf-8") as f:
                            json.dump(
                                list(scraper.full_results),
                                f,
                                ensure_ascii=False,
                                indent=2,
                            )
                        output_file_list.append(output_file)
                        print(
                            f"[Process {process_id}] Saved results to {output_file_list}"
                        )

                    except Exception as e:
                        error_msg = f"Error processing keyword '{query}': {e}"
                        print(f"[Process {process_id}] {error_msg}")
                        scraper.log_crash(error_msg)
                        continue

                    time.sleep(2)

            except Exception as e:
                error_msg = f"Error processing keyword '{query}': {e}"
                print(f"[Process {process_id}] {error_msg}")
                if "scraper" in locals():
                    scraper.log_crash(error_msg)

            finally:
                # Clean up the WebDriver
                if (
                    "scraper" in locals()
                    and hasattr(scraper, "driver")
                    and scraper.driver
                ):
                    try:
                        scraper.driver.quit()
                    except Exception as e:
                        logger.error(f"Error quitting WebDriver: {e}")

        # Save the results to a process-specific file
        return output_file_list

    def thread_safe_write(self, data):
        """
        Thread-safe method to write data to results and update search tracker.

        Args:
            data: List of place data dictionaries, each containing a 'google_map_url' key
        """
        if not data:
            return

        # Update search tracker with processed URLs
        for place in data:
            if "google_map_url" in place:
                self.search_tracker.add_searched(
                    place["google_map_url"],
                    {
                        "status": "completed",
                        "timestamp": time.time(),
                        "title": place.get("title", ""),
                    },
                )

        # Save the updated search tracker state
        try:
            self.search_tracker.save()
        except Exception as e:
            logger.error(f"Error saving search tracker: {e}")

        # Write the data to results
        if self.WRITE_LOCK:
            with self.WRITE_LOCK:
                self.full_results.extend(data)
        else:
            # Fallback if WRITE_LOCK is not available
            self.full_results.extend(data)

    def setup_driver(self):
        options = webdriver.EdgeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-extensions")
        # remove cache data
        options.add_argument("--disable-cache")
        # remove cookies
        options.add_argument("--disable-cookies")
        # Add random user-agent
        options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")

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

    def is_search_results_page(self):
        try:
            self.driver.find_element(By.XPATH, '//div[@role="feed"]')
            return True
        except Exception as e:
            self.log_crash(f"Error finding search results page: {e}")
            return False

    def loading_search_results(self, query, lat, lng):
        zoom_out_button = None
        search_area_button = None

        encoded_query = quote_plus(query)
        url = f"https://www.google.com/maps/search/{encoded_query}/@{lat},{lng},16z"
        self.open_url(url)
        time.sleep(2)
        if not self.is_search_results_page():
            self.log_crash(f"Search results page not found at lat: {lat}, lng: {lng}")
            return

        try:
            zoom_out_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.ID, "widget-zoom-out"))
            )
        except (TimeoutException, Exception) as e:
            print(f"Error finding zoom out button: {e}")
            self.log_crash(f"Error finding zoom out button at lat: {lat}, lng: {lng}")
            return
        if zoom_out_button:
            zoom_out_button.click()
            time.sleep(1)
        else:
            print("Zoom out button not found")
            self.log_crash(f"Zoom out button not found at lat: {lat}, lng: {lng}")
            return

        try:
            search_area_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@jsaction='search.refresh']")
                )
            )
        except (TimeoutException, Exception) as e:
            print(f"Error finding search area button: {e}")
            self.log_crash(
                f"Error finding search area button at lat: {lat}, lng: {lng}"
            )
            return
        if search_area_button:
            search_area_button.click()
            time.sleep(1)
        else:
            print("Search area button not found")
            self.log_crash(f"Search area button not found at lat: {lat}, lng: {lng}")
            return

    def scrolling_search_results(self):
        """
        Scroll through the search results feed to load more results.
        """
        feed = None
        try:
            # Wait for the feed element to be present before accessing it
            feed = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//div[@role="feed"]'))
            )
        except (NoSuchElementException, TimeoutException) as e:
            print("Error: Could not find results feed element")
            self.log_crash(f"Could not find results feed element. {e}")
            return

        scroll_pause_time = 2
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
                try:
                    # Wait for the feed element to be present before accessing it
                    feed = WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located(
                            (By.XPATH, '//div[@role="feed"]')
                        )
                    )
                except NoSuchElementException:
                    print("Error: Could not find results feed element")
                    self.log_crash("Could not find results feed element.")
                    return
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

            # Skip if we've already searched this URL
            if self.search_tracker.is_searched(google_map_url):
                print(f"Place already searched ({index + 1}/{len(results_feed)})")
                continue

            print(
                f"Total number of searched places: {self.search_tracker.get_all_searched().get(google_map_url, 0)}"
            )
            self.search_tracker.add_searched(
                google_map_url, {"status": "processing", "timestamp": time.time()}
            )

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
                        "governorate": self._governorate_name,
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

        self.thread_safe_write(places_data)
        print(f"Scraped {len(places_data)} places.")

    @staticmethod
    def combine_results(gov_name):
        """
        Combine all partial result files into final output files.
        Appends new results to existing files while avoiding duplicates.
        """
        governorate = gov_name.lower().replace(" ", "_")
        output_dir = "partial_results"
        output_csv = f"output/places_data_{governorate}.csv"
        output_json = f"output/places_data_{governorate}.json"

        if not os.path.exists(output_dir):
            print("No partial results directory found.")
            return

        # Get all result files
        result_files = [
            f
            for f in os.listdir(output_dir)
            if f.startswith("results_") and f.endswith(".json")
        ]

        if not result_files:
            print("No result files found to combine.")
            return

        # Load existing results if files exist
        existing_results = []
        seen_urls = set()

        # Load existing JSON data if it exists
        if os.path.exists(output_json):
            try:
                with open(output_json, "r", encoding="utf-8") as f:
                    existing_results = json.load(f)
                    seen_urls = {
                        item.get("google_map_url")
                        for item in existing_results
                        if item.get("google_map_url")
                    }
                print(
                    f"Loaded {len(existing_results)} existing results from {output_json}"
                )
            except (json.JSONDecodeError, Exception) as e:
                print(f"Warning: Could not read existing {output_json}: {e}")
                existing_results = []

        all_results = existing_results.copy()
        new_results = 0

        # Process each result file
        for filename in result_files:
            try:
                with open(
                    os.path.join(output_dir, filename), "r", encoding="utf-8"
                ) as f:
                    data = json.load(f)

                # Add only new results (based on google_map_url)
                file_new = 0
                for item in data:
                    url = item.get("google_map_url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(item)
                        file_new += 1
                        new_results += 1

                print(f"Processed {filename}: {len(data)} entries ({file_new} new)")

                # Remove the processed file
                try:
                    os.remove(os.path.join(output_dir, filename))
                except Exception as e:
                    print(f"Warning: Could not remove {filename}: {e}")

            except Exception as e:
                print(f"Error processing {filename}: {e}")
                continue

        if new_results == 0:
            print("No new results to add.")
            return

        print(f"Adding {new_results} new results to existing {len(existing_results)}")

        # Save combined results to JSON
        try:
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
            print(f"Saved {len(all_results)} total results to {output_json}")
        except Exception as e:
            print(f"Error saving to {output_json}: {e}")
            return

        # Save to CSV
        fieldnames = [
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

        try:
            # Determine if we need to write header (only if file doesn't exist)
            write_header = not os.path.exists(output_csv)

            with open(
                output_csv,
                "a" if not write_header else "w",
                newline="",
                encoding="utf-8-sig",
            ) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()

                # Only write new results to CSV
                for result in all_results[len(existing_results) :]:
                    writer.writerow({k: result.get(k, "") for k in fieldnames})

            print(f"Appended {new_results} new results to {output_csv}")

        except Exception as e:
            print(f"Error saving to {output_csv}: {e}")

        # Remove the partial results directory if empty
        try:
            if os.path.exists(output_dir) and not os.listdir(output_dir):
                os.rmdir(output_dir)
        except OSError as e:
            print(f"Warning: Could not remove directory {output_dir}: {e}")

    def load_previous_data(self, country_name):
        """Load previously searched data for the given country.

        Args:
            country_name: Name of the country to load data for
        """
        print("*" * 50)
        print(f"Loading data for {country_name}...")

        # Initialize search tracker for this country
        self.search_tracker = get_search_tracker(country_name, self._governorate_name)

        # For backward compatibility during transition
        self.searched = self.search_tracker.get_all_searched()
        print(f"Loaded {len(self.searched)} previously searched places")

        # Load already searched governorates from file
        gov_file = f"already_searched_governorate_{country_name.lower().replace(' ', '_')}_{self._governorate_name.lower().replace(' ', '_')}.json"
        try:
            if os.path.exists(gov_file):
                with open(gov_file, "r", encoding="utf-8") as f:
                    self.searched_governorate = json.load(f)
                print(
                    f"Loaded {len(self.searched_governorate)} previously searched governorates"
                )
            else:
                self.searched_governorate = {}
                print("No governorate search history found. Starting fresh.")
        except (json.JSONDecodeError, Exception) as e:
            self.searched_governorate = {}
            print(f"Error loading governorate data: {e}")
            logger.error(f"Error loading governorate data: {e}")

        print("*" * 50)

    def restart_browser(self):
        if self.driver:
            self.driver.quit()
        self.save_results()
        self.setup_driver()
        self.load_previous_data(self.country[0])
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
        self._governorate_name = governorate

        find_max_lng = False
        find_max_lat = False

        sectors = 0
        # num_of_sectors_before_pause = 10
        # num_of_sectors_before_restarting = 100

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
                    f"Searching sector {sectors + 1}: Lat {lat}, Lng {lng} ({self._governorate_name}, {self.country[0]})"
                )
                # Process each keyword group
                process_args = []
                for i, group_list in enumerate(keywords_terms):
                    group_name = f"Group_{i + 1}"
                    process_id = f"{group_name}_{i}"

                    process_args.append(
                        (group_list, lat, lng, self.country[0], process_id)
                    )

                os.makedirs("partial_results", exist_ok=True)

                with ProcessPoolExecutor(max_workers=3) as executor:
                    future_to_query = {
                        executor.submit(self.process_keyword, args): args[0]
                        for args in process_args
                    }
                    for future in as_completed(future_to_query):
                        query = future_to_query[future]
                        try:
                            result_file_list = future.result()
                            if result_file_list:
                                print(f"Successfully processed query: {query}")
                                print(f"Results saved to: {result_file_list}")
                            else:
                                print(f"Warning: Failed to process query: {query}")
                        except Exception as e:
                            print(f"Error processing query {query}: {e}")
                            self.log_crash(f"Error processing query {query}: {e}")

                    # After completing a keyword group, combine the results
                    print("Combining results...")
                    Scraper.combine_results(self._governorate_name)
                    print(f"Completed processing keyword group: {group_name}")
                    print("=" * 50)

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
            f"Crashed at lat: {self.current_lat}, lng: {self.current_lng} at {self._governorate_name}, {self.country[0]} (Error message: {message})"
        )
        logger.error(f"{traceback.format_exc()} \n\n")


if __name__ == "__main__":
    start_time = time.perf_counter()
    # Initialize the manager for process-safe data sharing
    manager = Manager()
    WRITE_LOCK = manager.Lock()

    # Initialize the scraper with shared data
    shared_data = {
        "manager": manager,
        "full_results": manager.list(),
        "searched": manager.dict(),
        "searched_governorate": manager.dict(),
        "finished_keywords": manager.dict(),
        "WRITE_LOCK": WRITE_LOCK,
    }

    # Freeze support for Windows multiprocessing
    multiprocessing.freeze_support()

    # Initialize the scraper
    scraper = Scraper(shared_data)

    # Load governorates from JSON file
    with open("governorates_bounds.json", "r", encoding="utf-8") as f:
        governorates_data = json.load(f)

    # Get governorates for the current country (default to first country in the list)
    governorates = governorates_data.get(scraper.country[0], [])

    search_counter = 1
    total_governorates = len(governorates)
    governorate_name = ""

    try:
        # Process each governorate sequentially
        cnt = 1
        for idx, governorate in enumerate(governorates):
            if cnt == 3:
                break

            if cnt == 2:
                if os.path.exists(
                    f"output/already_searched_{scraper.country[0]}_.json"
                ):
                    os.remove(f"output/already_searched_{scraper.country[0]}_.json")

            cnt += 1

            print(governorate["governorate"])

            scraper.governorate_name = str(governorate["governorate"])
            governorate_name = scraper.governorate_name

            # Initialize search tracker with the current governorate
            scraper.search_tracker = get_search_tracker(
                scraper.country[0], governorate_name
            )
            scraper.searched = scraper.search_tracker.get_all_searched()

            print(
                f"\nProcessing governorate {idx}/{total_governorates}: {governorate_name}"
            )

            # Move over sectors for this governorate
            scraper.move_over_sectors(
                governorate=governorate_name,
                min_lat=governorate["min_lat"],
                max_lat=governorate["max_lat"],
                min_lng=governorate["min_long"],
                max_lng=governorate["max_long"],
                start_lat=governorate["min_lat"],
                start_lng=governorate["max_long"],
            )

            print(f"Completed processing governorate: {governorate_name}")

            # Add a delay between governorates to avoid rate limiting
            if idx < total_governorates:
                print("Waiting before processing next governorate...")
                time.sleep(5)
        end_time = time.perf_counter()
        print(
            f"Script execution completed. Total time: {(end_time - start_time)/60:.2f} minutes"
        )
    except KeyboardInterrupt:
        print("\nScript interrupted by user. Combining results...")
        end_time = time.perf_counter()
        print(
            f"Script execution completed. Total time: {(end_time - start_time)/60:.2f} minutes"
        )
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        end_time = time.perf_counter()
        print(
            f"Script execution completed. Total time: {(end_time - start_time)/60:.2f} minutes"
        )
        scraper.log_crash(f"Script crashed with error: {e}")
    finally:
        # Combine all partial results before exiting
        print("Combining results from all processes...")
        Scraper.combine_results(governorate_name)
        print("Results combined successfully.")

        # Close the driver if it's open
        if hasattr(scraper, "driver") and scraper.driver:
            scraper.driver.quit()
            print("WebDriver closed.")

        end_time = time.perf_counter()
        print(
            f"Script execution completed. Total time: {(end_time - start_time)/60:.2f} minutes"
        )
