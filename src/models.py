"""This module defines Pydantic models for this project.

These models are used mainly for the structured tool and LLM outputs.
Resources:
- https://docs.pydantic.dev/latest/concepts/models/
"""

from __future__ import annotations

from pydantic import BaseModel, Field, RootModel


class CategoryReview(BaseModel):
    """Model for category-specific review scores."""

    title: str = Field(..., description='Category title (e.g., Staff, Cleanliness)')
    score: float = Field(..., description='Score for this category')


class PropertyAddress(BaseModel):
    """Model for property address details."""

    full: str = Field(..., description='Full address')
    postal_code: str | None = Field(None, description='Postal code', alias='postalCode')
    street: str | None = Field(None, description='Street address')
    country: str | None = Field(None, description='Country')
    region: str | None = Field(None, description='Region/State')


class BookingProperty(BaseModel):
    """Booking.com Property Pydantic model."""

    name: str = Field(..., description='The name of the property')
    url: str = Field(..., description='The booking URL of the property')
    description: str | None = Field(None, description='Detailed description of the property')
    address: PropertyAddress | None = Field(None, description='Property address details')
    location: str = Field(..., description='Location of the property')
    rating: float | None = Field(None, description='Overall property rating')
    reviews: int | None = Field(None, description='Number of reviews')
    category_reviews: list[CategoryReview] | None = Field(None, description='Category-specific review scores', alias='categoryReviews')
    price: float = Field(..., description='Price per night')
    currency: str = Field(..., description='Currency of the price')
    room_type: str | None = Field(None, description='Type of room/accommodation')
    stars: int | None = Field(None, description='Hotel star rating if applicable')
    amenities: list[str] | None = Field(None, description='List of available amenities')
    distance_from_center: str | None = Field(None, description='Distance from city center', alias='distanceFromCenter')
    check_in: str | None = Field(None, description='Check-in information', alias='checkIn')
    check_out: str | None = Field(None, description='Check-out information', alias='checkOut')
    image: str | None = Field(None, description='Main property image URL')
    images: list[str] | None = Field(None, description='Additional property image URLs')


class BookingProperties(RootModel):
    """Root model for list of BookingProperties."""

    root: list[BookingProperty]


class TravelSearchCriteria(BaseModel):
    """Model for parsed travel search criteria."""

    location: str = Field(..., description='Destination location')
    rooms: int = Field(default=1, description='Number of rooms required')
    min_price: float | None = Field(None, description='Minimum price per night')
    max_price: float | None = Field(None, description='Maximum price per night')
    min_rating: float | None = Field(None, description='Minimum rating required (e.g., 4.0)')
    currency: str = Field(default='USD', description='Currency for prices')
    language: str = Field(default='en-gb', description='Language for results')
    max_results: int = Field(default=10, description='Maximum number of results to return')