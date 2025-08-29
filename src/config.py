import os
from typing import List, Optional


class Config:
    """Configuration settings for the text-claude application."""
    
    def __init__(self):
        # Gmail settings
        self.gmail_credentials_file = os.getenv('GMAIL_CREDENTIALS_FILE', 'credentials.json')
        self.gmail_token_file = os.getenv('GMAIL_TOKEN_FILE', 'token.json')
        
        # Google Cloud settings
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT_ID', 'emailmyself-470502')
        self.pubsub_topic_name = os.getenv('PUBSUB_TOPIC_NAME', f'projects/{self.project_id}/topics/gmail-notifications')
        self.pubsub_subscription_name = os.getenv('PUBSUB_SUBSCRIPTION_NAME', 'gmail-notifications-sub')
        
        # Claude settings
        self.claude_working_directory = os.getenv('CLAUDE_WORKING_DIRECTORY', '/Users/jonathanli/code')
        
        # Email filtering settings
        self.target_email = 'jonathanmingli@gmail.com'
        self.required_subject = 'CLAUDE'
        
        # Server settings
        self.webhook_port = int(os.getenv('WEBHOOK_PORT', '5000'))
        self.webhook_host = os.getenv('WEBHOOK_HOST', '0.0.0.0')
        
        # Notification mode: 'pubsub' or 'webhook'
        self.notification_mode = os.getenv('NOTIFICATION_MODE', 'pubsub')
        
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if not os.path.exists(self.gmail_credentials_file):
            errors.append(f"Gmail credentials file not found: {self.gmail_credentials_file}")
        
        
        if not self.project_id:
            errors.append("Google Cloud Project ID not set")
        
        
        return errors
    
    def print_config(self):
        """Print current configuration (excluding sensitive data)."""
        print("=== Text-Claude Configuration ===")
        print(f"Gmail Credentials File: {self.gmail_credentials_file}")
        print(f"Gmail Token File: {self.gmail_token_file}")
        print(f"Google Cloud Project ID: {self.project_id}")
        print(f"Pub/Sub Topic: {self.pubsub_topic_name}")
        print(f"Pub/Sub Subscription: {self.pubsub_subscription_name}")
        print(f"Claude Working Directory: {self.claude_working_directory}")
        print(f"Target Email: {self.target_email}")
        print(f"Required Subject: {self.required_subject}")
        print(f"Webhook Host: {self.webhook_host}")
        print(f"Webhook Port: {self.webhook_port}")
        print(f"Notification Mode: {self.notification_mode}")
        print("=" * 35)