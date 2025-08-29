# Text-Claude

Gmail to Claude Code integration app that listens for text messages and launches Claude Code sessions.

## Overview

This application monitors your Gmail inbox for new messages and automatically processes them using Claude Code. When a new email arrives from an authorized sender, the app extracts the message content and launches a Claude Code session to handle the request.

## Features

- 🔄 Real-time Gmail monitoring via Google Cloud Pub/Sub
- 🤖 Claude Code SDK integration for automated code assistance
- 🔐 Configurable allowed sender whitelist for security
- 🌐 Support for both Pub/Sub and webhook notification modes
- 📧 Intelligent email content extraction and processing
- 🛠️ Full access to your codebase at `/Users/jonathanli/code`

## Prerequisites

- Python 3.10+
- Node.js (required for Claude Code SDK)
- Google Cloud Project with Gmail API and Pub/Sub enabled
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- Gmail API credentials (`credentials.json`)
- Anthropic API key

## Installation

1. Install the package:
```bash
pip install -e .
```

2. Install Claude Code CLI:
```bash
npm install -g @anthropic-ai/claude-code
```

3. Set up environment variables:
```bash
export GOOGLE_CLOUD_PROJECT_ID="emailmyself-470502"
```

## Configuration

The app uses the following configuration:

### Environment Variables

- `GOOGLE_CLOUD_PROJECT_ID` - Google Cloud project ID (default: emailmyself-470502)
- `GMAIL_CREDENTIALS_FILE` - Path to Gmail credentials (default: credentials.json)
- `GMAIL_TOKEN_FILE` - Path to Gmail token (default: token.json)
- `CLAUDE_WORKING_DIRECTORY` - Claude Code working directory (default: /Users/jonathanli/code)
- `ALLOWED_SENDERS` - Comma-separated list of allowed email addresses (default: jonathanmingli@gmail.com)
- `NOTIFICATION_MODE` - Either 'pubsub' or 'webhook' (default: pubsub)
- `WEBHOOK_HOST` - Webhook server host (default: 0.0.0.0)
- `WEBHOOK_PORT` - Webhook server port (default: 5000)

## Usage

### Available Commands

#### Check Configuration
```bash
text-claude config
```
Shows current configuration settings and environment variables.

#### View Recent Gmail Messages
```bash
text-claude messages
```
Displays your 5 most recent Gmail messages with sender and content preview.

#### Process a Specific Email
```bash
text-claude process --message-id MESSAGE_ID
```
Processes a specific email message (get MESSAGE_ID from `messages` command):
- Shows sender and content
- Checks if sender is authorized  
- Processes with Claude Code (if working)
- Great for testing email functionality

#### Test Connections
```bash
text-claude test
```
Tests both Gmail API and Claude Code connections.

#### Set Up Google Cloud Resources
```bash
text-claude setup
```
Creates necessary Pub/Sub topics and subscriptions for push notifications.

#### Start the Service
```bash
# Start in Pub/Sub mode (recommended)
text-claude start

# Start in webhook mode
text-claude start --mode webhook
```
Begins monitoring Gmail for new messages and processing them with Claude Code.

### Command Examples

```bash
# Basic workflow
text-claude config                           # Check settings
text-claude messages                         # See recent emails
text-claude process --message-id 198f3cf...  # Test with specific email
text-claude test                             # Test connections
text-claude setup                            # Set up infrastructure  
text-claude start                            # Start monitoring

# Different modes
text-claude start --mode pubsub              # Use Google Pub/Sub (default)
text-claude start --mode webhook             # Use webhook endpoint
```

## How It Works

1. **Gmail Monitoring**: The app sets up push notifications via Google Cloud Pub/Sub to monitor your Gmail inbox in real-time.

2. **Message Processing**: When a new email arrives:
   - Verifies sender is in allowed list
   - Extracts email content
   - Creates a formatted prompt for Claude

3. **Claude Integration**: 
   - Launches a Claude Code session with full access to your codebase
   - Processes the email request using Claude's coding capabilities
   - Returns structured responses

4. **Security**: Only processes emails from pre-configured allowed senders.

## Project Structure

```
src/
├── __init__.py
├── main.py                 # Main CLI application
├── config.py              # Configuration management
├── gmail_service.py       # Gmail API integration
├── claude_service.py      # Claude Code SDK integration
└── notification_handler.py # Pub/Sub and webhook handling
```

## Google Cloud Setup

1. Create a Google Cloud project
2. Enable Gmail API and Cloud Pub/Sub APIs
3. Create service account credentials
4. Download `credentials.json` to project root
5. Grant `gmail-api-push@system.gserviceaccount.com` publish rights to your Pub/Sub topic

## Security Considerations

- Only authorized email addresses can trigger Claude sessions
- All Claude sessions run in your specified working directory with full permissions
- Credentials are stored securely using Google's OAuth2 flow
- API keys should be kept secret and not committed to version control

## Troubleshooting

### Common Issues

1. **Gmail API Quota Exceeded**: Check your Google Cloud Console for API usage limits
2. **Claude Code CLI Not Found**: Install with `npm install -g @anthropic-ai/claude-code`
3. **Authentication Errors**: Regenerate `token.json` by deleting it and running the app again
4. **Pub/Sub Permission Errors**: Ensure your service account has proper permissions

### Debug Mode

Run with Python's debug flag to see detailed logs:
```bash
python -u -m src.main start
```

## Contributing

This is a personal automation tool. Modifications should be made carefully and tested thoroughly before deployment.

## License

Private use only.