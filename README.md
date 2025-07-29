# Autonomous Browser Search Bot

## Overview
The **Autonomous Browser Search Bot** is a Streamlit-based web application designed to perform automated web searches, scrape content, and generate AI-powered summaries of search results. It leverages browser automation with Playwright, web scraping with BeautifulSoup, and AI summarization using OpenAI's API. The application supports both Google and DuckDuckGo search engines, with fallback mechanisms to ensure robust performance even when primary search methods fail.

This tool is ideal for users who need to quickly gather and summarize information from the web, with a user-friendly interface that includes real-time activity logging, live browser screenshots, and exportable results in JSON and text formats.

## Features
- **Multi-Engine Search**: Supports searching via DuckDuckGo (recommended due to fewer bot restrictions) and Google, with an AI-only fallback mode when web scraping is unavailable.
- **Browser Automation**: Uses Playwright to simulate browser interactions, including handling cookie consents and navigating search result pages.
- **Web Scraping**: Extracts relevant content from search results using BeautifulSoup, with robust error handling and content cleaning.
- **AI Summarization**: Generates concise, informative summaries of search results using OpenAI's GPT-4o-mini model.
- **Real-Time Feedback**: Displays live browser screenshots and a detailed activity log to track the bot's progress.
- **Customizable Settings**: Allows users to configure the number of results to scrape (1-10) and choose the search engine.
- **Export Options**: Results can be exported as JSON or a plain text report for further analysis.
- **Responsive UI**: Built with Streamlit, featuring a modern interface with custom CSS for enhanced usability.

## Prerequisites
To run the Autonomous Browser Search Bot, ensure you have the following:

- **Python**: Version 3.8 or higher.
- **OpenAI API Key**: Required for AI-powered summarization. Obtain one from [OpenAI](https://openai.com).
- **Dependencies**: Install required Python packages listed in `requirements.txt` (see Installation section).
- **Playwright Browsers**: Install Playwright's browser binaries (handled automatically during setup).

## Installation
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/sakshamagarwalm2/BrowserAgent
   cd autonomous-browser-search-bot
   ```

2. **Create a Virtual Environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   Create a `requirements.txt` file with the following content:
   ```
   streamlit==1.31.0
   playwright==1.41.0
   requests==2.31.0
   beautifulsoup4==4.12.2
   openai==1.10.0
   pillow==10.2.0
   ```

   Then install:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright Browsers**:
   ```bash
   playwright install
   ```

5. **Set Up Environment** (optional):
   You can set the `OPENAI_API_KEY` environment variable to avoid entering it manually:
   ```bash
   export OPENAI_API_KEY='your-api-key'  # On Windows: set OPENAI_API_KEY=your-api-key
   ```

## Usage
1. **Run the Application**:
   ```bash
   streamlit run app.py
   ```
   This will launch the Streamlit app in your default web browser (typically at `http://localhost:8501`).

2. **Configure the App**:
   - In the sidebar, enter your OpenAI API key to enable AI summarization.
   - Select the search engine (DuckDuckGo recommended) and set the maximum number of results to scrape (1-10).
   - Optionally, choose a test query from the provided list to quickly try the app.

3. **Perform a Search**:
   - Enter a search query in the main interface (e.g., "latest AI developments in healthcare").
   - Click **Start Search** to begin the process.
   - Monitor the real-time activity log and live browser screenshot for progress updates.

4. **View and Export Results**:
   - The app displays an AI-generated summary, scraped content previews, and full search results.
   - Use the **Download Results as JSON** or **Download as Text Report** buttons to export the data.

5. **Clear Results**:
   - Click **Clear Results** to reset the app and start a new search.

## File Structure
```
autonomous-browser-search-bot/
├── app.py                  # Main Streamlit application
├── requirements.txt        # Python dependencies
├── README.md              # This documentation file
└── venv/                  # Virtual environment (optional)
```

## Code Structure
The application is implemented in `app.py` and organized as follows:
- **Streamlit Configuration**: Sets up the page layout, custom CSS, and session state.
- **StreamlitBrowserSearchBot Class**:
  - Manages search operations, web scraping, and AI summarization.
  - Includes methods for Google and DuckDuckGo searches, content scraping, screenshot capture, and summary generation.
  - Implements fallback strategies (DuckDuckGo → API-based fallback → AI-only response).
- **Activity Logging**: Tracks operations in real-time using a queue-based system.
- **UI Components**:
  - Sidebar for configuration (API key, search settings, test queries).
  - Main interface for search input, status indicators, and results display.
  - Live browser view for screenshots and activity log for debugging.
- **Error Handling**: Robust handling of network errors, CAPTCHAs, and scraping failures.

## Key Features Explained
- **Search Engine Options**:
  - **DuckDuckGo**: Preferred due to fewer bot restrictions and CAPTCHA challenges.
  - **Google**: May be blocked by CAPTCHAs but included for compatibility.
  - **AI-Only**: Generates responses using OpenAI's model without web scraping, useful as a fallback.

- **Fallback Mechanism**:
  - If Google search fails (e.g., due to CAPTCHA), the app switches to DuckDuckGo.
  - If DuckDuckGo fails, it uses a simple API-based fallback with predefined results.
  - If all else fails, it generates an AI-only response with a disclaimer.

- **Web Scraping**:
  - Uses BeautifulSoup to extract clean text from webpages, removing scripts, styles, and irrelevant elements.
  - Limits scraped content to 2000 characters to avoid performance issues.

- **AI Summarization**:
  - Uses OpenAI's GPT-4o-mini model for cost-effective, high-quality summaries.
  - Summarizes up to 800 characters per result to provide comprehensive insights.

- **Live Feedback**:
  - Displays browser screenshots during search to show progress.
  - Logs all actions (e.g., browser navigation, scraping, errors) in real-time.

## Limitations
- **Google Search**: Frequently blocked by CAPTCHAs or "unusual traffic" detection, making DuckDuckGo the preferred choice.
- **Rate Limits**: OpenAI API usage may be subject to rate limits depending on your plan.
- **Scraping Accuracy**: Some websites may block scraping or have complex structures that prevent complete content extraction.
- **Browser Performance**: Headless browser automation can be resource-intensive on low-end systems.
- **AI-Only Mode**: Responses may lack the latest information since they rely solely on the model's training data.

## Troubleshooting
- **OpenAI API Key Error**:
  - Ensure your API key is valid and has sufficient credits.
  - Check for typos when entering the key.
- **CAPTCHA Blocks**:
  - Switch to DuckDuckGo as the search engine.
  - Consider reducing the number of results to scrape.
- **No Results Returned**:
  - Verify your internet connection.
  - Try a different query or use the AI-only mode.
- **Browser Crashes**:
  - Ensure Playwright browsers are installed (`playwright install`).
  - Check system resources (RAM, CPU) during operation.
- **Scraping Failures**:
  - Some websites may block automated requests. The app will skip these and log the issue.

## Future Improvements
- Add support for additional search engines (e.g., Bing).
- Implement proxy rotation to bypass CAPTCHA restrictions.
- Enhance scraping with JavaScript rendering for dynamic content.
- Add caching for frequently searched queries to improve performance.
- Support for multilingual searches and non-Latin character handling.

## Contributing
Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a new branch (`git checkout -b feature/your-feature`).
3. Make your changes and commit (`git commit -m 'Add your feature'`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a pull request.

## License
This project is licensed under the MIT License. See the `LICENSE` file for details.

## Contact
For questions or feedback, please open an issue on the repository or contact the maintainer at [sakshamagarwalm2@gmail.com].