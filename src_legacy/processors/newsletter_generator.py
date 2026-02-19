"""
Newsletter Generator
Generates HTML newsletters from content data using templates
"""

from jinja2 import Environment, FileSystemLoader, Template
from pathlib import Path
from typing import Dict, List
from datetime import datetime
from src.utils.logger import default_logger as logger

class NewsletterGenerator:
    """Generate HTML newsletters from templates"""
    
    def __init__(self, template_dir: str = "templates"):
        """
        Initialize newsletter generator
        
        Args:
            template_dir: Directory containing Jinja2 templates
        """
        self.template_dir = Path(template_dir)
        self.env = Environment(loader=FileSystemLoader(str(self.template_dir)))
    
    def generate_html(
        self,
        newsletter_data: Dict,
        template_name: str = "newsletter_template.html"
    ) -> str:
        """
        Generate HTML newsletter from data
        
        Args:
            newsletter_data: Dictionary with newsletter content
            template_name: Name of the template file
            
        Returns:
            HTML string
        """
        try:
            logger.info(f"Generating newsletter HTML using template: {template_name}")
            
            # Load template
            template = self.env.get_template(template_name)
            
            # Render template with data
            html = template.render(**newsletter_data)
            
            logger.info("Newsletter HTML generated successfully")
            return html
            
        except Exception as e:
            logger.error(f"Error generating newsletter HTML: {str(e)}")
            raise
    
    def save_html(self, html: str, output_path: str) -> str:
        """
        Save HTML to file
        
        Args:
            html: HTML content
            output_path: Path to save file
            
        Returns:
            Absolute path to saved file
        """
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            
            logger.info(f"Newsletter saved to: {output_file}")
            return str(output_file.absolute())
            
        except Exception as e:
            logger.error(f"Error saving newsletter: {str(e)}")
            raise
    
    def generate_subject_line(self, main_issue_title: str, week_number: int = None) -> str:
        """
        Generate email subject line
        
        Args:
            main_issue_title: Main issue title
            week_number: Optional week number
            
        Returns:
            Subject line string
        """
        if week_number:
            return f"[DETA Week {week_number}] {main_issue_title}"
        else:
            # Use current week number
            week = datetime.now().isocalendar()[1]
            return f"[DETA Week {week}] {main_issue_title}"
    
    def generate_preview_text(self, main_issue_content: str, max_length: int = 100) -> str:
        """
        Generate email preview text (preheader)
        
        Args:
            main_issue_content: Main issue content
            max_length: Maximum length of preview text
            
        Returns:
            Preview text string
        """
        # Extract first sentence or first N characters
        preview = main_issue_content.strip().split('\n')[0]
        
        if len(preview) > max_length:
            preview = preview[:max_length-3] + "..."
        
        return preview

# Example usage
if __name__ == "__main__":
    from src.utils.mock_data import MockDataGenerator
    
    # Generate mock data
    newsletter_data = MockDataGenerator.generate_newsletter_data()
    
    # Create generator
    generator = NewsletterGenerator()
    
    # Generate HTML
    html = generator.generate_html(newsletter_data)
    
    # Generate subject line
    subject = generator.generate_subject_line(newsletter_data['main_issue_title'])
    print(f"Subject: {subject}")
    
    # Save to file
    output_path = "data/test_newsletter.html"
    saved_path = generator.save_html(html, output_path)
    print(f"Saved to: {saved_path}")
