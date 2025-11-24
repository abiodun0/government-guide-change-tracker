"""
Parser classes for extracting document information from HTML pages.
Uses strategy pattern with source-specific parsers.
"""
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class ParsedDocumentRow:
    """Data class for a parsed document row."""
    def __init__(
        self,
        title: str,
        pdf_link: str,
        description: Optional[str] = None,
        published_date: Optional[datetime.date] = None
    ):
        self.title = title
        self.pdf_link = pdf_link
        self.description = description
        self.published_date = published_date

    def __repr__(self):
        return f"ParsedDocumentRow(title='{self.title[:30]}...', pdf_link='{self.pdf_link}')"


class BaseParser(ABC):
    """Base parser class implementing common functionality."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.soup: Optional[BeautifulSoup] = None

    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML string into BeautifulSoup object."""
        self.soup = BeautifulSoup(html, 'lxml')
        return self.soup

    @abstractmethod
    def extract_rows(self, html: str) -> List[ParsedDocumentRow]:
        """
        Extract document rows from HTML.
        Must be implemented by subclasses.
        """
        pass

    def normalize_title(self, title: str) -> str:
        """Normalize title by trimming whitespace."""
        return title.strip() if title else ""

    def normalize_description(self, description: Optional[str]) -> Optional[str]:
        """Normalize description by trimming whitespace."""
        if not description:
            return None
        normalized = description.strip()
        return normalized if normalized else None

    def normalize_pdf_link(self, link: str) -> Optional[str]:
        """Normalize PDF link - convert relative to absolute and validate."""
        if not link:
            return None
        
        # Trim whitespace
        link = link.strip()
        
        # Convert relative URLs to absolute
        if link.startswith('/'):
            link = urljoin(self.base_url, link)
        elif not link.startswith('http'):
            link = urljoin(self.base_url, link)
        
        # Validate it's a PDF link
        if not link.lower().endswith('.pdf'):
            return None
        
        return link

    def parse_date(self, date_str: Optional[str]) -> Optional[datetime.date]:
        """Parse date string to datetime.date object."""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        if not date_str:
            return None

        # Common date formats
        date_formats = [
            '%m/%d/%Y',      # 6/17/2022
            '%m-%d-%Y',      # 6-17-2022
            '%Y-%m-%d',      # 2022-06-17
            '%B %d, %Y',     # June 17, 2022
            '%b %d, %Y',     # Jun 17, 2022
            '%d/%m/%Y',      # 17/6/2022
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    def build_slug(self, title: str, description: Optional[str] = None) -> str:
        """
        Build a deterministic slug using BOTH title and description.
        No priority — they are combined into a single text block.
        Sanitatise combined text.
        """

        # Combine both fields (even if one is None or empty)
        combined = f"{title or ''} {description or ''}".strip()

        if not combined:
            return ""

        slug = combined.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '_', slug)
        slug = slug.strip('_')

        return slug[:100]

    def is_valid_row(self, row: ParsedDocumentRow) -> bool:
        """Check if a row has required fields and is not a category header."""
        # Must have title and valid PDF link
        if not row.title or not row.pdf_link:
            return False
        
        return True


class GinnieMaeParser(BaseParser):
    """Parser for Ginnie Mae MBS Guide Library page."""
    
    def extract_rows(self, html: str) -> List[ParsedDocumentRow]:
        """Extract rows from Ginnie Mae MBS Guide Library HTML."""
        soup = self.parse_html(html)
        rows = []
        
        # Strategy 1: Try to find table with PDF links
        table = self._find_table_with_pdfs(soup)
        
        if table:
            rows.extend(self._extract_from_table(table))

        # Strategy 2: Fallback - find all PDF links directly (heuristic approach)
        if not rows:
            rows.extend(self._extract_from_pdf_links(soup))
        
        return rows
    
    def _find_table_with_pdfs(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """Find table containing PDF links using multiple strategies."""
        # Strategy 1: CSS selector with class/id containing keywords
        selectors = [
            'table[class*="mbs"]',
            'table[class*="guide"]',
            'table[class*="chapter"]',
            'table[id*="mbs"]',
            'table[id*="guide"]',
            'table[id*="chapter"]',
        ]
        
        for selector in selectors:
            try:
                table = soup.select_one(selector)
                if table and table.find('a', href=re.compile(r'\.pdf', re.I)):
                    return table
            except Exception:
                continue
        
        # Strategy 2: Find any table with PDF links
        tables = soup.find_all('table')
        for table in tables:
            if table.find('a', href=re.compile(r'\.pdf', re.I)):
                return table
        
        return None
    
    def _extract_from_table(self, table: BeautifulSoup) -> List[ParsedDocumentRow]:
        """Extract rows from a table structure."""
        rows = []
        
        for tr in table.find_all('tr'):
            # Skip header rows (all cells are th)
            cells = tr.find_all(['td', 'th'])
            if not cells:
                continue
            
            # Check if this is a header row (all th) - skip it
            all_th = all(cell.name == 'th' for cell in cells)
            if all_th:
                continue
            
            # Extract PDF link (heuristic: first <a> tag with .pdf)
            link_tag = tr.find('a', href=re.compile(r'\.pdf', re.I))
            if not link_tag:
                continue
            
            pdf_link = link_tag.get('href', '')
            pdf_link = self.normalize_pdf_link(pdf_link)
            if not pdf_link:
                continue
            
            # Extract title - multiple strategies (doesn't depend on th)
            title = self._extract_title(link_tag, cells, tr)
            if not title:
                continue
            
            title = self.normalize_title(title)
            
            # Extract description - look in adjacent cells or parent elements
            description = self._extract_description(link_tag, cells, tr, title)
            
            # Extract published date - look in last cell or nearby text (optional)
            published_date = self._extract_published_date(cells, tr)
            
            # Create row
            row = ParsedDocumentRow(
                title=title,
                pdf_link=pdf_link,
                description=description,
                published_date=published_date
            )
            
            # Validate row has required fields (title + valid PDF link)
            # Missing published date is allowed - versioning falls back to PDF hash
            if self.is_valid_row(row):
                rows.append(row)
        
        return rows
    
    def _extract_title(self, link_tag: BeautifulSoup, cells: List, tr: BeautifulSoup) -> Optional[str]:
        """Extract title using multiple strategies - doesn't depend on th tags."""
        # Strategy 1: Link text (most reliable)
        title = link_tag.get_text(strip=True)

        if title:
            return title
        
        # Strategy 2: First non-empty cell text (excluding th header cells)
        for cell in cells:
            if cell.name == 'th':
                continue
            cell_text = cell.get_text(strip=True)
            if cell_text and not re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', cell_text):  # Not a date
                return cell_text
        
        # Strategy 3: Parent element text (removing link text)
        parent = link_tag.find_parent(['td', 'th', 'div', 'li'])
        if parent:
            # Get all text, remove the link text
            full_text = parent.get_text(separator=' ', strip=True)
            link_text = link_tag.get_text(strip=True)
            if full_text and full_text != link_text:
                # Remove link text from full text
                title = full_text.replace(link_text, '').strip()
                if title:
                    return title
        
        # Strategy 4: Row text (first meaningful text)
        row_text = tr.get_text(separator=' ', strip=True)
        if row_text:
            # Split by common separators and take first meaningful part
            parts = re.split(r'\s{2,}|\t|\n', row_text)
            for part in parts:
                part = part.strip()
                if part and len(part) > 3 and not re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', part):
                    return part
        
        return None
    
    def _extract_description(self, link_tag: BeautifulSoup, cells: List, tr: BeautifulSoup, title: str) -> Optional[str]:
        """Extract description using multiple strategies."""
        # Strategy 1: Second cell (if exists and different from title)
        if len(cells) > 1:
            for cell in cells[1:]:
                if cell.name == 'th':
                    continue
                desc_text = cell.get_text(strip=True)
                if desc_text and desc_text != title and not re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', desc_text):
                    return self.normalize_description(desc_text)
        
        # Strategy 2: Parent element text (excluding title and link)
        parent = link_tag.find_parent(['td', 'th', 'div', 'li'])
        if parent:
            full_text = parent.get_text(separator=' ', strip=True)
            # Remove title and link text
            cleaned = full_text.replace(title, '').replace(link_tag.get_text(strip=True), '').strip()
            if cleaned and len(cleaned) > len(title):
                return self.normalize_description(cleaned)
        
        return None
    
    def _extract_published_date(self, cells: List, tr: BeautifulSoup) -> Optional[datetime.date]:
        """Extract published date using multiple strategies. Missing date is allowed."""
        # Strategy 1: Last cell (common pattern: title, description, date)
        if cells:
            for cell in reversed(cells):
                if cell.name == 'th':
                    continue
                date_text = cell.get_text(strip=True)
                if date_text:
                    date = self.parse_date(date_text)
                    if date:
                        return date
        
        # Strategy 2: Look for date patterns in row text
        row_text = tr.get_text(strip=True)
        date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', row_text)
        if date_match:
            date = self.parse_date(date_match.group())
            if date:
                return date
        
        # Missing published date is allowed - will fall back to PDF hash comparison
        return None

    def _extract_from_pdf_links(self, soup: BeautifulSoup) -> List[ParsedDocumentRow]:
        """Fallback: Extract rows by finding all PDF links directly (heuristic approach)."""
        rows = []
        
        # Find all PDF links (heuristic: first <a> tag with .pdf)
        pdf_links = soup.find_all('a', href=re.compile(r'\.pdf', re.I))
        
        for link in pdf_links:
            pdf_link = link.get('href', '')
            pdf_link = self.normalize_pdf_link(pdf_link)
            if not pdf_link:
                continue
            
            # Extract title from link text
            title = link.get_text(strip=True)
            if not title:
                # Try parent element
                parent = link.find_parent(['td', 'th', 'div', 'li', 'p'])
                if parent:
                    title = parent.get_text(strip=True)
            
            title = self.normalize_title(title)
            if not title:
                continue
            
            # Extract description from nearby elements
            description = None
            parent = link.find_parent(['td', 'th', 'div', 'li', 'p'])
            if parent:
                full_text = parent.get_text(separator=' ', strip=True)
                if full_text and full_text != title:
                    description = self.normalize_description(full_text)
            
            # Extract date from nearby text (optional)
            published_date = None
            if parent:
                date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', parent.get_text())
                if date_match:
                    published_date = self.parse_date(date_match.group())
            
            row = ParsedDocumentRow(
                title=title,
                pdf_link=pdf_link,
                description=description,
                published_date=published_date
            )
            
            # Validate: must have title + valid PDF link
            if self.is_valid_row(row):
                rows.append(row)
        
        return rows


class USDAParser(BaseParser):
    """Parser for USDA Handbook pages."""
    
    def extract_rows(self, html: str) -> List[ParsedDocumentRow]:
        soup = self.parse_html(html)
        rows = []
        div = self._find_table_div_pdfs(soup)

        if div:
            rows.extend(self._extract_from_div(div))

        
        return rows

    def _find_table_div_pdfs(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """Find table containing PDF links using multiple strategies."""
        # Strategy 1: CSS selector with class/id containing keywords
        selectors = [
            'div[class*="view-content"]',
        ]
        
        for selector in selectors:
            try:
                div = soup.select_one(selector)
                if div and div.find('a', href=re.compile(r'\.pdf', re.I)):
                    return div
            except Exception:
                continue
        
        # Strategy 2: Find any table with PDF links
        divs = soup.find_all('div')
        for div in divs:
            if div.find('a', href=re.compile(r'\.pdf', re.I)):
                return div
        
        return None
    
    def _extract_from_div(self, soup: BeautifulSoup) -> List[ParsedDocumentRow]:
        """Fallback: Extract rows by finding all PDF links directly (heuristic approach)."""
        rows = []
        
        # Find all PDF links (heuristic: first <a> tag with .pdf)
        for row in soup.select('.views-row'):
            link_tag = row.select_one('.views-field-download-media a')
            if not link_tag:
                continue  # skip entries without PDF links

            pdf_link = link_tag['href'].strip()
            pdf_link = self.normalize_pdf_link(pdf_link)
            if not pdf_link:
                continue
            title = link_tag.get_text(strip=True)
            title = self.normalize_title(title)
            if not title:
                continue
            # description is inside: .views-field-body p
            desc_tag = row.select_one('.views-field-body p')
            description = desc_tag.get_text(strip=True) if desc_tag else None
            description = self.normalize_description(description)
            if not description:
                continue
            published_date = None
            parent = desc_tag.find_parent(['div', 'li', 'td', 'p'])
            if parent:
                date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', parent.get_text())
                if date_match:
                    published_date = self.parse_date(date_match.group())
            
            row = ParsedDocumentRow(
                title=title,
                pdf_link=pdf_link,
                description=description,
                published_date=published_date
            )
            
            # Validate: must have title + valid PDF link
            if self.is_valid_row(row):
                rows.append(row)
        
        return rows

class CustomParser(BaseParser):
    """Generic parser for unknown sources - uses heuristics."""
    
    def extract_rows(self, html: str) -> List[ParsedDocumentRow]:
        """Extract rows using generic heuristics."""
        soup = self.parse_html(html)
        rows = []
        
        # Find all PDF links
        links = soup.find_all('a', href=re.compile(r'\.pdf', re.I))
        
        for link in links:
            pdf_link = link.get('href', '')
            pdf_link = self.normalize_pdf_link(pdf_link)
            if not pdf_link:
                continue
            
            title = link.get_text(strip=True)
            title = self.normalize_title(title)
            
            # Try to find description nearby
            description = None
            parent = link.find_parent(['div', 'li', 'td', 'p'])
            if parent:
                # Get all text, remove the link text
                full_text = parent.get_text(separator=' ', strip=True)
                if full_text and full_text != title:
                    description = self.normalize_description(full_text)
            
            # Try to find date nearby
            published_date = None
            if parent:
                # Look for date patterns in parent or siblings
                date_text = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', parent.get_text())
                if date_text:
                    published_date = self.parse_date(date_text.group())
            
            row = ParsedDocumentRow(
                title=title,
                pdf_link=pdf_link,
                description=description,
                published_date=published_date
            )
            
            if self.is_valid_row(row):
                rows.append(row)
        
        return rows


def get_parser(parser_slug: str, base_url: str) -> BaseParser:
    """
    Factory function to get the appropriate parser based on slug.
    Uses strategy pattern.
    """
    parsers = {
        'ginnie-mae': GinnieMaeParser,
        'usda': USDAParser,
        'custom': CustomParser,
    }
    
    parser_class = parsers.get(parser_slug, CustomParser)
    return parser_class(base_url)

