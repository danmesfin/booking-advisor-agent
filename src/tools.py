"""This module defines the tools used by the agent.

Feel free to modify or add new tools to suit your specific needs.

To learn how to create a new tool, see:
- https://docs.crewai.com/concepts/tools
"""

from __future__ import annotations

import os
from typing import Optional, Any
import json

from apify import Actor
from apify_client import ApifyClient
from crewai.tools import BaseTool
from crewai.utilities.converter import ValidationError
from pydantic import BaseModel, Field, PrivateAttr
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser

from src.models import BookingProperty, BookingProperties, TravelSearchCriteria


class BookingScraperInput(BaseModel):
    """Input schema for BookingScraper tool."""

    search_criteria: TravelSearchCriteria = Field(..., description="Travel search criteria including location, price range, etc.")


class BookingScraperTool(BaseTool):
    """Tool for scraping Booking.com properties."""

    name: str = 'Booking.com Property Scraper'
    description: str = 'Tool to search and scrape accommodation listings from Booking.com based on search criteria.'
    args_schema: type[BaseModel] = BookingScraperInput

    def _run(self, search_criteria: TravelSearchCriteria) -> list[BookingProperty]:
        Actor.log.info(f'Initializing Booking.com search with criteria: {search_criteria}')
        if not (token := os.getenv('APIFY_TOKEN')):
            Actor.log.error('APIFY_TOKEN environment variable is missing!')
            raise ValueError('APIFY_TOKEN environment variable is missing!')

        apify_client = ApifyClient(token=token)
        # Validate and format search parameters
        if not search_criteria.location.strip():
            Actor.log.error('Location cannot be empty')
            raise ValueError('Location cannot be empty')

        # Ensure price range is properly formatted
        min_price = max(0, search_criteria.min_price if search_criteria.min_price is not None else 0)
        max_price = max(min_price, search_criteria.max_price if search_criteria.max_price is not None else 999999)
        
        run_input = {
            'search': search_criteria.location.strip(),
            'maxItems': min(100, max(1, search_criteria.max_results)),  # Ensure reasonable limits
            'sortBy': 'distance_from_search',
            'currency': search_criteria.currency.upper(),
            'language': search_criteria.language.lower()
        }
        
        # Format price range as "min-max" if both values are available
        if min_price is not None and max_price is not None:
            run_input['minMaxPrice'] = f"{int(min_price)}-{int(max_price)}"
        elif min_price is not None:
            run_input['minPrice'] = str(min_price)
        elif max_price is not None:
            run_input['maxPrice'] = str(max_price)
            
        # Add star rating filter if minimum rating is specified
        if search_criteria.min_rating is not None:
            # Convert float rating to integer stars (e.g., 4.0 becomes "4")
            stars = int(search_criteria.min_rating)
            if stars > 0 and stars <= 5:
                run_input['starsCountFilter'] = str(stars)

        Actor.log.info(f'Configured search parameters: {run_input}')
        Actor.log.info(f'Starting Booking.com search for: {search_criteria.location}')
        if not (run := apify_client.actor('voyager/booking-scraper').call(run_input=run_input)):
            Actor.log.error(f'Failed to search properties in {search_criteria.location}. API call returned no results.')
            raise RuntimeError(f'Failed to search properties in {search_criteria.location}')

        dataset_id = run['defaultDatasetId']
        Actor.log.info(f'Search completed. Processing dataset ID: {dataset_id}')
        dataset_items: list[dict] = (apify_client.dataset(dataset_id).list_items()).items
        Actor.log.info(f'Retrieved {len(dataset_items)} raw properties from Booking.com')

        try:
            Actor.log.info('Validating and processing property data...')
            # Transform raw data before validation
            for item in dataset_items:
                # Convert location coordinates to string address
                if isinstance(item.get('location'), dict):
                    coords = item['location']
                    item['location'] = f"{item.get('address', {}).get('full', '')} (Lat: {coords.get('lat')}, Lng: {coords.get('lng')})"
                
                # Ensure price and currency are properly set
                if item.get('price') is None:
                    item['price'] = 0.0  # Default price
                if item.get('currency') is None:
                    item['currency'] = search_criteria.currency  # Use search criteria currency as default

            properties: BookingProperties = BookingProperties.model_validate(dataset_items)
            if not properties.root:
                Actor.log.warning('No properties found in the validated response')
                return []
            
            Actor.log.info(f'Successfully validated {len(properties.root)} properties')
            Actor.log.info('Returning all properties without additional filtering...')
            
            if len(properties.root) == 0:
                Actor.log.warning('No properties found in the search results')
            return properties.root
        except ValidationError as e:
            Actor.log.error(f'Data validation error for location {search_criteria.location}: {str(e)}')
            raise RuntimeError(f'Received invalid data for location {search_criteria.location}') from e


class SearchParameterInput(BaseModel):
    """Input schema for SearchParameterExtractor tool."""
    query: str = Field(..., description="Natural language query to extract search parameters from")


class SearchParameterExtractorTool(BaseTool):
    """Tool for extracting search parameters from natural language queries using LLM."""
    
    name: str = 'Search Parameter Extractor'
    description: str = 'Extracts structured search parameters from natural language travel queries using AI'
    args_schema: type[BaseModel] = SearchParameterInput

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Initialize LLM components after parent initialization
        self._initialize_llm()

    def _initialize_llm(self) -> None:
        """Initialize LLM components."""
        self._llm: ChatOpenAI = ChatOpenAI(temperature=0)
        self._parser: PydanticOutputParser = PydanticOutputParser(pydantic_object=TravelSearchCriteria)
        
        self._prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages([
            ("system", """You are a travel search parameter extractor. Extract structured parameters from natural language queries.
            Format instructions: {format_instructions}
            
            Guidelines:
            - Location should be a proper city/place name
            - Price ranges should be in USD
            - Ratings should be between 0-5
            - Room type can include: room, suite, apartment, house, villa, etc.
            - If a parameter is not mentioned, leave it as null
            - Default max_results to 10
            - Default currency to "USD"
            - Default language to "en"
            """),
            ("human", "{query}")
        ])

    def _run(self, query: str) -> TravelSearchCriteria:
        """Extract search parameters from natural language query using LLM.
        
        Args:
            query: Natural language query string
            
        Returns:
            TravelSearchCriteria object with extracted parameters
        """
        # Format the prompt with query and format instructions
        formatted_prompt = self._prompt.format_messages(
            query=query,
            format_instructions=self._parser.get_format_instructions()
        )
        
        # Get structured output from LLM
        output = self._llm.invoke(formatted_prompt).content
        
        try:
            # Parse the LLM output into TravelSearchCriteria
            search_criteria = self._parser.parse(output)
            Actor.log.info(f"Extracted parameters: {search_criteria}")
            return search_criteria
            
        except Exception as e:
            Actor.log.error(f"Failed to parse LLM output: {str(e)}")
            # Fallback to default values if parsing fails
            return TravelSearchCriteria(
                location="",
                min_price=None,
                max_price=None,
                min_rating=None,
                room_type=None,
                max_results=10,
                currency="USD",
                language="en"
            )