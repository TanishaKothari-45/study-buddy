"""
HTML to PDF Converter for Data Acquisition Agent
Converts scraped HTML content to PDF format
"""

import os
import re
import tempfile
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class HTMLToPDFConverter:
    """Converts HTML content to PDF format"""

    def __init__(self):
        """Initialize PDF converter"""
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if required dependencies are available"""
        try:
            import pdfkit
            self.backend = 'pdfkit'
        except ImportError:
            try:
                # Fallback to weasyprint if pdfkit not available
                import weasyprint
                self.backend = 'weasyprint'
            except ImportError:
                logger.warning("Neither pdfkit nor weasyprint available. Install with: pip install pdfkit weasyprint")
                self.backend = None

    def convert_html_to_pdf(self, html_content: str, output_path: str, title: str = "Document") -> bool:
        """
        Convert HTML content to PDF

        Args:
            html_content: HTML content to convert
            output_path: Path where PDF should be saved
            title: Document title

        Returns:
            True if conversion successful
        """
        if not self.backend:
            logger.error("No PDF conversion backend available")
            return False

        try:
            # Wrap content in proper HTML structure
            full_html = self._prepare_html(html_content, title)

            if self.backend == 'pdfkit':
                return self._convert_with_pdfkit(full_html, output_path)
            elif self.backend == 'weasyprint':
                return self._convert_with_weasyprint(full_html, output_path)

        except Exception as e:
            logger.error(f"PDF conversion failed: {str(e)}")
            return False

    def _prepare_html(self, content: str, title: str) -> str:
        """Prepare HTML content with proper structure"""
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{title}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 40px;
                    max-width: 800px;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    color: #333;
                    margin-top: 30px;
                    margin-bottom: 15px;
                }}
                p {{
                    margin-bottom: 15px;
                    text-align: justify;
                }}
                ul, ol {{
                    margin-bottom: 15px;
                    padding-left: 30px;
                }}
                li {{
                    margin-bottom: 5px;
                }}
                .page-break {{
                    page-break-before: always;
                }}
                @media print {{
                    body {{ margin: 20px; }}
                }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """

        return html_template.format(title=title, content=content)

    def _convert_with_pdfkit(self, html_content: str, output_path: str) -> bool:
        """Convert using pdfkit (wkhtmltopdf)"""
        try:
            import pdfkit

            # pdfkit configuration
            options = {
                'page-size': 'A4',
                'margin-top': '1in',
                'margin-right': '1in',
                'margin-bottom': '1in',
                'margin-left': '1in',
                'encoding': 'UTF-8',
                'no-outline': None,
                'enable-local-file-access': None
            }

            # Convert HTML to PDF
            pdfkit.from_string(html_content, output_path, options=options)

            # Verify file was created and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"Successfully created PDF: {output_path}")
                return True
            else:
                logger.error(f"PDF file created but appears empty: {output_path}")
                return False

        except Exception as e:
            logger.error(f"pdfkit conversion failed: {str(e)}")
            return False

    def _convert_with_weasyprint(self, html_content: str, output_path: str) -> bool:
        """Convert using weasyprint"""
        try:
            from weasyprint import HTML, CSS
            from weasyprint.text.fonts import FontConfiguration

            font_config = FontConfiguration()

            # Create CSS for better formatting
            css = CSS(string='''
                @page {
                    size: A4;
                    margin: 1in;
                }
                body {
                    font-family: serif;
                    line-height: 1.4;
                }
            ''')

            # Convert HTML to PDF
            html_doc = HTML(string=html_content)
            html_doc.write_pdf(
                output_path,
                stylesheets=[css],
                font_config=font_config
            )

            # Verify file was created and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"Successfully created PDF: {output_path}")
                return True
            else:
                logger.error(f"PDF file created but appears empty: {output_path}")
                return False

        except Exception as e:
            logger.error(f"weasyprint conversion failed: {str(e)}")
            return False

    def create_study_material_pdf(self, scraped_content: Dict[str, Any], output_path: str) -> bool:
        """
        Create a well-formatted PDF from scraped study material

        Args:
            scraped_content: Content dictionary from scraper
            output_path: Path where PDF should be saved

        Returns:
            True if conversion successful
        """
        title = scraped_content.get('title', 'Study Material')
        content = scraped_content.get('content', '')

        if not content.strip():
            logger.error("No content to convert to PDF")
            return False

        # Enhance content for better PDF formatting
        enhanced_html = self._enhance_study_content(content, title)

        return self.convert_html_to_pdf(enhanced_html, output_path, title)

    def _enhance_study_content(self, content: str, title: str) -> str:
        """Enhance content with better formatting for study materials"""
        # Add section breaks for better readability
        enhanced_content = content

        # Add page breaks before major sections
        enhanced_content = re.sub(
            r'(?:^|\n)(Chapter|Section|Topic|Unit)\s+\d*[:.]?\s*(.+?)(?=\n(?:Chapter|Section|Topic|Unit|\Z))',
            r'\n<div class="page-break"></div>\n<h2>\1 \2</h2>\n',
            enhanced_content,
            flags=re.MULTILINE | re.IGNORECASE
        )

        # Convert bullet points to proper HTML lists
        enhanced_content = re.sub(
            r'^\s*[-*•]\s+(.+)$',
            r'<li>\1</li>',
            enhanced_content,
            flags=re.MULTILINE
        )

        # Wrap consecutive list items in ul tags
        enhanced_content = re.sub(
            r'(<li>.*?</li>)(\s*<li>.*?</li>)+',
            r'<ul>\g<0></ul>',
            enhanced_content,
            flags=re.DOTALL
        )

        # Add formatting for better structure
        enhanced_content = f"""
        <div style="text-align: center; margin-bottom: 30px;">
            <h1>{title}</h1>
        </div>
        {enhanced_content}
        """

        return enhanced_content
