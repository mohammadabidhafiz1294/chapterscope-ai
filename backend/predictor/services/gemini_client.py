"""Gemini Pro API client for topic extraction and text analysis."""

import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class TopicResult:
    """Result of topic extraction."""
    name: str
    description: str
    confidence: float
    category: str
    keywords: List[str]


@dataclass
class GeminiResponse:
    """Response from Gemini API."""
    success: bool
    content: str
    topics: List[TopicResult]
    processing_time: float
    error: Optional[str] = None


class GeminiClient:
    """Client for interacting with Google Gemini Pro API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini client.

        The API key is validated lazily so services that merely construct a
        client can still be imported and unit-tested without credentials.
        """
        self.api_key = (api_key or getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not configured; AI requests will fail")

        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-pro"
        self.max_retries = 3
        self.retry_delay = 1.0

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 1 second between requests

        logger.info("GeminiClient initialized")

    def _wait_for_rate_limit(self):
        """Wait to respect rate limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last
            time.sleep(wait_time)

        self.last_request_time = time.time()

    def _make_request(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Make a request to Gemini API."""
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured")

        self._wait_for_rate_limit()

        url = f"{self.base_url}/models/{self.model}:generateContent"
        params = {'key': self.api_key}

        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": max_tokens,
            }
        }

        headers = {
            'Content-Type': 'application/json'
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, params=params, json=payload, headers=headers, timeout=30)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:  # Rate limit
                    if attempt < self.max_retries - 1:
                        wait_time = (attempt + 1) * self.retry_delay
                        logger.warning(f"Rate limit hit, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Rate limit exceeded after {self.max_retries} attempts")
                else:
                    raise Exception(f"API request failed with status {response.status_code}: {response.text}")

            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * self.retry_delay
                    logger.warning(f"Request failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Request failed after {self.max_retries} attempts: {e}")

        raise Exception("Max retries exceeded")

    def extract_topics(self, text: str, max_topics: int = 10) -> GeminiResponse:
        """
        Extract topics from exam paper text using Gemini Pro.

        Args:
            text: The exam paper text to analyze
            max_topics: Maximum number of topics to extract

        Returns:
            GeminiResponse with extracted topics
        """
        start_time = time.time()

        try:
            prompt = f"""
            Analyze the following exam paper text and extract the main academic topics.
            Return a JSON object with the following structure:
            {{
                "topics": [
                    {{
                        "name": "Topic Name",
                        "description": "Brief description of the topic",
                        "confidence": 0.95,
                        "category": "Academic Category",
                        "keywords": ["keyword1", "keyword2", "keyword3"]
                    }}
                ]
            }}

            Guidelines:
            - Extract {max_topics} most important topics
            - Focus on core academic subjects and concepts
            - Provide confidence scores between 0.0 and 1.0
            - Categorize topics appropriately (e.g., "Mathematics", "Computer Science", "Physics")
            - Include relevant keywords for each topic
            - Only return valid JSON

            Syllabus Text:
            {text[:4000]}  # Limit text length for API
            """

            response = self._make_request(prompt, max_tokens=2000)

            # Parse the response
            if 'candidates' in response and response['candidates']:
                content = response['candidates'][0]['content']['parts'][0]['text']

                # Try to extract JSON from the response
                try:
                    # Find JSON in the response (it might be wrapped in text)
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1

                    if json_start != -1 and json_end > json_start:
                        json_content = content[json_start:json_end]
                        parsed_data = json.loads(json_content)

                        topics = []
                        for topic_data in parsed_data.get('topics', []):
                            topic = TopicResult(
                                name=topic_data.get('name', 'Unknown'),
                                description=topic_data.get('description', ''),
                                confidence=float(topic_data.get('confidence', 0.5)),
                                category=topic_data.get('category', 'General'),
                                keywords=topic_data.get('keywords', [])
                            )
                            topics.append(topic)

                        processing_time = time.time() - start_time
                        logger.info(f"Successfully extracted {len(topics)} topics in {processing_time:.2f}s")

                        return GeminiResponse(
                            success=True,
                            content=content,
                            topics=topics,
                            processing_time=processing_time
                        )
                    else:
                        raise ValueError("No JSON found in response")

                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.error(f"Failed to parse Gemini response: {e}")
                    return GeminiResponse(
                        success=False,
                        content=content,
                        topics=[],
                        processing_time=time.time() - start_time,
                        error=f"Failed to parse response: {e}"
                    )
            else:
                return GeminiResponse(
                    success=False,
                    content="",
                    topics=[],
                    processing_time=time.time() - start_time,
                    error="No candidates in response"
                )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error extracting topics: {e}")
            return GeminiResponse(
                success=False,
                content="",
                topics=[],
                processing_time=processing_time,
                error=str(e)
            )

    def analyze_text_complexity(self, text: str) -> Dict[str, Any]:
        """Analyze the complexity of syllabus text."""
        try:
            prompt = f"""
            Analyze the complexity of the following academic text and return a JSON object:
            {{
                "complexity_score": 0.75,
                "reading_level": "Undergraduate",
                "technical_terms_count": 25,
                "estimated_study_hours": 40,
                "prerequisites": ["Basic Mathematics", "Programming Fundamentals"]
            }}

            Text to analyze:
            {text[:2000]}
            """

            response = self._make_request(prompt, max_tokens=500)

            if 'candidates' in response and response['candidates']:
                content = response['candidates'][0]['content']['parts'][0]['text']

                # Try to extract JSON
                json_start = content.find('{')
                json_end = content.rfind('}') + 1

                if json_start != -1 and json_end > json_start:
                    json_content = content[json_start:json_end]
                    return json.loads(json_content)

            return {
                "complexity_score": 0.5,
                "reading_level": "Unknown",
                "technical_terms_count": 0,
                "estimated_study_hours": 0,
                "prerequisites": []
            }

        except Exception as e:
            logger.error(f"Error analyzing text complexity: {e}")
            return {
                "complexity_score": 0.5,
                "reading_level": "Unknown",
                "technical_terms_count": 0,
                "estimated_study_hours": 0,
                "prerequisites": []
            }

    def generate_json(
        self, prompt: str, max_tokens: int = 2000
    ) -> Optional[Dict[str, Any]]:
        """Generate a JSON object response from an arbitrary prompt.

        Phase 3 uses this as the LLM-assisted parsing fallback. Returns the
        parsed dict, or None on any failure (network, auth, malformed JSON).
        Never logs the API key or raw document content.
        """
        try:
            response = self._make_request(prompt, max_tokens=max_tokens)
        except Exception as exc:
            logger.error("Gemini generate_json request failed: %s", exc)
            return None

        try:
            candidates = response.get('candidates') or []
            if not candidates:
                logger.warning("Gemini generate_json returned no candidates")
                return None
            content = candidates[0]['content']['parts'][0]['text']
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("Gemini generate_json response missing content: %s", exc)
            return None

        # Robustly locate a JSON object inside the response text.
        try:
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start == -1 or json_end <= json_start:
                logger.warning("Gemini generate_json response contained no JSON object")
                return None
            return json.loads(content[json_start:json_end])
        except json.JSONDecodeError as exc:
            logger.warning("Gemini generate_json returned invalid JSON: %s", exc)
            return None
