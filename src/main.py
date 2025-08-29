#!/usr/bin/env python3
"""
Text-Claude: Gmail to Claude Code integration app

This application listens for Gmail messages and launches Claude Code sessions
to process requests sent via email.
"""

import sys
import argparse
import asyncio
import os
from typing import Optional

from .config import Config
from .gmail_service import GmailService
from .claude_service import ClaudeService
from .notification_handler import NotificationHandler


def setup_environment():
    """Set up environment variables if not already set."""
    # Ensure Claude Code CLI is available
    if not os.system("which claude >/dev/null 2>&1") == 0:
        print("Warning: Claude Code CLI not found. Please install it with: npm install -g @anthropic-ai/claude-code")
    
    # Check if Node.js is available (required for Claude Code)
    if not os.system("which node >/dev/null 2>&1") == 0:
        print("Warning: Node.js not found. Claude Code SDK requires Node.js to be installed.")
    
    # Set headless mode for Claude Code
    os.environ['CLAUDE_HEADLESS'] = '1'


def setup_pubsub_topic_and_subscription(config: Config):
    """Set up Google Cloud Pub/Sub topic and subscription."""
    from google.cloud import pubsub_v1
    
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    
    topic_path = publisher.topic_path(config.project_id, 'gmail-notifications')
    subscription_path = subscriber.subscription_path(config.project_id, config.pubsub_subscription_name)
    
    try:
        # Create topic if it doesn't exist
        try:
            publisher.create_topic(request={"name": topic_path})
            print(f"Created topic: {topic_path}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"Topic already exists: {topic_path}")
            else:
                raise
        
        # Create subscription if it doesn't exist
        try:
            subscriber.create_subscription(
                request={"name": subscription_path, "topic": topic_path}
            )
            print(f"Created subscription: {subscription_path}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"Subscription already exists: {subscription_path}")
            else:
                raise
        
        return topic_path, subscription_path
        
    except Exception as error:
        print(f"Error setting up Pub/Sub: {error}")
        raise


def setup_gmail_notifications(gmail_service: GmailService, topic_name: str):
    """Set up Gmail push notifications."""
    try:
        result = gmail_service.setup_push_notifications(topic_name)
        print(f"Gmail notifications set up successfully")
        print(f"Watch expiration: {result.get('expiration')}")
        return result
    except Exception as error:
        print(f"Error setting up Gmail notifications: {error}")
        raise


def run_pubsub_mode(config: Config):
    """Run the app in Pub/Sub mode."""
    print("Running in Pub/Sub mode...")
    
    # Set up services
    gmail_service = GmailService(
        credentials_file=config.gmail_credentials_file,
        token_file=config.gmail_token_file
    )
    
    claude_service = ClaudeService(
        working_directory=config.claude_working_directory
    )
    
    # Set up Pub/Sub
    topic_path, subscription_path = setup_pubsub_topic_and_subscription(config)
    
    # Set up Gmail notifications
    setup_gmail_notifications(gmail_service, topic_path)
    
    # Create notification handler
    handler = NotificationHandler(
        gmail_service=gmail_service,
        claude_service=claude_service,
        project_id=config.project_id,
        subscription_name=config.pubsub_subscription_name
    )
    
    # Start listening
    handler.start_listening()


def run_webhook_mode(config: Config):
    """Run the app in webhook mode."""
    print("Running in webhook mode...")
    
    # Set up services
    gmail_service = GmailService(
        credentials_file=config.gmail_credentials_file,
        token_file=config.gmail_token_file
    )
    
    claude_service = ClaudeService(
        working_directory=config.claude_working_directory
    )
    
    # Create notification handler
    handler = NotificationHandler(
        gmail_service=gmail_service,
        claude_service=claude_service,
        project_id=config.project_id,
        subscription_name=config.pubsub_subscription_name
    )
    
    # Create and run Flask app
    app = handler.create_webhook_app()
    print(f"Starting webhook server on {config.webhook_host}:{config.webhook_port}")
    app.run(host=config.webhook_host, port=config.webhook_port, debug=False)


def test_gmail_connection(config: Config):
    """Test Gmail API connection."""
    print("Testing Gmail connection...")
    
    try:
        gmail_service = GmailService(
            credentials_file=config.gmail_credentials_file,
            token_file=config.gmail_token_file
        )
        
        # Test by getting recent messages
        messages = gmail_service.get_recent_messages(max_results=5)
        print(f"Successfully connected to Gmail. Found {len(messages)} recent messages. {messages}")
        
        return True
    except Exception as error:
        print(f"Gmail connection test failed: {error}")
        return False


def test_claude_connection(config: Config):
    """Test Claude Code connection via subprocess."""
    print("Testing Claude Code connection...")
    
    try:
        claude_service = ClaudeService(
            working_directory=config.claude_working_directory
        )
        
        response = claude_service.launch_claude_session("What is 2+2?")
        print(f"Claude Code test successful. Response: {response[:100]}...")
        return True
    except Exception as error:
        error_str = str(error)
        print(f"Claude Code test failed: {error}")
        if "credit" in error_str.lower() or "balance" in error_str.lower():
            print("Note: Account has insufficient credits.")
            print("Please add credits to your Claude Pro account.")
        elif "command not found" in error_str.lower():
            print("Note: Claude CLI not found. Please install: npm install -g @anthropic-ai/claude-code")
        return False


def main():
    """Main entry point for the text-claude CLI."""
    parser = argparse.ArgumentParser(
        description="Gmail to Claude Code integration app",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  text-claude start                 # Start the service
  text-claude start --mode webhook # Start in webhook mode
  text-claude test                  # Test connections
  text-claude setup                 # Set up Pub/Sub resources
  text-claude messages              # Show recent Gmail messages
  text-claude process --message-id MESSAGE_ID  # Process a specific email
        """
    )
    
    parser.add_argument(
        'command',
        choices=['start', 'test', 'setup', 'config', 'messages', 'process'],
        help='Command to run'
    )
    
    parser.add_argument(
        '--mode',
        choices=['pubsub', 'webhook'],
        help='Notification mode (default: pubsub)'
    )
    
    parser.add_argument(
        '--config-file',
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--message-id',
        help='Gmail message ID to process (use with process command)'
    )
    
    args = parser.parse_args()
    
    # Set up environment
    setup_environment()
    
    # Load configuration
    config = Config()
    
    if args.mode:
        config.notification_mode = args.mode
    
    # Validate configuration
    if args.command not in ['config', 'messages', 'process']:
        errors = config.validate()
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
    
    # Handle commands
    if args.command == 'config':
        config.print_config()
        
    elif args.command == 'messages':
        print("=== Recent Gmail Messages ===\n")
        try:
            gmail_service = GmailService(
                credentials_file=config.gmail_credentials_file,
                token_file=config.gmail_token_file
            )
            
            messages = gmail_service.get_recent_messages(max_results=5)
            
            for i, msg in enumerate(messages, 1):
                message_id = msg['id']
                sender = gmail_service.get_sender_email(message_id)
                content = gmail_service.get_message_content(message_id)
                
                print(f"Message {i}:")
                print(f"From: {sender}")
                print(f"Content: {content[:200]}...")
                print("-" * 50)
                
        except Exception as error:
            print(f"Error getting messages: {error}")
            sys.exit(1)
    
    elif args.command == 'process':
        if not args.message_id:
            print("Error: --message-id is required for process command")
            print("Use 'text-claude messages' to see available message IDs")
            sys.exit(1)
        
        print(f"=== Processing Email Message {args.message_id} ===\n")
        try:
            gmail_service = GmailService(
                credentials_file=config.gmail_credentials_file,
                token_file=config.gmail_token_file
            )
            
            claude_service = ClaudeService(
                working_directory=config.claude_working_directory
            )
            
            # Get message details
            sender = gmail_service.get_sender_email(args.message_id)
            recipient = gmail_service.get_recipient_email(args.message_id)
            subject = gmail_service.get_subject(args.message_id)
            content = gmail_service.get_message_content(args.message_id)
            
            print(f"From: {sender}")
            print(f"To: {recipient}")
            print(f"Subject: {subject}")
            print("-" * 50)
            print("Message Content:")
            print(content)
            print("-" * 50)
            
            # Check if email meets Claude criteria
            valid_sender = sender.lower() == 'jonathanmingli@gmail.com'
            valid_recipient = recipient.lower() == 'jonathanmingli@gmail.com'
            valid_subject = subject.upper() == 'CLAUDE'
            
            print(f"✅ Valid sender (jonathanmingli@gmail.com): {valid_sender}")
            print(f"✅ Valid recipient (jonathanmingli@gmail.com): {valid_recipient}")
            print(f"✅ Valid subject (CLAUDE): {valid_subject}")
            
            if not (valid_sender and valid_recipient and valid_subject):
                print("\n❌ Email does not meet criteria for Claude processing:")
                if not valid_sender:
                    print(f"   - Wrong sender: {sender} (must be jonathanmingli@gmail.com)")
                if not valid_recipient:
                    print(f"   - Wrong recipient: {recipient} (must be jonathanmingli@gmail.com)")
                if not valid_subject:
                    print(f"   - Wrong subject: '{subject}' (must be 'CLAUDE')")
                sys.exit(1)
            
            print("\n✅ Email meets all criteria for Claude processing!")
            
            # Process with Claude (skip if Claude test fails)
            try:
                print("Processing with Claude Code...")
                response = claude_service.process_email_request(content, sender)
                print("✅ Claude Response:")
                print(response)
            except Exception as claude_error:
                print(f"⚠️ Claude processing failed: {claude_error}")
                print("The email functionality works, but Claude Code has an issue.")
                
        except Exception as error:
            print(f"Error processing message: {error}")
            sys.exit(1)
        
    elif args.command == 'test':
        print("Running connection tests...")
        
        gmail_ok = test_gmail_connection(config)
        claude_ok = test_claude_connection(config)
        
        if gmail_ok and claude_ok:
            print("✅ All tests passed!")
            sys.exit(0)
        else:
            print("❌ Some tests failed!")
            sys.exit(1)
            
    elif args.command == 'setup':
        print("Setting up Pub/Sub resources...")
        try:
            setup_pubsub_topic_and_subscription(config)
            print("✅ Setup completed successfully!")
        except Exception as error:
            print(f"❌ Setup failed: {error}")
            sys.exit(1)
            
    elif args.command == 'start':
        config.print_config()
        
        try:
            if config.notification_mode == 'webhook':
                run_webhook_mode(config)
            else:
                run_pubsub_mode(config)
        except KeyboardInterrupt:
            print("\nShutting down gracefully...")
        except Exception as error:
            print(f"Error: {error}")
            sys.exit(1)


if __name__ == '__main__':
    main()