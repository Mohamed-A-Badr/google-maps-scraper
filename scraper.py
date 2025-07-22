"""
NOTE
[] attributes
    - [X] dirver
    - [X] country
    - [X] governorate
    - [] total_sectors
    - [] manager
    - [X] full_results
    - [] searched_governorate
    - [] finished_keywords
    - [] WRITE_LOCK
    - [X] search_tracker
    - [] searched
    - [X] current_lat
    - [X] current_lng
?   - [X] starter_lat
?   - [X] starter_long
    - [] first_coord_loop_lat
    - [] first_coord_loop_lng
[] methods
    - [-] getters setters
    - [X] setup_driver
    - [X] log_crash
    - [X] open_url
    - [X] load_previous_data
    - [X] loading_search_results
    - [X] is_search_results_page
    - [X] scrolling_search_results
    - [X] scrape_results
    - [X] thread_safe_write
    - [X] combine_results
    - [X] Process_keyword
?   - [X] multi_keywords
?   - [X] Single_keywords
    - [X] move_over_sectors
"""

import csv
import json
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

from is_inside_country import find_near_location
from keywords import keywords_terms
from logger import info_logger, logger
from search_tracker import get_search_tracker
from sector_generator import generate

USER_AGENTS = [
    # Chrome Desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Firefox Desktop
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:99.0) Gecko/20100101 Firefox/99.0",
    # Edge Desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.2365.66",
]

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)


class Scraper:
    def __init__(self, shared_data=None):
        self._driver = None

        self._current_lat = 0
        self._current_long = 0

        self._starter_lat = True
        self._starter_long = True

        self._governorate = ""
        self._country = ""

        self._search_tracker = None
        self._searched = {}
        self._searched_governorate = {}

        self.full_results = []

        self._manager = None
        self._WRITE_LOCK = None

    # =============================================
    # Initialize getters and setters
    # =============================================

    @property
    def current_lat(self):
        return self._current_lat

    @current_lat.setter
    def current_lat(self, value):
        self._current_lat = value

    @property
    def current_long(self):
        return self._current_long

    @current_long.setter
    def current_long(self, value):
        self._current_long = value

    @property
    def governorate(self):
        return self._governorate

    @governorate.setter
    def governorate(self, value):
        self._governorate = value

    @property
    def country(self):
        return self._country

    @country.setter
    def country(self, value):
        self._country = value

    @property
    def search_tracker(self):
        return self._search_tracker

    @search_tracker.setter
    def search_tracker(self, value):
        self._search_tracker = value

    @property
    def searched(self):
        return self._searched

    @searched.setter
    def searched(self, value):
        self._searched = value

    @property
    def searched_governorate(self):
        return self._searched_governorate

    @searched_governorate.setter
    def searched_governorate(self, value):
        self._searched_governorate = value

    @property
    def manager(self):
        return self._manager

    @manager.setter
    def manager(self, value):
        self._manager = value

    @property
    def WRITE_LOCK(self):
        return self._WRITE_LOCK

    @WRITE_LOCK.setter
    def WRITE_LOCK(self, value):
        self._WRITE_LOCK = value

    # =============================================
    # Initilize attributes for multi-keywords
    # =============================================
    def _multi_keywords_init_(self, shared_data=None):
        if not shared_data:
            self.manager = Manager()
            self.full_results = self.manager.list()
            self.searched = self.manager.dict()
            self.searched_governorate = self.manager.dict()
            self.finished_keywords = self.manager.dict()

        self.manager = (
            shared_data["manager"] if shared_data and "manager" in shared_data else None
        )
        self.full_results = (
            shared_data["full_results"]
            if shared_data and "full_results" in shared_data
            else []
        )
        self.searched = shared_data.get("searched", {}) if shared_data else {}
        self.searched_governorate = (
            shared_data.get("searched_governorate", {}) if shared_data else {}
        )
        self.finished_keywords = (
            shared_data.get("finished_keywords", {}) if shared_data else {}
        )
        self.WRITE_LOCK = shared_data.get("WRITE_LOCK") if shared_data else None

    # =============================================
    # Initilize selenium driver
    # =============================================

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
            self._driver = webdriver.Edge(options=options, service=service)
        except WebDriverException as e:
            self.log_crash(f"WebDriverException: {e}")
            raise RuntimeError(f"Failed to initialize Edge WebDriver: {e}")

    # =============================================
    # Log crashes
    # =============================================

    def log_crash(self, message):
        logger.error(
            f"Crashed at lat: {self.current_lat}, long: {self.current_long} at {self.governorate}, {self.country} (Error message: {message})"
        )
        logger.error(f"{traceback.format_exc()} \n\n")

    # =============================================
    # Open Searching url
    # =============================================
    def open_url(self, url):
        if self._driver is not None:
            self._driver.get(url)
        else:
            self.log_crash("Driver not initialized.")
            raise RuntimeError("Driver not initialized.")

    # =============================================
    # Restart the browser
    # =============================================
    def restart_browser(self):
        if self._driver is not None:
            self._driver.quit()
            self._driver = None
        self.save_results()
        self.setup_driver()
        self.load_previous_data()
        print("=" * 50)
        print("Browser restarted and searched places reloaded.")
        print("=" * 50)

    # =============================================
    # Loading pervious results to avoid duplicate
    # =============================================
    def load_previous_data(self):
        """
        Load previously searched data for the given country.
        """
        print("*" * 50)
        print(f"Loading data for {self.country}...")

        # info_logger.info(f"{self.governorate}, {self.country}")
        # Initialize search tracker for this country
        self.search_tracker = get_search_tracker(self.country, self.governorate)

        # For backward compatibility during transition
        self.searched = self.search_tracker.get_all_searched()
        print(f"Loaded {len(self.searched)} previously searched places")

        # Load already searched governorates from file
        # gov_file = f"already_searched_governorate_{self.country.lower().replace(' ', '_')}_{self.governorate.lower().replace(' ', '_')}.json"
        # try:
        #     if os.path.exists(gov_file):
        #         with open(gov_file, "r", encoding="utf-8") as f:
        #             self.searched_governorate = json.load(f)
        #         print(
        #             f"Loaded {len(self.searched_governorate)} previously searched governorates"
        #         )
        #     else:
        #         self.searched_governorate = {}
        #         print("No governorate search history found. Starting fresh.")
        # except (json.JSONDecodeError, Exception) as e:
        #     self.searched_governorate = {}
        #     print(f"Error loading governorate data: {e}")
        #     logger.error(f"Error loading governorate data: {e}")

        print("*" * 50)

    # =============================================
    # Checking if the search feed exists
    # =============================================
    def is_search_results_page(self):
        try:
            self._driver.find_element(By.XPATH, '//div[@role="feed"]')
            return True
        except Exception as e:
            self.log_crash(f"Error finding search results page: {e}")
            return False

    # =============================================
    # Accessing search feed to get results
    # =============================================
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
            zoom_out_button = WebDriverWait(self._driver, 20).until(
                EC.element_to_be_clickable((By.ID, "widget-zoom-out"))
            )
        except (TimeoutException, Exception) as e:
            print(f"Error finding zoom out button: {e}")
            self.log_crash(f"Error finding zoom out button at lat: {lat}, lng: {lng}")
            return
        if zoom_out_button:
            zoom_out_button.click()
        else:
            print("Zoom out button not found")
            self.log_crash(f"Zoom out button not found at lat: {lat}, lng: {lng}")
            return

        try:
            search_area_button = WebDriverWait(self._driver, 20).until(
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

    # =============================================
    # Scrolling to get max search result
    # =============================================
    def scrolling_search_results(self):
        """
        Scroll through the search results feed to load more results.
        """
        feed = None
        try:
            # Wait for the feed element to be present before accessing it
            feed = WebDriverWait(self._driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//div[@role="feed"]'))
            )
        except (NoSuchElementException, TimeoutException) as e:
            print("Error: Could not find results feed element")
            self.log_crash(f"Could not find results feed element. {e}")
            return

        scroll_pause_time = 2
        last_height = self._driver.execute_script(
            "return arguments[0].scrollHeight", feed
        )
        scroll_attempts = 0
        max_scroll_attempts = 20

        while scroll_attempts < max_scroll_attempts:
            try:
                self._driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight", feed
                )
                time.sleep(scroll_pause_time)
                # Re-acquire the feed element to avoid stale reference
                try:
                    # Wait for the feed element to be present before accessing it
                    feed = WebDriverWait(self._driver, 20).until(
                        EC.presence_of_element_located(
                            (By.XPATH, '//div[@role="feed"]')
                        )
                    )
                except NoSuchElementException:
                    print("Error: Could not find results feed element")
                    self.log_crash("Could not find results feed element.")
                    return
                new_height = self._driver.execute_script(
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

    # =============================================
    # Scraping places data
    # =============================================
    def scrape_results(self):
        """
        Scrape the results from the place's page and store them in full_results.
        """
        places_data = []
        soup = BeautifulSoup(self._driver.page_source, "lxml")
        results_feed = soup.find_all("a", class_="hfpxzc")

        for index, i in enumerate(results_feed):
            if (index + 1) % 50 == 0 and not CONFIG["multi_keywords"]:
                self.restart_browser()

            google_map_url = i.get("href")

            # Skip if we've already searched this URL
            if self.search_tracker.is_searched(google_map_url):
                print(f"Place already searched ({index + 1}/{len(results_feed)})")
                continue

            self.search_tracker.add_searched(
                google_map_url, {"status": "processing", "timestamp": time.time()}
            )

            self.open_url(google_map_url)
            print(f"Processing place {index + 1}/{len(results_feed)}")
            info_logger.info(f"Processing place {index + 1}/{len(results_feed)}")

            card_data = BeautifulSoup(self._driver.page_source, "lxml")

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
                card = WebDriverWait(self._driver, 10).until(
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
                        "governorate": self.governorate,
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
        if CONFIG["multi_keywords"]:
            self.thread_safe_write(places_data)
        else:
            self.full_results.extend(places_data)
        print(f"Scraped {len(places_data)} places.")

    # =============================================
    # Scraping places with multiple keywords
    # =============================================

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

    @staticmethod
    def combine_results(gov_name):
        """
        Combine all partial result files into final output files.
        Appends new results to existing files while avoiding duplicates.
        """
        output_dir = "partial_results"
        output_csv = f"output/places_data_{gov_name}.csv"
        output_json = f"output/places_data_{gov_name}.json"

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

    @classmethod
    def process_keyword(cls, args):
        """Class method to be called in a separate process"""
        keyword_list, current_sector, total_sectors, lat, long, process_id = args

        # Create a new scraper instance for this process

        output_file_list = []

        print("*" * 50)
        print("I'm in process keyword")
        print("*" * 50)

        scraper = cls()
        try:
            scraper.setup_driver()
            scraper.load_previous_data()
            for keywords in keyword_list:
                # print("*" * 50)
                # print(keywords)
                # print("*" * 50)
                for query in keywords:
                    # print("*" * 50)
                    # print(query)
                    # print("*" * 50)
                    try:
                        print(
                            f"[Process {process_id}] Searching using keyword: {query} {current_sector}/{total_sectors}"
                        )
                        info_logger.info(
                            f"[Process {process_id}] Searching using keyword: {query} {current_sector}/{total_sectors}"
                        )
                        # Load the search results for the sector
                        scraper.loading_search_results(query, lat, long)

                        # Scroll through and scrape the results
                        scraper.scrolling_search_results()

                        # Scrape results
                        scraper.scrape_results()

                        print(
                            f"[Process {process_id}] Completed search for: {query} {current_sector}/{total_sectors}"
                        )
                        info_logger.info(
                            f"[Process {process_id}] Completed search for: {query} {current_sector}/{total_sectors}"
                        )

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
                            f"[Process {process_id}] Saved results to {len(output_file_list)} files {current_sector}/{total_sectors}"
                        )
                        info_logger.info(
                            f"[Process {process_id}] Saved results to {len(output_file_list)} files {current_sector}/{total_sectors}"
                        )

                    except Exception as e:
                        error_msg = f"Error processing keyword '{query}': {e} {current_sector}/{total_sectors}"
                        print(f"[Process {process_id}] {error_msg}")
                        scraper.log_crash(error_msg)
                        continue

        except Exception as e:
            error_msg = f"Error processing keyword '{query}': {e} {current_sector}/{total_sectors}"
            print(
                f"[Process {process_id}] {error_msg} {current_sector}/{total_sectors}"
            )
            if "scraper" in locals():
                scraper.log_crash(error_msg)

        finally:
            # Clean up the WebDriver
            if "scraper" in locals() and hasattr(scraper, "driver") and scraper._driver:
                try:
                    scraper._driver.quit()
                except Exception as e:
                    logger.error(f"Error quitting WebDriver: {e}")

        # Save the results to a process-specific file
        return output_file_list

    def multi_keywords(self, current_sector, total_sectors):
        process_args = []
        for i, group_list in enumerate(keywords_terms):
            group_name = f"Group_{i + 1}"
            process_id = f"{group_name}_{i}"

            process_args.append(
                (
                    group_list,
                    current_sector,
                    total_sectors,
                    self.current_lat,
                    self.current_long,
                    process_id,
                )
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
            Scraper.combine_results(self.governorate)
            print(f"Completed processing keyword group: {group_name}")
            print("=" * 50)

    # =============================================
    # Scraping places with one keyword
    # =============================================

    def save_results(self):
        os.makedirs("output", exist_ok=True)
        csv_file = f"output/{self.governorate}.csv"
        json_file = f"output/{self.governorate}.json"

        # Save data in json file
        try:
            with open(json_file, "w", encoding="utf-8") as f:
                print("Saving data in json file...")
                json.dump(list(self.full_results), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error Saving json file: {e}")
            self.log_crash(f"Error Saving json file: {e}")

        print("Json file saved successfully")

        field_name = [
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

        # Save data in csv file
        try:
            csv_file_exists = not os.path.exists(csv_file)
            with open(
                csv_file,
                "a" if not csv_file_exists else "w",
                newline="",
                encoding="utf-8-sig",
            ) as f:
                writer = csv.DictWriter(f, fieldnames=field_name)
                if csv_file_exists:
                    writer.writeheader()
                for result in self.full_results:
                    writer.writerow({k: result.get(k, "") for k in field_name})

        except Exception as e:
            print(f"Error Saving csv file: {e}")
            self.log_crash(f"Error Saving csv file: {e}")
        print("Csv file saved successfully")

        # Update search tracker with processed URLs
        for place in self.full_results:
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

        self.full_results.clear()

    def single_keyword(self, sector):
        self.current_lat, self.current_long = sector
        try:
            self.loading_search_results(
                query=CONFIG["keyword"], lat=self.current_lat, lng=self.current_long
            )
            self.scrolling_search_results()
            self.scrape_results()
            self.save_results()
        except Exception as e:
            self.log_crash(f"Error loading search results: {e}")

    # =============================================
    # Generate sectors
    # =============================================

    def generate_sectors(
        self,
        min_lat: float,
        max_lat: float,
        min_long: float,
        max_long: float,
        step_lat: float,
        step_long: float,
    ) -> list:
        sectors_list = []

        lat = min_lat
        find_max_lat = False

        while lat <= max_lat:
            long = min_long
            find_max_long = False

            while long <= max_long:
                inside, near_lat, near_long = find_near_location(
                    lat, long, self.country
                )
                sectors_list.append((lat, long) if inside else (near_lat, near_long))

                long += step_long

                epsilon = 1e-6
                if not find_max_long:
                    if abs(long - max_long) < epsilon:
                        find_max_long = True
                    elif long > max_long:
                        long = max_long
                        find_max_long = True

            lat += step_lat

            epsilon = 1e-6
            if not find_max_lat:
                if abs(lat - max_lat) < epsilon:
                    find_max_lat = True
                elif lat > max_lat:
                    lat = max_lat
                    find_max_lat = True

        return sectors_list

    # =============================================
    # Move over sectors
    # =============================================

    def move_over_sectors(
        self,
        sectors_list: list,
        start_sector_idx: int = 0,
    ):
        for idx, sector in enumerate(sectors_list):
            if idx < start_sector_idx:
                continue

            self.current_lat, self.current_long = sector

            print(
                f" 📍 Searching sector {idx}/{len(sectors_list) - 1}: Lat {self.current_lat}, long {self.current_long} ({self.governorate}, {self.country})"
            )
            info_logger.info(
                f"Searching sector {idx}/{len(sectors_list) - 1}: Lat {self.current_lat}, long {self.current_long} ({self.governorate}, {self.country})"
            )

            if CONFIG["multi_keywords"]:
                self.multi_keywords(idx, len(sectors_list))
            else:
                # print("*" * 50)
                # print("Single keyword")
                self.single_keyword(sector)
                # print("*" * 50)


if __name__ == "__main__":
    start_time = time.perf_counter()

    scraper = Scraper()
    scraper.setup_driver()

    if CONFIG["multi_keywords"]:
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
        multiprocessing.freeze_support()

        scraper._multi_keywords_init_(shared_data=shared_data)

    with open("governorates_bounds.json", "r", encoding="utf-8") as f:
        governorate_list = json.load(f)

    scraper.country = CONFIG["country"]
    governorates = governorate_list.get(scraper.country, "")

    total_governorates = len(governorates)

    try:
        for idx, governorate in enumerate(governorates):
            print(governorate)

            scraper.governorate = str(governorate["governorate"])
            scraper.load_previous_data()
            scraper.search_tracker = get_search_tracker(
                scraper.country, scraper.governorate
            )
            scraper.searched = scraper.search_tracker.get_all_searched()

            print(f"\nProcessing governorate {idx}/{total_governorates}: {governorate}")

            # sectors_list = scraper.generate_sectors(
            #     min_lat=governorate["min_lat"],
            #     max_lat=governorate["max_lat"],
            #     min_long=governorate["min_long"],
            #     max_long=governorate["max_long"],
            #     step_lat=CONFIG["step_lat"],
            #     step_long=CONFIG["step_long"],
            # )

            # print(f"Generated {len(sectors_list)} sectors for {scraper.governorate}")
            # print(sectors_list)

            # exit()

            sectors_list = generate(governorate=scraper.governorate)

            # Move over sectors for this governorate
            scraper.move_over_sectors(
                sectors_list=sectors_list,
                start_sector_idx=CONFIG["start_sector_idx"],
            )
            print(f"Completed processing governorate: {scraper.governorate}")

            break

        end_time = time.perf_counter()
        print(
            f"Script execution completed. Total time: {(end_time - start_time) / 60:.2f} minutes"
        )
    except KeyboardInterrupt:
        print("\nScript interrupted by user. Saving results...")
        end_time = time.perf_counter()
        print(
            f"Script execution completed. Total time: {(end_time - start_time) / 60:.2f} minutes"
        )
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        end_time = time.perf_counter()
        print(
            f"Script execution completed. Total time: {(end_time - start_time) / 60:.2f} minutes"
        )
        scraper.log_crash(f"Script crashed with error: {e}")
    finally:
        # If in single keyword mode, save the in-memory results to a file
        if not CONFIG["multi_keywords"]:
            scraper.save_results()

        # Combine all partial results before exiting
        if CONFIG["multi_keywords"]:
            print("Combining results from all processes...")
            Scraper.combine_results(scraper.governorate)
            print("Results combined successfully.")
        else:
            print("Saving results...")
            scraper.save_results()
            print("Results saved successfully.")

        # Close the driver if it's open
        if hasattr(scraper, "driver") and scraper.driver:
            scraper.driver.quit()
            print("WebDriver closed.")

        end_time = time.perf_counter()
        print(
            f"Script execution completed. Total time: {(end_time - start_time) / 60:.2f} minutes"
        )
