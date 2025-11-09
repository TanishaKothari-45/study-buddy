"""
PDF generation from OCR extracted text
Preserves line breaks and page structure
"""
import logging
from typing import List, Dict, Any
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

logger = logging.getLogger(__name__)

def generate_pdf_from_ocr_results(
    ocr_results: List[Dict[str, Any]],
    output_path: str,
    title: str = "OCR Extracted Text",
    page_size: str = "A4"
) -> str:
    """
    Generate PDF from OCR results with preserved line breaks
    
    Args:
        ocr_results: List of OCR result dictionaries, each with:
            - page_number: Page number
            - text: Extracted text
            - confidence: Confidence score
            - ocr_method: OCR method used
        output_path: Path to save the generated PDF
        title: Title for the PDF document
        page_size: Page size ('A4' or 'letter')
    
    Returns:
        Path to generated PDF file
    """
    logger.info(f"📄 Generating PDF from {len(ocr_results)} pages...")
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    
    # Select page size
    if page_size.lower() == "letter":
        pagesize = letter
    else:
        pagesize = A4
    
    # Create PDF document
    doc = SimpleDocTemplate(output_path, pagesize=pagesize)
    
    # Container for PDF elements
    story = []
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor='#000000',
        spaceAfter=30,
        alignment=TA_LEFT
    )
    
    # Page header style
    page_header_style = ParagraphStyle(
        'PageHeader',
        parent=styles['Heading2'],
        fontSize=12,
        textColor='#666666',
        spaceAfter=12,
        alignment=TA_LEFT
    )
    
    # Body text style (preserves line breaks)
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        textColor='#000000',
        alignment=TA_LEFT,
        spaceAfter=12
    )
    
    # Metadata style
    metadata_style = ParagraphStyle(
        'Metadata',
        parent=styles['Normal'],
        fontSize=9,
        textColor='#888888',
        alignment=TA_LEFT,
        spaceAfter=6
    )
    
    # Add title
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Process each page
    for i, result in enumerate(ocr_results):
        page_number = result.get("page_number", i + 1)
        text = result.get("text", "")
        confidence = result.get("confidence", 0.0)
        ocr_method = result.get("ocr_method", "unknown")
        
        # Add page header
        page_header = f"Page {page_number}"
        story.append(Paragraph(page_header, page_header_style))
        
        # Add metadata
        metadata_text = f"OCR Method: {ocr_method.upper()} | Confidence: {confidence:.1%}"
        story.append(Paragraph(metadata_text, metadata_style))
        story.append(Spacer(1, 0.1*inch))
        
        # Process text: preserve line breaks
        # Replace newlines with <br/> tags for ReportLab
        if text:
            # Log what we're putting in PDF
            logger.debug(f"   Page {page_number}: Adding text to PDF ({len(text)} chars)")
            logger.debug(f"      Preview: {text[:100]}...")
            
            # Escape HTML special characters
            text_escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # Replace newlines with <br/> tags to preserve line breaks
            text_formatted = text_escaped.replace("\n", "<br/>")
            
            # Also replace double newlines with paragraph breaks
            text_formatted = text_formatted.replace("<br/><br/>", "<br/><br/>")
            
            # Add text paragraph
            story.append(Paragraph(text_formatted, body_style))
        else:
            # Empty page
            logger.warning(f"   Page {page_number}: No text to add to PDF!")
            story.append(Paragraph("<i>No text extracted from this page</i>", body_style))
        
        # Add page break (except for last page)
        if i < len(ocr_results) - 1:
            story.append(PageBreak())
    
    # Build PDF
    try:
        doc.build(story)
        logger.info(f"✅ PDF generated successfully: {output_path}")
        logger.info(f"   • Pages: {len(ocr_results)}")
        logger.info(f"   • File size: {os.path.getsize(output_path) / 1024:.2f} KB")
        return output_path
    except Exception as e:
        logger.error(f"❌ Failed to generate PDF: {e}")
        raise


