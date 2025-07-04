# Google Maps Data Scraper

This project is a Python script designed to automatically extract information and reviews for a specific place on Google Maps. It uses the `Playwright` library to automate the web browser and saves the extracted data in a structured format.

## Features

- Extracts general information about a place on Google Maps (name, rating, review count, address, phone, website, category, price level, opening hours).
- Extracts place reviews (author, rating, review text, date).
- Saves extracted data into readable CSV files.
- Creates a unique folder for each scraping session and saves debugging information like screenshots to this folder.
- Provides an option to sort reviews by newest or most relevant.
- Ability to extract up to a specified maximum number of reviews.

## Requirements

To run this project, you will need the following software and Python libraries:

- Python 3.x
- Git (for downloading Playwright browsers)

### Python Libraries

You can install the necessary Python libraries using the following command:

```bash
pip install playwright pandas python-slugify tqdm
```

### Browser Setup

`Playwright` needs to download browser engines to automate web pages. You can install them by running the following command:

```bash
playwright install
```

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/your_username/URL-Scraper.git
   cd URL-Scraper
   ```
2. Install the required Python libraries and Playwright browsers (see "Requirements" section above).

## Usage

You need to run the script from the command line.

```bash
python "Google Place ID Review Scraper.py" <Google Maps URL> [max_reviews] [sort_type]
```

Example:

- **Running with default settings (up to 100 reviews, sorted by newest):**
  ```bash
  python "Google Place ID Review Scraper.py" "https://www.google.com/maps/place/Starbucks/@40.985655,29.027581,17z/data=!3m1!4b1!4m6!3m5!1s0x14cac7936a1c5d19:0x8e8e8e8e8e8e8e8e!8m2!3d40.985655!4d29.030156!16s%2Fg%2F11b6m7m07s"
  ```

- **Extracting 50 reviews and sorting by most relevant:**
  ```bash
  python "Google Place ID Review Scraper.py" "https://www.google.com/maps/place/Starbucks/@40.985655,29.027581,17z/data=!3m1!4b1!4m6!3m5!1s0x14cac7936a1c5d19:0x8e8e8e8e8e8e8e8e!8m2!3d40.985655!4d29.030156!16s%2Fg%2F11b6m7m07s" 50 "most_relevant"
  ```

### Parameters:

- `<Google Maps URL>`: (Required) The full URL of the Google Maps place you want to scrape.
- `[max_reviews]`: (Optional) The maximum number of reviews to scrape. Defaults to 100.
- `[sort_type]`: (Optional) The sorting method for reviews. Accepted values:
    - `"newest"` (Default): Newest reviews.
    - `"most_relevant"`: Most relevant reviews.
    - `"highest_rating"`: Highest-rated reviews.
    - `"lowest_rating"`: Lowest-rated reviews.

## How it Works

The main operational steps of the script are as follows:

1.  **Initialization:**
    -   The Playwright browser is launched (by default in `headless=False` mode, meaning you can see the browser interface).
    -   A new browser context and page are created.
    -   The script navigates to the Google Maps URL provided by the user.

2.  **Accepting Cookies:**
    -   If present, the script attempts to close the cookie acceptance pop-up.

3.  **Getting Place Name:**
    -   The script tries to identify the name of the place using various CSS selectors on the page. If a reliable name cannot be found, a default name is used.

4.  **Creating Output Folder:**
    -   A folder named after the place and a unique session ID is created under the `~/Downloads` directory to save extracted data and debugging screenshots.

5.  **Collecting General Information:**
    -   General information about the place such as rating, review count, address, phone number, website, category, price level, and opening hours is collected by scanning relevant elements.

6.  **Scraping Reviews:**
    -   The script navigates to the reviews section.
    -   Reviews are loaded until the specified `max_reviews` count or the end of the page is reached, and information for each review (author, rating, text, date) is extracted.
    -   Reviews are sorted according to the specified `sort_by` parameter.
    -   The page is scrolled down to load more reviews.

7.  **Saving Data:**
    -   The extracted general information and reviews are converted into `pandas` DataFrames.
    -   These DataFrames are saved as CSV files named `genel_bilgiler.csv` (general_info.csv) and `yorumlar.csv` (reviews.csv) within the created folder.

8.  **Closing Browser:**
    -   After the data extraction is complete, the browser is closed.

## Project Structure

```
URL Scraper/
├── Google Place ID Review Scraper.py   # Main data scraping script
├── pyrightconfig.json                  # Configuration file for Pyright static analysis tool
└── README.md                           # This README file
```

## Development

If you'd like to contribute to the code, feel free to open a pull request. 