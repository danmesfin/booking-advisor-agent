"""Main module for the Apify Actor.

This module contains the main logic for the Actor, including:
- Parameter extraction from natural language queries
- Property search using the Booking.com scraper
- Results analysis and filtering
"""

from __future__ import annotations

import json
from typing import Any

from apify import Actor
from pydantic import ValidationError

from src.models import TravelSearchCriteria
from src.tools import BookingScraperTool, SearchParameterExtractorTool


async def extract_search_parameters(query: str, currency: str = 'USD', language: str = 'en-gb', max_results: int = 10) -> TravelSearchCriteria:
    """Extract structured search parameters from a natural language query.

    Args:
        query: The natural language search query.
        currency: Currency for prices (default: USD)
        language: Language for results (default: en-gb)
        max_results: Maximum number of results to return (default: 10)

    Returns:
        TravelSearchCriteria object with the extracted search parameters.
    """
    extractor_tool = SearchParameterExtractorTool()
    extracted_params = extractor_tool._run(query)
    
    # Override with input configuration
    extracted_params.currency = currency
    extracted_params.language = language
    extracted_params.max_results = max_results
    
    return extracted_params


async def main() -> None:
    """Main entry point for the Apify Actor.

    This coroutine handles the entire workflow of processing search queries and returning results.
    """
    async with Actor:
        await Actor.charge('actor-start')
        Actor.log.info('Actor started successfully')

        # Get and validate input
        actor_input = await Actor.get_input()
        Actor.log.info('Received actor input')

        search_query = actor_input.get('searchQuery')
        if not search_query:
            msg = 'Missing "searchQuery" attribute in input!'
            Actor.log.error(msg)
            raise ValueError(msg)

        Actor.log.info(f'Processing search query: {search_query}')
        
        # Configure search parameters
        currency = actor_input.get('currency', 'USD')
        language = actor_input.get('language', 'en-gb')
        max_results = actor_input.get('maxResults', 10)
        
        Actor.log.info(f'Using configuration - Currency: {currency}, Language: {language}, Max Results: {max_results}')

        # Extract search parameters with configuration
        Actor.log.info('Extracting search parameters')
        search_criteria = await extract_search_parameters(
            search_query,
            currency=currency,
            language=language,
            max_results=max_results
        )
        Actor.log.info(f'Created search criteria: {search_criteria}')

        # Initialize and execute search
        Actor.log.info('Initializing property search')
        booking_scraper = BookingScraperTool()
        try:
            search_results = booking_scraper._run(search_criteria)
            Actor.log.info(f'Found {len(search_results)} properties')
        except Exception as e:
            msg = f'Property search failed: {str(e)}'
            Actor.log.error(msg)
            raise RuntimeError(msg)

        # Convert search results to plain objects before storing
        serialized_results = []
        for result in search_results:
            if hasattr(result, '__dict__'):
                serialized_results.append(result.__dict__)
            elif isinstance(result, dict):
                serialized_results.append(result)
            else:
                serialized_results.append(json.loads(json.dumps(result, default=lambda o: o.__dict__)))

        # Store results
        Actor.log.info(f'Storing {len(serialized_results)} results')
        await Actor.push_data(serialized_results)
        await Actor.charge('task-completed')

        Actor.log.info('Successfully processed search query and stored results!')


def calculate_match_score(property: Any, criteria: TravelSearchCriteria) -> float:
    """Calculate how well a property matches the search criteria.

    Args:
        property: The property to evaluate.
        criteria: The search criteria to match against.

    Returns:
        A score from 0-100 indicating how well the property matches the criteria.
    """
    score = 0.0
    
    # Location match (base score)
    score += 50.0
    
    # Price range match (up to 20 points)
    if criteria.min_price is not None and criteria.max_price is not None:
        if criteria.min_price <= property.price <= criteria.max_price:
            score += 20.0
        else:
            price_distance = min(
                abs(property.price - criteria.min_price),
                abs(property.price - criteria.max_price)
            )
            score += max(0, 20.0 - (price_distance / criteria.max_price) * 20.0)
    
    # Rating match (up to 15 points)
    if criteria.min_rating is not None and property.rating is not None:
        if property.rating >= criteria.min_rating:
            score += 15.0
        else:
            score += max(0, 15.0 - (criteria.min_rating - property.rating) * 5.0)
    
    # Room type match (up to 15 points)
    if criteria.room_type and property.room_type:
        if criteria.room_type.lower() in property.room_type.lower():
            score += 15.0
    
    return min(100.0, score)