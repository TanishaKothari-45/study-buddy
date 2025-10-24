"""
Acquisition Logger for Data Acquisition Agent
Tracks all download and scraping activities in CSV format
"""

import os
import csv
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class AcquisitionLogger:
    """Logs all data acquisition activities"""

    def __init__(self, log_dir: str = "../data/geography/logs"):
        """
        Initialize logger

        Args:
            log_dir: Directory for log files
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.log_file = self.log_dir / "geography_acquisition_log.csv"
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Create log file with headers if it doesn't exist"""
        if not self.log_file.exists():
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'subject',
                    'subtopic',
                    'source_name',
                    'url',
                    'status',
                    'file_path',
                    'file_size',
                    'error_message',
                    'content_hash',
                    'word_count',
                    'download_time_seconds'
                ])

    def log_acquisition_attempt(self,
                              subject: str,
                              subtopic: str,
                              source_name: str,
                              url: str,
                              status: str,
                              file_path: str = "",
                              file_size: int = 0,
                              error_message: str = "",
                              content_hash: str = "",
                              word_count: int = 0,
                              download_time: float = 0.0) -> None:
        """
        Log a single acquisition attempt

        Args:
            subject: Main subject (geography)
            subtopic: Specific subtopic
            source_name: Name of the source (vision_ias, ncert, etc.)
            url: Source URL
            status: Status (downloaded, scraped, failed)
            file_path: Path to downloaded file
            file_size: Size of downloaded file in bytes
            error_message: Error message if failed
            content_hash: Hash of content for duplicate detection
            word_count: Word count for HTML content
            download_time: Time taken for download/conversion
        """
        timestamp = datetime.now().isoformat()

        log_entry = [
            timestamp,
            subject,
            subtopic,
            source_name,
            url,
            status,
            file_path,
            file_size,
            error_message,
            content_hash,
            word_count,
            round(download_time, 2)
        ]

        # Append to log file
        try:
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(log_entry)

            logger.info(f"Logged acquisition: {status} - {source_name} - {subtopic}")

        except Exception as e:
            logger.error(f"Failed to write to log file: {str(e)}")

    def log_search_results(self, query: str, results_count: int, filtered_count: int = None) -> None:
        """Log search operation results"""
        self.log_acquisition_attempt(
            subject="geography",
            subtopic="search",
            source_name="google_search",
            url=query,
            status="search_completed",
            file_size=results_count,
            error_message=f"Found {results_count} results" + (f", filtered to {filtered_count}" if filtered_count else "")
        )

    def log_pdf_download(self,
                        url: str,
                        subtopic: str,
                        source_name: str,
                        file_path: str,
                        file_size: int,
                        download_time: float,
                        content_hash: str = "") -> None:
        """Log successful PDF download"""
        self.log_acquisition_attempt(
            subject="geography",
            subtopic=subtopic,
            source_name=source_name,
            url=url,
            status="downloaded",
            file_path=file_path,
            file_size=file_size,
            content_hash=content_hash,
            download_time=download_time
        )

    def log_html_scraping(self,
                         url: str,
                         subtopic: str,
                         source_name: str,
                         word_count: int,
                         download_time: float) -> None:
        """Log successful HTML scraping"""
        self.log_acquisition_attempt(
            subject="geography",
            subtopic=subtopic,
            source_name=source_name,
            url=url,
            status="scraped",
            word_count=word_count,
            download_time=download_time
        )

    def log_conversion_to_pdf(self,
                             url: str,
                             subtopic: str,
                             source_name: str,
                             file_path: str,
                             file_size: int,
                             conversion_time: float,
                             original_word_count: int = 0) -> None:
        """Log successful HTML to PDF conversion"""
        self.log_acquisition_attempt(
            subject="geography",
            subtopic=subtopic,
            source_name=source_name,
            url=url,
            status="converted_to_pdf",
            file_path=file_path,
            file_size=file_size,
            word_count=original_word_count,
            download_time=conversion_time
        )

    def log_failure(self,
                   url: str,
                   subtopic: str,
                   source_name: str,
                   error_message: str,
                   download_time: float = 0.0) -> None:
        """Log failed acquisition attempt"""
        self.log_acquisition_attempt(
            subject="geography",
            subtopic=subtopic,
            source_name=source_name,
            url=url,
            status="failed",
            error_message=error_message,
            download_time=download_time
        )

    def get_acquisition_stats(self) -> Dict[str, Any]:
        """Get statistics from the log file"""
        stats = {
            'total_attempts': 0,
            'successful_downloads': 0,
            'successful_scrapes': 0,
            'failed_attempts': 0,
            'by_subtopic': {},
            'by_source': {},
            'total_size_downloaded': 0,
            'average_download_time': 0.0
        }

        if not self.log_file.exists():
            return stats

        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                download_times = []
                for row in reader:
                    stats['total_attempts'] += 1

                    status = row['status']
                    subtopic = row['subtopic']
                    source = row['source_name']
                    file_size = int(row.get('file_size', 0))
                    download_time = float(row.get('download_time_seconds', 0))

                    # Count by status
                    if status == 'downloaded':
                        stats['successful_downloads'] += 1
                    elif status == 'scraped':
                        stats['successful_scrapes'] += 1
                    elif status == 'failed':
                        stats['failed_attempts'] += 1

                    # Count by subtopic
                    if subtopic not in stats['by_subtopic']:
                        stats['by_subtopic'][subtopic] = 0
                    stats['by_subtopic'][subtopic] += 1

                    # Count by source
                    if source not in stats['by_source']:
                        stats['by_source'][source] = 0
                    stats['by_source'][source] += 1

                    # Accumulate size and time
                    if file_size > 0:
                        stats['total_size_downloaded'] += file_size
                    if download_time > 0:
                        download_times.append(download_time)

                # Calculate averages
                if download_times:
                    stats['average_download_time'] = round(sum(download_times) / len(download_times), 2)

        except Exception as e:
            logger.error(f"Failed to read acquisition stats: {str(e)}")

        return stats

    def export_summary_report(self, output_path: str = None) -> str:
        """Export a summary report of acquisition activities"""
        stats = self.get_acquisition_stats()

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.log_dir / f"geography_acquisition_summary_{timestamp}.txt"

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("Geography Data Acquisition Summary Report\\n")
                f.write("=" * 50 + "\\n\\n")

                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n\\n")

                f.write("Overall Statistics:\\n")
                f.write(f"Total Attempts: {stats['total_attempts']}\\n")
                f.write(f"Successful Downloads: {stats['successful_downloads']}\\n")
                f.write(f"Successful Scrapes: {stats['successful_scrapes']}\\n")
                f.write(f"Failed Attempts: {stats['failed_attempts']}\\n")
                f.write(f"Total Size Downloaded: {stats['total_size_downloaded']:,} bytes\\n")
                f.write(f"Average Download Time: {stats['average_download_time']} seconds\\n\\n")

                f.write("By Subtopic:\\n")
                for subtopic, count in stats['by_subtopic'].items():
                    f.write(f"  {subtopic}: {count}\\n")

                f.write("\\nBy Source:\\n")
                for source, count in stats['by_source'].items():
                    f.write(f"  {source}: {count}\\n")

            logger.info(f"Summary report exported to: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to export summary report: {str(e)}")
            return ""
