import logging
import csv
import os
import json
from datetime import datetime
from typing import List, Dict
from linkedin_jobs_scraper import LinkedinScraper
from linkedin_jobs_scraper.events import Events, EventData, EventMetrics
from linkedin_jobs_scraper.query import Query, QueryOptions, QueryFilters
from linkedin_jobs_scraper.filters import RelevanceFilters, TimeFilters, TypeFilters, ExperienceLevelFilters, \
    OnSiteOrRemoteFilters, SalaryBaseFilters

class LinkedInJobsScraper:
    def __init__(self, output_file='linkedin_jobs.csv'):
        self.output_file = output_file
        self.jobs_data = []
        self.existing_job_ids = set()  
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger('linkedin_scraper')
        
        # Load config from environment variables
        self.config = self.load_config_from_env()
        
        # Load existing job IDs from CSV
        self.load_existing_job_ids()
        
    def load_config_from_env(self) -> Dict:
        """Load configuration from environment variables (GitHub secrets)"""
        # Default configuration
        default_config = {
            'cookie': '',
            'search_queries': [
                {
                    'query': 'Python Developer',
                    'locations': ['United States'],
                    'limit': 50
                },
                {
                    'query': 'Software Engineer',
                    'locations': ['United States'],
                    'limit': 50
                }
            ],
            'scraper_settings': {
                'headless': True,
                'max_workers': 1,
                'slow_mo': 1.0,
                'page_load_timeout': 40
            }
        }
        
        try:
            # Load LinkedIn cookie from environment variable
            cookie = os.getenv('LINKEDIN_COOKIE')
            if cookie:
                default_config['cookie'] = cookie
                self.logger.info("LinkedIn cookie loaded from environment variable")
            else:
                self.logger.warning("LINKEDIN_COOKIE environment variable not found")
            
            # Load search configuration from environment variable (JSON format)
            search_config = os.getenv('SEARCH_CONFIG')
            if search_config:
                try:
                    search_data = json.loads(search_config)
                    if 'search_queries' in search_data:
                        default_config['search_queries'] = search_data['search_queries']
                        self.logger.info("Search queries loaded from environment variable")
                    if 'scraper_settings' in search_data:
                        default_config['scraper_settings'].update(search_data['scraper_settings'])
                        self.logger.info("Scraper settings loaded from environment variable")
                except json.JSONDecodeError as e:
                    self.logger.error(f"Error parsing SEARCH_CONFIG JSON: {e}")
            else:
                self.logger.info("Using default search configuration")
            
            return default_config
            
        except Exception as e:
            self.logger.error(f"Error loading config from environment: {e}")
            return default_config
    
    def load_existing_job_ids(self):
        """Load existing job IDs from CSV file to avoid duplicates"""
        if not os.path.exists(self.output_file):
            self.logger.info("No existing CSV file found. Starting fresh.")
            return
        
        try:
            with open(self.output_file, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    job_id = row.get('job_id', '').strip()
                    if job_id:
                        self.existing_job_ids.add(job_id)
            
            self.logger.info(f"Loaded {len(self.existing_job_ids)} existing job IDs from CSV")
            
        except Exception as e:
            self.logger.error(f"Error loading existing job IDs: {e}")
            self.existing_job_ids = set()  # Reset to empty set on error
    
    def check_authentication(self) -> bool:
        """Check if LinkedIn authentication is available"""
        # Check environment variable first
        li_at_cookie = os.getenv('LI_AT_COOKIE')
        linkedin_cookie = os.getenv('LINKEDIN_COOKIE')
        
        if li_at_cookie:
            self.logger.info("Found LI_AT_COOKIE environment variable")
            return True
        elif linkedin_cookie:
            # Set the LI_AT_COOKIE from LINKEDIN_COOKIE
            os.environ['LI_AT_COOKIE'] = linkedin_cookie
            self.logger.info("Using LINKEDIN_COOKIE as LI_AT_COOKIE")
            return True
        
        # Check config
        if self.config.get('cookie'):
            os.environ['LI_AT_COOKIE'] = self.config['cookie']
            self.logger.info("Using cookie from configuration")
            return True
        
        self.logger.warning("No LinkedIn authentication found. Scraper will run in anonymous mode (may have limited functionality).")
        return True  # Allow anonymous mode but warn user
    
    def on_data(self, data: EventData):
        """Handle scraped job data"""
        job_id = getattr(data, 'job_id', '').strip()
        
        # Skip if job already exists
        if job_id and job_id in self.existing_job_ids:
            self.logger.info(f"Skipping duplicate job ID: {job_id} - {getattr(data, 'title', 'Unknown Title')}")
            return
        
        job_data = {
            'job_id': job_id,
            'title': getattr(data, 'title', ''),
            'company': getattr(data, 'company', ''),
            'company_link': getattr(data, 'company_link', ''),
            'company_img_link': getattr(data, 'company_img_link', ''),
            'place': getattr(data, 'place', ''),
            'description': getattr(data, 'description', ''),
            'description_html': getattr(data, 'description_html', ''),
            'date': getattr(data, 'date', ''),
            'date_text': getattr(data, 'date_text', ''),
            'link': getattr(data, 'link', ''),
            'apply_link': getattr(data, 'apply_link', ''),
            'insights': str(getattr(data, 'insights', [])),
            'scraped_at': datetime.now().isoformat()
        }
        
        # Add to jobs data and existing IDs set
        self.jobs_data.append(job_data)
        if job_id:
            self.existing_job_ids.add(job_id)
        
        self.logger.info(f"Scraped new job: {job_data['title']} at {job_data['company']} (ID: {job_id})")
    
    def on_metrics(self, metrics: EventMetrics):
        """Handle scraping metrics"""
        self.logger.info(f"Metrics: {str(metrics)}")
    
    def on_error(self, error):
        """Handle scraping errors"""
        self.logger.error(f"Scraping error: {error}")
        
        # Check for specific error types and provide suggestions
        error_str = str(error)
        if "Cannot read properties of undefined" in error_str:
            self.logger.error("DOM element not found - LinkedIn may have changed their page structure")
        elif "JavascriptException" in error_str:
            self.logger.error("JavaScript execution failed - check if LinkedIn page loaded correctly")
        elif "TimeoutException" in error_str:
            self.logger.error("Page load timeout - try increasing page_load_timeout or check internet connection")
        elif "WebDriverException" in error_str:
            self.logger.error("WebDriver error - check Chrome installation and options")
    
    def on_end(self):
        """Handle scraping completion"""
        self.logger.info("Scraping completed")
    
    def save_to_csv(self):
        """Save scraped jobs to CSV file"""
        if not self.jobs_data:
            self.logger.warning("No new jobs data to save")
            return
        
        file_exists = os.path.exists(self.output_file)
        
        try:
            with open(self.output_file, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'job_id', 'title', 'company', 'company_link', 'company_img_link',
                    'place', 'description', 'description_html', 'date', 'date_text',
                    'link', 'apply_link', 'insights', 'scraped_at'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # Write header only if file is new
                if not file_exists:
                    writer.writeheader()
                
                # Write job data (only new jobs that weren't duplicates)
                for job in self.jobs_data:
                    writer.writerow(job)
                
                self.logger.info(f"Saved {len(self.jobs_data)} new jobs to {self.output_file}")
                
        except Exception as e:
            self.logger.error(f"Error saving to CSV: {e}")
    
    def create_queries(self) -> List[Query]:
        """Create search queries from config"""
        queries = []
        
        for query_config in self.config['search_queries']:
            query = Query(
                query=query_config.get('query', ''),
                options=QueryOptions(
                    locations=query_config.get('locations', ['United States']),
                    apply_link=query_config.get('apply_link', True),
                    skip_promoted_jobs=query_config.get('skip_promoted_jobs', True),
                    limit=query_config.get('limit', 50),
                    filters=QueryFilters(
                        relevance=RelevanceFilters.RECENT,
                        time=TimeFilters.WEEK,
                        type=[TypeFilters.FULL_TIME, TypeFilters.PART_TIME, TypeFilters.CONTRACT],
                        experience=[ExperienceLevelFilters.ENTRY_LEVEL],
                        on_site_or_remote=[OnSiteOrRemoteFilters.ON_SITE, OnSiteOrRemoteFilters.REMOTE, OnSiteOrRemoteFilters.HYBRID]
                    )
                )
            )
            queries.append(query)
        
        return queries
    
    def test_scraper_setup(self):
        """Test the scraper setup before running full scrape"""
        self.logger.info("Testing scraper setup...")
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            
            chrome_options = ChromeOptions()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # Test Chrome driver
            driver = webdriver.Chrome(options=chrome_options)
            driver.get("https://www.google.com")
            title = driver.title
            driver.quit()
            
            self.logger.info(f"Chrome driver test successful - loaded page: {title}")
            return True
            
        except Exception as e:
            self.logger.error(f"Chrome driver test failed: {e}")
            return False

    def run_scraper(self):
        """Run the LinkedIn job scraper"""
        self.logger.info("Starting LinkedIn job scraper...")
        
        # Test scraper setup first
        if not self.test_scraper_setup():
            self.logger.error("Scraper setup test failed. Please check Chrome installation.")
            return False
        
        # Check authentication
        if not self.check_authentication():
            self.logger.error("Authentication setup failed.")
            return False
        
        # Clear previous job data
        self.jobs_data = []
        
        # Create scraper instance with GitHub Actions compatible settings
        scraper_settings = self.config['scraper_settings']
        
        # Add Chrome options for headless environment
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        chrome_options = ChromeOptions()
        
        if scraper_settings['headless'] or os.getenv('GITHUB_ACTIONS'):
            chrome_options.add_argument('--headless')
            
        # Essential Chrome options for stability
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # DO NOT disable JavaScript - LinkedIn needs it!
        # chrome_options.add_argument('--disable-javascript')  # REMOVED
        
        # Modern user agent
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Add experimental options to avoid detection
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.logger.info("Using optimized Chrome options")
        
        scraper = LinkedinScraper(
            chrome_executable_path=None,
            chrome_binary_location=None,
            chrome_options=chrome_options,
            headless=scraper_settings['headless'],
            max_workers=1,  # Use single worker for stability
            slow_mo=2.0,    # Increase delay between actions
            page_load_timeout=60  # Increase timeout
        )
        
        # Add event listeners
        scraper.on(Events.DATA, lambda data: self.on_data(data))
        scraper.on(Events.ERROR, lambda error: self.on_error(error))
        scraper.on(Events.END, lambda: self.on_end())
        scraper.on(Events.METRICS, lambda metrics: self.on_metrics(metrics))
        
        # Create queries
        queries = self.create_queries()
        
        try:
            # Run scraper
            self.logger.info(f"Running {len(queries)} search queries...")
            scraper.run(queries)
            
            # Save results
            self.save_to_csv()
            
            self.logger.info("Scraping session completed successfully!")
            return True
            
        except Exception as e:
            self.logger.error(f"Scraping failed: {e}")
            return False

def main():
    """Main function"""
    scraper = LinkedInJobsScraper()
    success = scraper.run_scraper()
    
    # Exit with appropriate code for GitHub Actions
    if not success:
        exit(1)

if __name__ == "__main__":
    main()
