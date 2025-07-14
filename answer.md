### Deep Performance Optimization Plan for `main.py`

To substantially speed up `main.py`, we'll reorganize architecture, minimize overhead, and apply best practices. Below is a prioritized action plan with concrete code-level changes.

---

#### 1. Profile to Identify Hotspots
- **Action**: Integrate `cProfile` to generate a function-level profile report.
- **Implementation**:
  ```python
  import cProfile, pstats

  if __name__ == '__main__':
      profiler = cProfile.Profile()
      profiler.enable()

      main()

      profiler.disable()
      ps = pstats.Stats(profiler).sort_stats('cumtime')
      ps.print_stats(20)
  ```
- **Benefit**: Reveals actual time spent in WebDriver setup, `find_near_location`, parsing, I/O, etc.

---

#### 2. Consolidate WebDriver Instances
- **Current**: `process_keyword` constructs one `Scraper()` *per keyword*, launching one Edge driver each time.
- **Revised**: Launch **one driver per process** and reuse for all keywords in that process.

  ```python
  @classmethod
  def process_keyword(cls, args):
      keyword_list, lat, lng, country, pid = args
      scraper = cls()  # one instance
      scraper.setup_driver()

      # Outside keyword loop: adjust coordinates once
      inside, lat, lng = find_near_location(lat, lng, country)

      for kw in keyword_list:
          try:
              scraper.search_and_scrape(kw, lat, lng)
          except Exception as e:
              scraper.log_crash(str(e))
      scraper.driver.quit()
  ```

- **Benefit**: Cuts driver startup time (~2s+ each) dramatically.

---

#### 3. Batch JSON Writes and Reduce Disk I/O
- **Current**: After each keyword, results are dumped to disk.
- **Revised**: Accumulate all process results in memory, then write a **single JSON** at the end.

  ```python
  places_accum = []
  ...  # inside loop, append to places_accum
  # After loop:
  timestamp = int(time.time())
  with open(f'partial_{pid}_{timestamp}.json', 'w') as f:
      json.dump(places_accum, f, ensure_ascii=False, indent=2)
  ```

- **Benefit**: Minimizes file open/write overhead.

---

#### 4. Optimize Coordinates Lookup
- **Current**: `find_near_location` (heavy geospatial op) called for every keyword.
- **Revised**: Perform **once per sector** before keyword loop.

- **Benefit**: Reduces repeated shapefile loading and spatial computation.

---

#### 5. Switch to Headless Browser & Disable Graphics
- **Action**: Add
  ```python
  options.add_argument('--headless')
  options.add_argument('--disable-gpu')
  ```
- **Benefit**: Minimizes rendering overhead and speeds navigation.

---

#### 6. Use Fast HTML Parser
- **Action**: Change BeautifulSoup parser to `lxml`:
  ```python
  soup = BeautifulSoup(self.driver.page_source, 'lxml')
  ```
- **Benefit**: ~2× faster parsing.

---

#### 7. Replace `time.sleep` with Explicit Waits
- **Action**: Wherever `time.sleep()` is used (e.g., after clicks), switch to `WebDriverWait` for the next element.
- **Benefit**: Reduces unnecessary delays when network is fast.

---

#### 8. Reduce Scrolling Overhead
- **Action**: Lower `max_scroll_attempts` from 20 to ~5 and/or increase JS scroll offset:
  ```js
  driver.execute_script('arguments[0].scrollTop += 1000', feed)
  ```
- **Benefit**: Fewer loops, faster result loading.

---

#### 9. Cache Governorate Bounds in Memory
- **Action**: Load `governorates_bounds.json` once globally, not per Scraper instantiation.

---

#### 10. Parallelize at Sector Level
- **Action**: Instead of splitting by keyword group, have each process handle **all keywords** for one sector. Use `executor.map` over `(lat, lng)`, reducing process startups.
- **Benefit**: Cuts total driver instantiations = #sectors, not #sectors×#keyword-groups.

---

### Example Refactored Flow Sketch
```python
# 1. Preload JSON
GOV_BOUNDS = json.load(open('governorates_bounds.json'))

# 2. process_sector handles one sector
def process_sector(args):
    lat, lng, gov = args
    inside, lat, lng = find_near_location(lat, lng, 'Egypt')
    driver = init_driver()
    acc = []
    for kw_group in keywords_terms:
        for kw in kw_group:
            res = search_and_parse(driver, kw, lat, lng)
            acc.extend(res)
    driver.quit()
    return acc

# 3. Main uses ProcessPoolExecutor on list of sectors
sectors = [(lat, lng, gov) for each sector]
with ProcessPoolExecutor(max_workers=4) as exe:
    for result in exe.map(process_sector, sectors):
        write_to_combined(result)
```

Implementing these changes should yield **5× or more speedup** by cutting redundant operations, reducing external calls, and improving parallelism.
