import subprocess
import json
import os
import tempfile
from typing import Optional, Dict, Any


class ClaudeService:
    def __init__(self, working_directory: str = "/Users/jonathanli/code"):
        self.working_directory = working_directory
    
    def launch_claude_session(self, prompt: str) -> str:
        """Launch a Claude Code session with the given prompt using subprocess."""
        try:
            # Write prompt to a temporary file to avoid command line length issues
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
                temp_file.write(prompt)
                temp_file_path = temp_file.name
            
            try:
                # Build the Claude command using stdin redirect with all tools
                allowed_tools = [
                    'Bash', 'Edit', 'Glob', 'Grep', 'LS', 'MultiEdit', 
                    'NotebookEdit', 'Read', 'Task', 
                    'TodoWrite', 'WebFetch', 'WebSearch', 'Write'
                ]
                
                cmd = [
                    'claude',
                    '--dangerously-skip-permissions',
                    '--print',
                    '--output-format', 'stream-json',
                    '--verbose',
                    '--allowedTools', ','.join(allowed_tools)
                ]
                
                # Set working directory and run command with stdin from file
                with open(temp_file_path, 'r') as temp_file:
                    result = subprocess.run(
                        cmd,
                        cwd=self.working_directory,
                        stdin=temp_file,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout
                    )
            finally:
                # Clean up temp file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
            
            if result.returncode != 0:
                error_msg = f"Claude command failed with return code {result.returncode}"
                if result.stderr:
                    error_msg += f"\nstderr: {result.stderr}"
                if result.stdout:
                    error_msg += f"\nstdout: {result.stdout}"
                print(f"Claude command debug info: {error_msg}")
                raise subprocess.CalledProcessError(result.returncode, cmd, error_msg)
            
            # Parse JSON output from Claude
            if result.stdout.strip():
                try:
                    json_response = json.loads(result.stdout.strip())
                    print(f"DEBUG: Claude JSON response keys: {list(json_response.keys())}")
                    
                    # Extract the final response text from the JSON structure
                    if 'result' in json_response:
                        result_data = json_response['result']
                        if isinstance(result_data, dict) and 'content' in result_data:
                            # Handle content array format
                            content = result_data['content']
                            if isinstance(content, list):
                                text_parts = []
                                for item in content:
                                    if isinstance(item, dict) and item.get('type') == 'text':
                                        text_parts.append(item.get('text', ''))
                                return '\n'.join(text_parts) if text_parts else "Claude session completed successfully."
                            elif isinstance(content, str):
                                return content
                        elif isinstance(result_data, str):
                            return result_data
                    
                    # Fallback: look for any text content in the response
                    response_text = self.extract_text_from_json(json_response)
                    return response_text if response_text else "Claude session completed successfully."
                    
                except json.JSONDecodeError:
                    # If JSON parsing fails, return raw output
                    return result.stdout.strip()
            else:
                return "Claude session completed successfully."
            
        except subprocess.TimeoutExpired:
            raise Exception("Claude session timed out after 5 minutes")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Claude command failed: {e.stderr or str(e)}")
        except Exception as error:
            raise Exception(f"Error launching Claude session: {error}")
    
    def extract_text_from_json(self, json_obj) -> str:
        """Recursively extract text content from JSON response."""
        text_parts = []
        
        if isinstance(json_obj, dict):
            for key, value in json_obj.items():
                if key == 'text' and isinstance(value, str):
                    text_parts.append(value)
                elif isinstance(value, (dict, list)):
                    text_parts.append(self.extract_text_from_json(value))
        elif isinstance(json_obj, list):
            for item in json_obj:
                if isinstance(item, (dict, list)):
                    text_parts.append(self.extract_text_from_json(item))
                elif isinstance(item, str):
                    text_parts.append(item)
        elif isinstance(json_obj, str):
            text_parts.append(json_obj)
        
        return '\n'.join(filter(None, text_parts))
    
    def format_claude_prompt(self, message_content: str, sender_email: str) -> str:
        """Format a Claude prompt from email content."""
        prompt = f"""
You are Claude Code, processing a request sent via email from {sender_email} with subject "CLAUDE".

Email content:
{message_content}

Please execute this request. You have full access to the codebase at /Users/jonathanli/code and all tools needed to complete tasks including:
- File operations (Read, Write, Edit, MultiEdit)
- Shell commands (Bash)
- Search operations (Glob, Grep, LS) 
- Web operations (WebFetch, WebSearch)
- Notebook operations (NotebookEdit, NotebookRead)
- Task management (Task, TodoWrite)

Take action to complete the request as described in the email.
"""
        return prompt.strip()
    
    def process_email_request_streaming(self, message_content: str, sender_email: str, 
                                       progress_callback=None) -> str:
        """Process an email request with streaming updates and return final response."""
        prompt = self.format_claude_prompt(message_content, sender_email)
        
        print(f"Processing request from {sender_email}")
        print(f"Prompt: {prompt[:200]}...")
        
        try:
            # Write prompt to a temporary file to avoid command line length issues
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
                temp_file.write(prompt)
                temp_file_path = temp_file.name
            
            try:
                # Build the Claude command using stdin redirect with streaming JSON
                allowed_tools = [
                    'Bash', 'Edit', 'Glob', 'Grep', 'LS', 'MultiEdit', 
                    'NotebookEdit', 'Read', 'Task', 
                    'TodoWrite', 'WebFetch', 'WebSearch', 'Write'
                ]
                
                cmd = [
                    'claude',
                    '--dangerously-skip-permissions',
                    '--print',
                    '--output-format', 'stream-json',
                    '--verbose',
                    '--allowedTools', ','.join(allowed_tools)
                ]
                
                # Set working directory and run command with stdin from file
                with open(temp_file_path, 'r') as temp_file:
                    process = subprocess.Popen(
                        cmd,
                        cwd=self.working_directory,
                        stdin=temp_file,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    # Process streaming output line by line
                    assistant_responses = []
                    final_response = None
                    
                    for line in iter(process.stdout.readline, ''):
                        line = line.strip()
                        if not line:
                            continue
                            
                        try:
                            data = json.loads(line)
                            
                            # Handle different message types
                            if data.get('type') == 'assistant':
                                message = data.get('message', {})
                                content = message.get('content', [])
                                
                                for item in content:
                                    if item.get('type') == 'text':
                                        text = item.get('text', '')
                                        assistant_responses.append(text)
                                        
                                        # Call progress callback if provided
                                        if progress_callback:
                                            progress_callback(text)
                            
                            elif data.get('type') == 'result':
                                # Final result with metadata
                                final_response = data
                                
                        except json.JSONDecodeError:
                            # Skip lines that aren't valid JSON
                            continue
                    
                    # Wait for process to complete
                    process.wait()
                    
                    if process.returncode != 0:
                        stderr_output = process.stderr.read() if process.stderr else ""
                        error_msg = f"Claude command failed with return code {process.returncode}"
                        if stderr_output:
                            error_msg += f"\nstderr: {stderr_output}"
                        print(f"Claude command debug info: {error_msg}")
                        raise subprocess.CalledProcessError(process.returncode, cmd, error_msg)
                    
                    # Return the combined assistant responses
                    return '\n'.join(assistant_responses) if assistant_responses else "Claude session completed successfully."
                    
            finally:
                # Clean up temp file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except subprocess.TimeoutExpired:
            raise Exception("Claude session timed out")
        except Exception as error:
            raise Exception(f"Error launching Claude session: {error}")
    
    def process_email_request(self, message_content: str, sender_email: str) -> str:
        """Process an email request and return Claude's response (non-streaming version)."""
        return self.process_email_request_streaming(message_content, sender_email)