"""
Stibee Email Publisher
Sends newsletters via Stibee API
"""

import requests
from typing import Dict, List
from datetime import datetime
from src.utils.logger import default_logger as logger

class StibeePublisher:
    """Publish newsletters using Stibee API"""
    
    def __init__(self, api_key: str, list_id: str):
        """
        Initialize Stibee publisher
        
        Args:
            api_key: Stibee API key
            list_id: Stibee mailing list ID
        """
        self.api_key = api_key
        self.list_id = list_id
        self.base_url = "https://api.stibee.com/v1"
        self.headers = {
            "AccessToken": api_key,
            "Content-Type": "application/json"
        }
    
    def create_campaign(
        self,
        subject: str,
        html_content: str,
        from_email: str,
        from_name: str
    ) -> Dict:
        """
        Create a new email campaign
        
        Args:
            subject: Email subject line
            html_content: HTML email content
            from_email: Sender email address
            from_name: Sender name
            
        Returns:
            Campaign creation response
        """
        try:
            url = f"{self.base_url}/lists/{self.list_id}/campaigns"
            
            payload = {
                "subject": subject,
                "content": html_content,
                "fromEmail": from_email,
                "fromName": from_name,
                "replyTo": from_email
            }
            
            logger.info(f"Creating campaign: {subject}")
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Campaign created successfully: {result.get('id')}")
            return result
            
        except Exception as e:
            logger.error(f"Error creating campaign: {str(e)}")
            raise
    
    def send_campaign(self, campaign_id: str, schedule_time: str = None) -> Dict:
        """
        Send or schedule a campaign
        
        Args:
            campaign_id: ID of the campaign to send
            schedule_time: Optional ISO format datetime to schedule sending
            
        Returns:
            Send response
        """
        try:
            url = f"{self.base_url}/campaigns/{campaign_id}/send"
            
            payload = {}
            if schedule_time:
                payload["reserveTime"] = schedule_time
                logger.info(f"Scheduling campaign {campaign_id} for {schedule_time}")
            else:
                logger.info(f"Sending campaign {campaign_id} immediately")
            
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Campaign sent successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error sending campaign: {str(e)}")
            raise
    
    def get_campaign_stats(self, campaign_id: str) -> Dict:
        """
        Get campaign statistics
        
        Args:
            campaign_id: Campaign ID
            
        Returns:
            Statistics including open rate, click rate, etc.
        """
        try:
            url = f"{self.base_url}/campaigns/{campaign_id}/stats"
            
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            stats = response.json()
            
            return {
                'campaign_id': campaign_id,
                'sent': stats.get('sent', 0),
                'opened': stats.get('opened', 0),
                'clicked': stats.get('clicked', 0),
                'open_rate': stats.get('openRate', 0),
                'click_rate': stats.get('clickRate', 0),
                'unsubscribed': stats.get('unsubscribed', 0)
            }
            
        except Exception as e:
            logger.error(f"Error fetching stats: {str(e)}")
            return {}
    
    def send_test_email(
        self,
        campaign_id: str,
        test_emails: List[str]
    ) -> Dict:
        """
        Send test email to specified addresses
        
        Args:
            campaign_id: Campaign ID
            test_emails: List of email addresses to send test to
            
        Returns:
            Test send response
        """
        try:
            url = f"{self.base_url}/campaigns/{campaign_id}/test"
            
            payload = {
                "emails": test_emails
            }
            
            logger.info(f"Sending test email to {len(test_emails)} addresses")
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            
            logger.info("Test email sent successfully")
            return response.json()
            
        except Exception as e:
            logger.error(f"Error sending test email: {str(e)}")
            raise

# Example usage
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv("config/.env")
    
    api_key = os.getenv("STIBEE_API_KEY")
    list_id = os.getenv("STIBEE_LIST_ID")
    
    if api_key and list_id:
        publisher = StibeePublisher(api_key, list_id)
        print("Stibee publisher initialized")
