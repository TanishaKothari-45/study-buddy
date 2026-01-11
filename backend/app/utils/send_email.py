"""
Email notification utility for sending cron job status alerts.
Supports Gmail SMTP for sending success/failure notifications.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Optional
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent.parent.parent / '.env'
load_dotenv(env_path)

logger = logging.getLogger(__name__)


def get_email_config() -> Dict[str, str]:
    """
    Read email configuration from environment variables.
    
    Returns:
        Dict containing email configuration
    """
    return {
        'enabled': os.getenv('EMAIL_ENABLED', 'false').lower() == 'true',
        'provider': os.getenv('EMAIL_PROVIDER', 'gmail'),
        'to': os.getenv('EMAIL_TO', ''),
        'from': os.getenv('EMAIL_FROM', ''),
        'gmail_password': os.getenv('GMAIL_APP_PASSWORD', ''),
    }


def format_email_body(status: str, details: Dict) -> str:
    """
    Format HTML email body with status and details.
    
    Args:
        status: 'success' or 'failure'
        details: Dictionary containing job details
        
    Returns:
        HTML formatted email body
    """
    is_success = status.lower() == 'success'
    
    # Status emoji and color
    status_emoji = "✅" if is_success else "❌"
    status_color = "#10b981" if is_success else "#ef4444"
    status_text = "SUCCESS" if is_success else "FAILED"
    
    # Build details section
    details_html = ""
    if is_success:
        details_html = f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>PDF Downloaded:</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{details.get('pdf_name', 'N/A')}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Chunks Created:</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{details.get('chunks_created', 'N/A')}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Stored in ChromaDB:</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">Yes ✓</td>
        </tr>
        """
    else:
        details_html = f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Error:</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; color: #ef4444;">{details.get('error', 'Unknown error')}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Exit Code:</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{details.get('exit_code', 'N/A')}</td>
        </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #374151; margin: 0; padding: 20px; background-color: #f9fafb;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden;">
            <!-- Header -->
            <div style="background-color: {status_color}; color: white; padding: 24px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 600;">
                    {status_emoji} Current Affairs Download {status_text}
                </h1>
            </div>
            
            <!-- Content -->
            <div style="padding: 24px;">
                <p style="margin-top: 0; font-size: 16px;">
                    The scheduled current affairs download job has completed.
                </p>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    {details_html}
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Timestamp:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{details.get('timestamp', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px;"><strong>Log File:</strong></td>
                        <td style="padding: 8px; font-family: monospace; font-size: 12px;">{details.get('log_file', 'N/A')}</td>
                    </tr>
                </table>
                
                {'<p style="color: #10b981; font-weight: 500;">📚 New content is now available in your study buddy system!</p>' if is_success else '<p style="color: #ef4444; font-weight: 500;">⚠️ Please check the log file for details.</p>'}
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f9fafb; padding: 16px; text-align: center; font-size: 12px; color: #6b7280; border-top: 1px solid #e5e7eb;">
                <p style="margin: 0;">
                    Automated notification from Study Buddy Cron Job<br>
                    Scheduled: 2nd of every month at 2:00 AM
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def send_notification_email(status: str, details: Dict) -> bool:
    """
    Send email notification about cron job status.
    
    Args:
        status: 'success' or 'failure'
        details: Dictionary containing job details like:
            - pdf_name: Name of downloaded PDF (for success)
            - chunks_created: Number of chunks created (for success)
            - error: Error message (for failure)
            - exit_code: Exit code (for failure)
            - log_file: Path to log file
            - timestamp: When the job ran
            
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        config = get_email_config()
        
        # Check if email is enabled
        if not config['enabled']:
            logger.info("Email notifications are disabled (EMAIL_ENABLED=false)")
            return False
        
        # Validate configuration
        if not config['to'] or not config['from']:
            logger.error("Email configuration incomplete: EMAIL_TO or EMAIL_FROM not set")
            return False
        
        if config['provider'] == 'gmail' and not config['gmail_password']:
            logger.error("Gmail app password not configured (GMAIL_APP_PASSWORD not set)")
            return False
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"{'✅ Success' if status.lower() == 'success' else '❌ Failed'}: Current Affairs Download"
        msg['From'] = config['from']
        msg['To'] = config['to']
        
        # Add HTML body
        html_body = format_email_body(status, details)
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email via Gmail SMTP
        if config['provider'] == 'gmail':
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(config['from'], config['gmail_password'])
                server.send_message(msg)
                logger.info(f"Email notification sent successfully to {config['to']}")
                return True
        else:
            logger.error(f"Unsupported email provider: {config['provider']}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")
        return False


def send_success_notification(pdf_name: str, chunks_created: int, log_file: str) -> bool:
    """
    Convenience function to send success notification.
    
    Args:
        pdf_name: Name of the downloaded PDF
        chunks_created: Number of chunks created
        log_file: Path to the log file
        
    Returns:
        True if email sent successfully, False otherwise
    """
    details = {
        'pdf_name': pdf_name,
        'chunks_created': chunks_created,
        'log_file': log_file,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    return send_notification_email('success', details)


def send_failure_notification(error: str, exit_code: int, log_file: str) -> bool:
    """
    Convenience function to send failure notification.
    
    Args:
        error: Error message
        exit_code: Exit code from the script
        log_file: Path to the log file
        
    Returns:
        True if email sent successfully, False otherwise
    """
    details = {
        'error': error,
        'exit_code': exit_code,
        'log_file': log_file,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    return send_notification_email('failure', details)


if __name__ == "__main__":
    # Test the email functionality
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    print("Testing email notification...")
    print("This will send a test email using your configured settings.\n")
    
    # Test success email
    success = send_success_notification(
        pdf_name="Test Workbook.pdf",
        chunks_created=52,
        log_file="/path/to/test.log"
    )
    
    if success:
        print("✅ Test email sent successfully!")
        print("Check your inbox at:", os.getenv('EMAIL_TO'))
    else:
        print("❌ Failed to send test email")
        print("Check your email configuration in .env file")
        sys.exit(1)
