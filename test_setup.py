#!/usr/bin/env python3
"""
Test script to verify the LinkedIn scraper setup
"""

import logging
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_setup')

def test_chrome_driver():
    """Test Chrome WebDriver setup"""
    logger.info("Testing Chrome WebDriver...")
    
    try:
        chrome_options = ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://www.google.com")
        title = driver.title
        logger.info(f"✓ Chrome driver working - Page title: {title}")
        driver.quit()
        return True
        
    except Exception as e:
        logger.error(f"✗ Chrome driver test failed: {e}")
        return False

def test_linkedin_access():
    """Test basic LinkedIn access"""
    logger.info("Testing LinkedIn access...")
    
    try:
        chrome_options = ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://www.linkedin.com")
        
        # Check if page loads
        if "LinkedIn" in driver.title:
            logger.info("✓ LinkedIn page accessible")
            result = True
        else:
            logger.error(f"✗ Unexpected page title: {driver.title}")
            result = False
            
        driver.quit()
        return result
        
    except Exception as e:
        logger.error(f"✗ LinkedIn access test failed: {e}")
        return False

def test_linkedin_scraper_import():
    """Test linkedin-jobs-scraper import"""
    logger.info("Testing linkedin-jobs-scraper import...")
    
    try:
        from linkedin_jobs_scraper import LinkedinScraper
        from linkedin_jobs_scraper.events import Events, EventData
        from linkedin_jobs_scraper.query import Query, QueryOptions
        logger.info("✓ linkedin-jobs-scraper imported successfully")
        return True
        
    except ImportError as e:
        logger.error(f"✗ Failed to import linkedin-jobs-scraper: {e}")
        logger.error("Try: pip install linkedin-jobs-scraper")
        return False

def main():
    """Run all tests"""
    logger.info("Starting setup validation tests...")
    
    tests = [
        ("LinkedIn Scraper Import", test_linkedin_scraper_import),
        ("Chrome WebDriver", test_chrome_driver),
        ("LinkedIn Access", test_linkedin_access),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n--- Running {test_name} Test ---")
        success = test_func()
        results.append((test_name, success))
    
    # Summary
    logger.info("\n--- Test Results Summary ---")
    all_passed = True
    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"{test_name}: {status}")
        if not success:
            all_passed = False
    
    if all_passed:
        logger.info("\n🎉 All tests passed! Your setup should work.")
    else:
        logger.error("\n❌ Some tests failed. Please fix the issues before running the scraper.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
