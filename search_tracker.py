import json
import os
from multiprocessing import Manager, Lock
from typing import Set, Dict, Any
import logging

logger = logging.getLogger(__name__)

class SearchTracker:
    def __init__(self, country: str):
        """
        Initialize the search tracker for a specific country.
        
        Args:
            country: Country name (used for the filename)
        """
        self.country = country.lower().replace(" ", "_")
        self.filename = f"already_searched_{self.country}.json"
        self.lock = Lock()
        
        # Use a Manager for process-safe sharing
        self.manager = Manager()
        self.searched_urls = self.manager.dict()
        
        # Load existing data if available
        self._load()
    
    def _load(self) -> None:
        """Load searched URLs from file."""
        if not os.path.exists(self.filename):
            return
            
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.searched_urls.update(data)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error loading searched URLs: {e}")
    
    def save(self) -> None:
        """Save the current state to file."""
        try:
            with self.lock:
                with open(self.filename, 'w', encoding='utf-8') as f:
                    # Convert to regular dict for JSON serialization
                    json.dump(dict(self.searched_urls), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving searched URLs: {e}")
    
    def add_searched(self, url: str, data: Dict[str, Any] = None) -> None:
        """
        Add a URL to the searched set.
        
        Args:
            url: The Google Maps URL that was searched
            data: Optional additional data to store with the URL
        """
        with self.lock:
            self.searched_urls[url] = data or {}
    
    def is_searched(self, url: str) -> bool:
        """Check if a URL has already been searched."""
        with self.lock:
            return url in self.searched_urls
    
    def get_all_searched(self) -> Dict[str, Any]:
        """Get all searched URLs and their data."""
        with self.lock:
            return dict(self.searched_urls)
    
    def clear(self) -> None:
        """Clear all searched URLs."""
        with self.lock:
            self.searched_urls.clear()
            try:
                if os.path.exists(self.filename):
                    os.remove(self.filename)
            except Exception as e:
                logger.error(f"Error clearing search tracker: {e}")

# Global instance for the current country
global_search_tracker = None

def get_search_tracker(country: str) -> 'SearchTracker':
    """Get or create a global search tracker for the country."""
    global global_search_tracker
    if global_search_tracker is None or global_search_tracker.country != country.lower().replace(" ", "_"):
        global_search_tracker = SearchTracker(country)
    return global_search_tracker
