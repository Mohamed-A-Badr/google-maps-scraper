import csv
import json
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


class Scraper:
    def __init__(self):
        self.driver = None
        self.search_query = "أشعة OR سينية OR radiology"
        self.total_sectors = 0
        self.full_results = []
        self.searched = {}

        self.setup_driver()
        self.load_searched_places()

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
            raise RuntimeError(f"Failed to initialize Edge WebDriver: {e}")

    def open_url(self, url):
        if self.driver is not None:
            self.driver.get(url)
        else:
            raise RuntimeError("Driver not initialized.")

    def loading_search_results(self, lat, lng):
        encoded_query = quote_plus(self.search_query)
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
        time.sleep(1)

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
        time.sleep(1)

    def scrolling_search_results(self):
        """
        Scroll through the search results feed to load more results.
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
            time.sleep(scroll_pause_time)

            current_results = len(
                feed.find_elements(By.XPATH, './/a[contains(@href, "/maps/place")]')
            )
            if current_results == 0:
                print("No results found.")
                break

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
                print(f"Place {index + 1}/{len(results_feed)} already processed.")
                continue

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
                reviews_text = reviews_elements[1].get_text()
                if re.match(r"^\(\d+\)$", reviews_text):
                    number_of_reviews = reviews_text

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
        data = []
        existing_urls = set()
        if os.path.exists("places_data.json"):
            try:
                with open("places_data.json", "r", encoding="utf-8") as json_file:
                    data = json.load(json_file)
                    existing_urls = {
                        entry["google_map_url"]
                        for entry in data
                        if "google_map_url" in entry
                    }
            except json.JSONDecodeError:
                print("Error decoding JSON from places_data.json. Starting fresh.")
                data = []

        unique_results = [
            res
            for res in self.full_results
            if res["google_map_url"] not in existing_urls
        ]
        data.extend(unique_results)

        with open("places_data.json", "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=4)

        columns = [
            "title",
            "address",
            "phone",
            "category",
            "rating",
            "number_of_reviews",
            "website",
            "booking_link",
            "google_map_url",
        ]
        if unique_results:
            with open("places_data.csv", "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                if f.tell() == 0:
                    writer.writeheader()
                for result in unique_results:
                    writer.writerow(result)
            print(f"{len(unique_results)} new unique places saved to CSV and JSON.")
        else:
            print("No new unique results to save.")

        searched_data = {}
        if os.path.exists("already_searched.json"):
            with open("already_searched.json", "r", encoding="utf-8") as f:
                try:
                    searched_data = json.load(f)
                except json.JSONDecodeError:
                    searched_data = {}

        searched_data.update(self.searched)
        with open("already_searched.json", "w", encoding="utf-8") as f:
            json.dump(searched_data, f, ensure_ascii=False, indent=4)

        print("Already searched places saved to already_searched.json")
        self.searched.clear()
        self.full_results.clear()

    def load_searched_places(self):
        print("*" * 50)
        print("Loading already searched places from already_searched.json")
        try:
            with open("already_searched.json", "r", encoding="utf-8") as f:
                self.searched = json.load(f)
            print("Already searched places loaded successfully.")
        except (FileNotFoundError, json.JSONDecodeError):
            self.searched = {}
            print("No previously searched places found. Starting fresh.")
        print("*" * 50)

    def restart_browser(self):
        if self.driver:
            self.driver.quit()
        self.save_results()
        self.setup_driver()
        self.load_searched_places()
        print("=" * 50)
        print("Browser restarted and searched places reloaded.")
        print("=" * 50)

    def move_over_sectors(
        self, min_lat, max_lat, min_lng, max_lng, lat_step=0.03, lng_step=0.05
    ):
        lat = min_lat
        sectors = 0
        num_of_sectors_before_pause = 20
        num_of_sectors_before_restarting = 5
        while lat <= max_lat:
            lng = min_lng
            while lng <= max_lng:
                print(f"Searching sector {sectors + 1}: Lat {lat}, Lng {lng}")
                self.loading_search_results(lat, lng)
                self.scrolling_search_results()
                self.scrape_results()

                lng += lng_step
                sectors += 1
                self.total_sectors += 1

                if sectors % num_of_sectors_before_pause == 0:
                    print("Avoiding block...")
                    time.sleep(5)
                if self.total_sectors % num_of_sectors_before_restarting == 0:
                    print(f"Total sectors processed: {self.total_sectors}")
                    self.restart_browser()
            lat += lat_step


if __name__ == "__main__":
    start_time = time.perf_counter()
    scraper = Scraper()
    try:
        lat = 29.9976991
        lng = 31.1819956

        scraper.move_over_sectors(
            min_lat=lat - 0.15,
            max_lat=lat + 0.15,
            min_lng=lng - 0.15,
            max_lng=lng + 0.15,
        )
        scraper.save_results()

        print("total time taken:", time.perf_counter() - start_time)
        scraper.driver.quit()
        print("Scraping completed and browsers closed.")
    except (KeyboardInterrupt, Exception) as e:
        print("An error occurred:", str(e))
        if scraper.driver:
            scraper.save_results()
            scraper.driver.quit()
