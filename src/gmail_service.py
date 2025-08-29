import os.path
import json
import base64
from typing import Optional, List, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.cloud import pubsub_v1


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]


class GmailService:
    def __init__(self, credentials_file: str = "credentials.json", token_file: str = "token.json"):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self._setup_service()
    
    def _setup_service(self):
        """Set up Gmail API service with authentication."""
        creds = None
        
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())
        
        self.service = build("gmail", "v1", credentials=creds)
    
    def setup_push_notifications(self, topic_name: str, label_ids: List[str] = None) -> Dict[str, Any]:
        """Set up push notifications for Gmail using Pub/Sub."""
        if label_ids is None:
            label_ids = ["INBOX"]
        
        try:
            request = {
                'labelIds': label_ids,
                'topicName': topic_name,
                'labelFilterBehavior': 'INCLUDE'
            }
            
            result = self.service.users().watch(userId='me', body=request).execute()
            print(f"Watch setup successful. Expiration: {result.get('expiration')}")
            return result
            
        except HttpError as error:
            print(f"An error occurred setting up push notifications: {error}")
            raise
    
    def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get a specific message by ID."""
        try:
            message = self.service.users().messages().get(
                userId='me', 
                id=message_id,
                format='full'
            ).execute()
            return message
        except HttpError as error:
            print(f"An error occurred getting message {message_id}: {error}")
            raise
    
    def get_message_content(self, message_id: str) -> str:
        """Extract text content from a message."""
        message = self.get_message(message_id)
        
        def extract_text_from_payload(payload):
            """Recursively extract text from message payload."""
            text_content = []
            
            if 'parts' in payload:
                for part in payload['parts']:
                    text_content.extend(extract_text_from_payload(part))
            else:
                if payload.get('mimeType') == 'text/plain':
                    if 'data' in payload['body']:
                        data = payload['body']['data']
                        text = base64.urlsafe_b64decode(data).decode('utf-8')
                        text_content.append(text)
            
            return text_content
        
        text_parts = extract_text_from_payload(message['payload'])
        return '\n'.join(text_parts)
    
    def get_sender_email(self, message_id: str) -> str:
        """Get sender email from a message."""
        message = self.get_message(message_id)
        headers = message['payload'].get('headers', [])
        
        for header in headers:
            if header['name'].lower() == 'from':
                # Extract email from "Name <email@example.com>" format
                from_header = header['value']
                if '<' in from_header and '>' in from_header:
                    return from_header.split('<')[1].split('>')[0]
                else:
                    return from_header
        
        return ""
    
    def get_recipient_email(self, message_id: str) -> str:
        """Get recipient email from a message."""
        message = self.get_message(message_id)
        headers = message['payload'].get('headers', [])
        
        for header in headers:
            if header['name'].lower() == 'to':
                # Extract email from "Name <email@example.com>" format
                to_header = header['value']
                if '<' in to_header and '>' in to_header:
                    return to_header.split('<')[1].split('>')[0]
                else:
                    return to_header
        
        return ""
    
    def get_subject(self, message_id: str) -> str:
        """Get subject line from a message."""
        message = self.get_message(message_id)
        headers = message['payload'].get('headers', [])
        
        for header in headers:
            if header['name'].lower() == 'subject':
                return header['value']
        
        return ""
    
    def get_recent_messages(self, query: str = "", max_results: int = 10) -> List[Dict[str, Any]]:
        """Get recent messages matching query."""
        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            return messages
        except HttpError as error:
            print(f"An error occurred getting recent messages: {error}")
            raise
    
    def get_message_timestamp(self, message_id: str) -> float:
        """Get the internal date/timestamp of a message as Unix timestamp."""
        try:
            message = self.get_message(message_id)
            # Gmail stores internal date in milliseconds, convert to seconds
            internal_date_ms = int(message.get('internalDate', 0))
            return internal_date_ms / 1000.0
        except (HttpError, ValueError) as error:
            print(f"An error occurred getting message timestamp for {message_id}: {error}")
            return 0.0
    
    def get_history(self, start_history_id: str) -> List[Dict[str, Any]]:
        """Get message history since a specific history ID."""
        try:
            results = self.service.users().history().list(
                userId='me',
                startHistoryId=start_history_id
            ).execute()
            
            history = results.get('history', [])
            return history
        except HttpError as error:
            print(f"An error occurred getting history: {error}")
            raise
    
    def get_thread_id(self, message_id: str) -> str:
        """Get the thread ID for a message."""
        try:
            message = self.get_message(message_id)
            return message.get('threadId', '')
        except HttpError as error:
            print(f"An error occurred getting thread ID for {message_id}: {error}")
            return ""
    
    def send_reply_email(self, thread_id: str, to_email: str, subject: str, body: str) -> Optional[str]:
        """Send a reply email to an existing thread. Returns message ID if successful."""
        try:
            # Create message
            message = MIMEText(body)
            message['to'] = to_email
            message['subject'] = f"Re: {subject}" if not subject.startswith('Re:') else subject
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send as reply to thread
            send_message = {
                'raw': raw_message,
                'threadId': thread_id
            }
            
            result = self.service.users().messages().send(
                userId='me',
                body=send_message
            ).execute()
            
            message_id = result.get('id')
            print(f"Reply email sent successfully: {message_id}")
            return message_id
            
        except HttpError as error:
            print(f"An error occurred sending reply email: {error}")
            return None
    
    def send_email(self, to_email: str, subject: str, body: str) -> Optional[str]:
        """Send a standalone email. Returns message ID if successful."""
        try:
            # Create message
            message = MIMEText(body)
            message['to'] = to_email
            message['subject'] = subject
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send message
            send_message = {'raw': raw_message}
            
            result = self.service.users().messages().send(
                userId='me',
                body=send_message
            ).execute()
            
            message_id = result.get('id')
            print(f"Email sent successfully: {message_id}")
            return message_id
            
        except HttpError as error:
            print(f"An error occurred sending email: {error}")
            return None