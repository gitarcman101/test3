"""
Notion Manager
Manages content curation using Notion database
"""

from typing import List, Dict, Optional
from datetime import datetime
from src.utils.logger import default_logger as logger
import json
from pathlib import Path

class NotionManager:
    """Manage content in Notion database"""
    
    def __init__(self, api_key: str = None, database_id: str = None, mock_mode: bool = True):
        """
        Initialize Notion manager
        
        Args:
            api_key: Notion API key
            database_id: Notion database ID
            mock_mode: If True, use mock data instead of actual API
        """
        self.api_key = api_key
        self.database_id = database_id
        self.mock_mode = mock_mode or not (api_key and database_id)
        
        if not self.mock_mode:
            try:
                from notion_client import Client
                self.client = Client(auth=api_key)
                logger.info("Notion client initialized")
            except ImportError:
                logger.warning("notion-client not installed, using mock mode")
                self.mock_mode = True
        else:
            logger.info("Notion manager initialized in MOCK mode")
            self.mock_storage = []
    
    def add_articles(self, summaries: List[Dict]) -> List[str]:
        """
        Add article summaries to Notion database
        
        Args:
            summaries: List of summary dictionaries
            
        Returns:
            List of created page IDs
        """
        if self.mock_mode:
            return self._mock_add_articles(summaries)
        
        page_ids = []
        
        for summary in summaries:
            try:
                # Create page in Notion
                new_page = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties={
                        "Title": {
                            "title": [
                                {
                                    "text": {
                                        "content": summary['original_title']
                                    }
                                }
                            ]
                        },
                        "Source": {
                            "rich_text": [
                                {
                                    "text": {
                                        "content": summary['source']
                                    }
                                }
                            ]
                        },
                        "Category": {
                            "select": {
                                "name": summary.get('category', 'general')
                            }
                        },
                        "URL": {
                            "url": summary['original_url']
                        },
                        "Status": {
                            "select": {
                                "name": "To Review"
                            }
                        }
                    },
                    children=[
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": summary['summary']
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                )
                
                page_ids.append(new_page['id'])
                logger.info(f"Added article to Notion: {summary['original_title']}")
                
            except Exception as e:
                logger.error(f"Error adding article to Notion: {str(e)}")
        
        return page_ids
    
    def _mock_add_articles(self, summaries: List[Dict]) -> List[str]:
        """Mock version of add_articles"""
        page_ids = []
        
        for i, summary in enumerate(summaries):
            page_id = f"mock_page_{datetime.now().timestamp()}_{i}"
            
            # Store in mock storage
            self.mock_storage.append({
                'id': page_id,
                'title': summary['original_title'],
                'source': summary['source'],
                'category': summary.get('category', 'general'),
                'url': summary['original_url'],
                'summary': summary['summary'],
                'status': 'To Review',
                'created_at': datetime.now().isoformat()
            })
            
            page_ids.append(page_id)
            logger.info(f"[MOCK] Added article: {summary['original_title']}")
        
        return page_ids
    
    def get_approved_articles(self) -> List[Dict]:
        """
        Get articles marked as approved for newsletter
        
        Returns:
            List of approved article dictionaries
        """
        if self.mock_mode:
            return self._mock_get_approved_articles()
        
        try:
            # Query Notion database for approved articles
            response = self.client.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "Status",
                    "select": {
                        "equals": "Approved"
                    }
                }
            )
            
            articles = []
            for page in response['results']:
                articles.append(self._parse_notion_page(page))
            
            logger.info(f"Retrieved {len(articles)} approved articles from Notion")
            return articles
            
        except Exception as e:
            logger.error(f"Error querying Notion: {str(e)}")
            return []
    
    def _mock_get_approved_articles(self) -> List[Dict]:
        """Mock version of get_approved_articles"""
        # In mock mode, return all articles as "approved"
        logger.info(f"[MOCK] Retrieved {len(self.mock_storage)} approved articles")
        return self.mock_storage
    
    def export_to_file(self, filepath: str) -> str:
        """
        Export mock storage to JSON file
        
        Args:
            filepath: Path to save JSON file
            
        Returns:
            Path to saved file
        """
        if not self.mock_mode:
            logger.warning("Export only available in mock mode")
            return ""
        
        try:
            output_path = Path(filepath)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.mock_storage, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Exported {len(self.mock_storage)} articles to: {output_path}")
            return str(output_path.absolute())
            
        except Exception as e:
            logger.error(f"Error exporting data: {str(e)}")
            return ""
    
    def _parse_notion_page(self, page: Dict) -> Dict:
        """Parse Notion page to article dictionary"""
        properties = page['properties']
        
        return {
            'id': page['id'],
            'title': properties['Title']['title'][0]['text']['content'],
            'source': properties['Source']['rich_text'][0]['text']['content'],
            'category': properties['Category']['select']['name'],
            'url': properties['URL']['url'],
            'status': properties['Status']['select']['name'],
        }

# Example usage
if __name__ == "__main__":
    from src.utils.mock_data import MockDataGenerator
    
    # Create mock manager
    manager = NotionManager(mock_mode=True)
    
    # Generate mock summaries
    articles = MockDataGenerator.generate_articles(3)
    summaries = MockDataGenerator.generate_summaries(articles)
    
    # Add to Notion (mock)
    page_ids = manager.add_articles(summaries)
    print(f"Created {len(page_ids)} pages")
    
    # Get approved articles
    approved = manager.get_approved_articles()
    print(f"Retrieved {len(approved)} approved articles")
    
    # Export to file
    filepath = manager.export_to_file("data/notion_export.json")
    print(f"Exported to: {filepath}")
