import json
import base64
import binascii
import time
import ssl
from typing import Dict, Any, Callable, Optional
from flask import Flask, request, jsonify
from google.cloud import pubsub_v1
from concurrent.futures import ThreadPoolExecutor
import threading
from googleapiclient.errors import HttpError


class NotificationHandler:
    def __init__(self, 
                 gmail_service,
                 claude_service, 
                 project_id: str,
                 subscription_name: str):
        self.gmail_service = gmail_service
        self.claude_service = claude_service
        self.project_id = project_id
        self.subscription_name = subscription_name
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(
            project_id, subscription_name
        )
        self.executor = ThreadPoolExecutor(max_workers=4)
        # Track processed messages to prevent duplicates
        self.processed_messages = set()
        self.processed_messages_lock = threading.Lock()
        # Track processed history IDs to prevent duplicate notifications
        self.processed_history_ids = set()
        self.processed_history_ids_lock = threading.Lock()
        # Keep track of when we last cleaned up processed messages
        self.last_cleanup_time = time.time()
        # Track server start time to filter out old events
        self.server_start_time = time.time()
        # Track emails we've sent to prevent processing our own replies
        self.sent_message_ids = set()
        self.sent_message_ids_lock = threading.Lock()
    
    def decode_notification_data(self, data) -> Dict[str, Any]:
        """Decode notification data from Pub/Sub."""
        try:
            # Handle both bytes and string data
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            
            # Try to parse as JSON first (data might already be decoded)
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                # If not JSON, try base64 decoding first
                # Fix padding if necessary
                missing_padding = len(data) % 4
                if missing_padding:
                    data += '=' * (4 - missing_padding)
                
                decoded_data = base64.b64decode(data)
                return json.loads(decoded_data)
                
        except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"Failed to decode notification data: {e}")
            print(f"Raw data type: {type(data)}")
            print(f"Raw data length: {len(data)}")
            if isinstance(data, bytes):
                print(f"Raw data: {data[:100]}")
            else:
                print(f"Raw data: {data[:100]}...")
            raise
    
    def retry_gmail_operation(self, operation, max_retries=3, delay=2):
        """Retry Gmail API operations with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return operation()
            except (ssl.SSLError, HttpError, ConnectionError, OSError) as e:
                if attempt == max_retries - 1:
                    print(f"Gmail API permanently failed after {max_retries} attempts: {e}")
                    return None  # Return None instead of crashing
                print(f"Gmail API error (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(delay * (2 ** attempt))  # Exponential backoff
        return None
    
    def is_system_generated_email(self, message_content: str, sender_email: str, message_id: str) -> tuple[bool, str]:
        """Check if an email is system-generated (our own replies)."""
        
        # Check if we sent this message
        with self.sent_message_ids_lock:
            if message_id in self.sent_message_ids:
                return True, "Email was sent by this system"
        
        # Check content patterns for system-generated messages
        system_patterns = [
            'ack',
            'Progress update:',
            'Task completed!',
            'Claude processing failed with error:',
            'Processing with Claude Code',
            'Claude response generated'
        ]
        
        content_lower = message_content.lower().strip()
        for pattern in system_patterns:
            if pattern.lower() in content_lower:
                return True, f"Email contains system pattern: '{pattern}'"
        
        # Check if it's a very short response (likely system-generated)
        if len(content_lower) < 10:
            return True, "Email is too short (likely system-generated)"
            
        return False, "Email appears to be user-generated"
    
    def is_valid_claude_email(self, message_id: str) -> tuple[bool, str]:
        """Check if email meets all criteria for Claude processing.
        
        Returns: (is_valid, reason)
        """
        try:
            # Get email details with retry logic
            sender = self.retry_gmail_operation(
                lambda: self.gmail_service.get_sender_email(message_id)
            )
            recipient = self.retry_gmail_operation(
                lambda: self.gmail_service.get_recipient_email(message_id)
            )
            subject = self.retry_gmail_operation(
                lambda: self.gmail_service.get_subject(message_id)
            )
            
            # Check if any operations failed
            if sender is None or recipient is None or subject is None:
                return False, "Failed to retrieve email details due to network errors"
            
            # Must be from jonathanmingli@gmail.com
            if sender.lower() != 'jonathanmingli@gmail.com':
                return False, f"Sender {sender} is not jonathanmingli@gmail.com"
            
            # Must be to jonathanmingli@gmail.com
            if recipient.lower() != 'jonathanmingli@gmail.com':
                return False, f"Recipient {recipient} is not jonathanmingli@gmail.com"
            
            # Must have subject "CLAUDE"
            if subject.upper() != 'CLAUDE':
                return False, f"Subject '{subject}' is not 'CLAUDE'"
            
            return True, "Email meets all criteria for Claude processing"
            
        except Exception as e:
            return False, f"Error checking email criteria: {e}"
    
    def cleanup_processed_messages(self):
        """Clean up old processed message IDs to prevent memory growth."""
        current_time = time.time()
        # Clean up every hour (3600 seconds)
        if current_time - self.last_cleanup_time > 3600:
            with self.processed_messages_lock:
                # Keep only the last 100 processed messages to prevent unbounded growth
                if len(self.processed_messages) > 100:
                    # Convert to list, keep last 50, convert back to set
                    messages_list = list(self.processed_messages)
                    self.processed_messages = set(messages_list[-50:])
                    print(f"Cleaned up processed messages, now tracking {len(self.processed_messages)} messages")
                    
            with self.processed_history_ids_lock:
                # Keep only the last 100 processed history IDs
                if len(self.processed_history_ids) > 100:
                    history_list = list(self.processed_history_ids)
                    self.processed_history_ids = set(history_list[-50:])
                    print(f"Cleaned up processed history IDs, now tracking {len(self.processed_history_ids)} history IDs")
            
            with self.sent_message_ids_lock:
                # Keep only the last 50 sent message IDs
                if len(self.sent_message_ids) > 50:
                    sent_list = list(self.sent_message_ids)
                    self.sent_message_ids = set(sent_list[-25:])
                    print(f"Cleaned up sent message IDs, now tracking {len(self.sent_message_ids)} sent messages")
                    
            self.last_cleanup_time = current_time
    
    def process_notification(self, notification_data: Dict[str, Any]):
        """Process a Gmail notification."""
        try:
            # Periodic cleanup of processed messages
            self.cleanup_processed_messages()
            
            email_address = notification_data.get('emailAddress')
            history_id = notification_data.get('historyId')
            
            print(f"Processing notification for {email_address}, history ID: {history_id}")
            
            # Check if we've already processed this history ID
            with self.processed_history_ids_lock:
                if history_id in self.processed_history_ids:
                    print(f"✅ Skipping already processed history ID {history_id}")
                    return
                self.processed_history_ids.add(history_id)
            
            # Get messages from history since the notification was triggered
            try:
                # Try to get history changes first (more efficient)
                history_changes = self.retry_gmail_operation(
                    lambda: self.gmail_service.get_history(history_id)
                )
                
                if history_changes:
                    # Extract message IDs from history changes
                    recent_messages = []
                    for history_item in history_changes:
                        if 'messagesAdded' in history_item:
                            for msg_added in history_item['messagesAdded']:
                                recent_messages.append({'id': msg_added['message']['id']})
                    print(f"Found {len(recent_messages)} new messages from history API")
                else:
                    print("No history changes found, falling back to unread messages query")
                    # Fallback to unread messages query
                    recent_messages = self.retry_gmail_operation(
                        lambda: self.gmail_service.get_recent_messages(
                            query="is:unread", 
                            max_results=5
                        )
                    )
            except Exception as e:
                print(f"History API failed: {e}, falling back to unread messages query")
                # Fallback to unread messages query
                recent_messages = self.retry_gmail_operation(
                    lambda: self.gmail_service.get_recent_messages(
                        query="is:unread", 
                        max_results=5
                    )
                )
            
            if recent_messages is None:
                print("Failed to retrieve recent messages due to network errors, skipping notification")
                return
            
            print(f"Found {len(recent_messages)} recent unread messages to check")
            with self.processed_messages_lock:
                print(f"Currently tracking {len(self.processed_messages)} processed messages")
            
            for i, msg in enumerate(recent_messages):
                message_id = msg['id']
                print(f"Checking message {i+1}/{len(recent_messages)}: {message_id}")
                
                # Check if we've already processed this message
                with self.processed_messages_lock:
                    if message_id in self.processed_messages:
                        print(f"✅ Skipping already processed message {message_id}")
                        continue
                
                # Check message timestamp to filter out old messages
                message_timestamp = self.retry_gmail_operation(
                    lambda: self.gmail_service.get_message_timestamp(message_id)
                )
                
                if message_timestamp and message_timestamp < self.server_start_time:
                    age_minutes = (self.server_start_time - message_timestamp) / 60
                    print(f"⏰ Skipping old message {message_id} (age: {age_minutes:.1f} minutes before server start)")
                    continue
                
                # Check if email meets all criteria for Claude processing
                is_valid, reason = self.is_valid_claude_email(message_id)
                
                if not is_valid:
                    print(f"Skipping message {message_id}: {reason}")
                    continue
                
                # Get message content to check if it's system-generated
                message_content = self.retry_gmail_operation(
                    lambda: self.gmail_service.get_message_content(message_id)
                )
                sender_email = self.retry_gmail_operation(
                    lambda: self.gmail_service.get_sender_email(message_id)
                )
                
                if message_content is None or sender_email is None:
                    print(f"Skipping message {message_id} due to network errors")
                    continue
                
                # Check if this is a system-generated email (our own reply)
                is_system, system_reason = self.is_system_generated_email(
                    message_content, sender_email, message_id
                )
                
                if is_system:
                    print(f"🤖 Skipping system-generated message {message_id}: {system_reason}")
                    continue
                
                # Get remaining details for processing
                subject = self.retry_gmail_operation(
                    lambda: self.gmail_service.get_subject(message_id)
                )
                
                if subject is None:
                    print(f"Skipping message {message_id} - could not get subject")
                    continue
                
                # Skip empty messages
                if not message_content.strip():
                    print(f"Skipping empty message {message_id}")
                    continue
                
                print(f"✅ Processing CLAUDE email from {sender_email} (Message ID: {message_id})")
                print(f"Subject: {subject}")
                print(f"Content preview: {message_content[:100]}...")
                
                # Mark as processed before starting Claude processing
                with self.processed_messages_lock:
                    self.processed_messages.add(message_id)
                
                # Get thread ID for email replies
                thread_id = self.retry_gmail_operation(
                    lambda: self.gmail_service.get_thread_id(message_id)
                )
                
                # Send acknowledgment email that processing started
                if thread_id:
                    ack_message_id = self.retry_gmail_operation(
                        lambda: self.gmail_service.send_reply_email(
                            thread_id, sender_email, subject, "ack"
                        )
                    )
                    if ack_message_id:
                        print("📧 Sent acknowledgment email")
                        # Track this as a sent message to avoid processing it
                        with self.sent_message_ids_lock:
                            self.sent_message_ids.add(ack_message_id)
                    else:
                        print("⚠️ Failed to send acknowledgment email")
                
                # Process with Claude using streaming for real-time updates
                try:
                    progress_updates = []
                    
                    def progress_callback(update_text):
                        """Called for each streaming update from Claude."""
                        print(f"🔄 Claude progress: {update_text[:100]}...")
                        progress_updates.append(update_text)
                        
                        # Send progress updates via email (limit to significant updates)
                        if thread_id and len(update_text) > 50:  # Only send substantial updates
                            if len(progress_updates) % 3 == 0:  # Send every 3rd update to avoid spam
                                progress_email = f"Progress update:\n\n{update_text}"
                                progress_message_id = self.retry_gmail_operation(
                                    lambda: self.gmail_service.send_reply_email(
                                        thread_id, sender_email, subject, progress_email
                                    )
                                )
                                if progress_message_id:
                                    print("📧 Sent progress update email")
                                    # Track this as a sent message
                                    with self.sent_message_ids_lock:
                                        self.sent_message_ids.add(progress_message_id)
                    
                    response = self.claude_service.process_email_request_streaming(
                        message_content, sender_email, progress_callback
                    )
                    
                    print(f"🤖 Claude processing completed ({len(response)} chars)")
                    print(f"Response preview: {response[:200]}...")
                    
                    # Send final result email with Claude's complete response
                    if thread_id and response:
                        final_email = f"Task completed!\n\n{response}"
                        final_message_id = self.retry_gmail_operation(
                            lambda: self.gmail_service.send_reply_email(
                                thread_id, sender_email, subject, final_email
                            )
                        )
                        if final_message_id:
                            print("📧 Sent final result email")
                            # Track this as a sent message
                            with self.sent_message_ids_lock:
                                self.sent_message_ids.add(final_message_id)
                        else:
                            print("⚠️ Failed to send final result email")
                            
                except Exception as claude_error:
                    print(f"❌ Claude processing failed: {claude_error}")
                    
                    # Send error email if Claude processing failed
                    if thread_id:
                        error_message = f"Claude processing failed with error: {str(claude_error)}"
                        error_message_id = self.retry_gmail_operation(
                            lambda: self.gmail_service.send_reply_email(
                                thread_id, sender_email, subject, error_message
                            )
                        )
                        if error_message_id:
                            print("📧 Sent error notification email")
                            # Track this as a sent message
                            with self.sent_message_ids_lock:
                                self.sent_message_ids.add(error_message_id)
                        else:
                            print("⚠️ Failed to send error notification email")
                
        except Exception as error:
            print(f"Error processing notification: {error}")
    
    def callback(self, message):
        """Pub/Sub message callback."""
        try:
            notification_data = self.decode_notification_data(message.data)
            
            # Run processing in thread pool and wait for completion
            future = self.executor.submit(
                self.process_notification, 
                notification_data
            )
            
            # Wait for processing to complete before acknowledging
            try:
                future.result(timeout=600)  # 10 minute timeout for processing
                message.ack()  # Only ack after successful processing
                print(f"Successfully processed and acknowledged notification")
            except Exception as processing_error:
                print(f"Processing failed: {processing_error}")
                message.nack()  # Negative ack so message can be retried
            
        except Exception as error:
            print(f"Error in callback: {error}")
            message.nack()
    
    def start_listening(self):
        """Start listening for Pub/Sub notifications."""
        import datetime
        start_time_str = datetime.datetime.fromtimestamp(self.server_start_time).strftime('%Y-%m-%d %H:%M:%S')
        print(f"Starting to listen on subscription: {self.subscription_path}")
        print(f"📅 Server started at: {start_time_str} (will skip emails older than this)")
        
        flow_control = pubsub_v1.types.FlowControl(max_messages=10)
        
        # Configure the subscriber
        streaming_pull_future = self.subscriber.subscribe(
            subscription=self.subscription_path,
            callback=self.callback,
            flow_control=flow_control,
        )
        
        print("Listening for messages...")
        print("Send yourself an email with subject 'CLAUDE' to test!")
        
        try:
            streaming_pull_future.result()
        except KeyboardInterrupt:
            streaming_pull_future.cancel()
            print("\nShutting down...")
    
    def create_webhook_app(self) -> Flask:
        """Create Flask app for webhook notifications (alternative to Pub/Sub)."""
        app = Flask(__name__)
        
        @app.route('/webhook', methods=['POST'])
        def webhook():
            try:
                # Verify the request
                data = request.get_json()
                
                if not data:
                    return jsonify({'error': 'No data provided'}), 400
                
                # Decode notification
                message_data = data.get('message', {})
                if 'data' in message_data:
                    notification_data = self.decode_notification_data(
                        message_data['data']
                    )
                    
                    # Process notification asynchronously
                    self.executor.submit(
                        self.process_notification,
                        notification_data
                    )
                
                return jsonify({'status': 'success'}), 200
                
            except Exception as error:
                print(f"Webhook error: {error}")
                return jsonify({'error': str(error)}), 500
        
        @app.route('/health', methods=['GET'])
        def health():
            return jsonify({'status': 'healthy'}), 200
        
        return app