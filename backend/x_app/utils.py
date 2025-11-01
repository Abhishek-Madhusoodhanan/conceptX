"""
All utility functions in ONE file
"""
import os
from pypdf import PdfReader
from docx import Document


def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from PDF, DOCX, or TXT files
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    
    try:
        if ext == '.pdf':
            return extract_from_pdf(file_path)
        elif ext == '.docx':
            return extract_from_docx(file_path)
        elif ext == '.txt':
            return extract_from_txt(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    except Exception as e:
        raise Exception(f"Error extracting text: {str(e)}")


def extract_from_pdf(file_path: str) -> str:
    """Extract text from PDF file"""
    try:
        reader = PdfReader(file_path)
        text = []
        
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
        
        return "\n\n".join(text)
    except Exception as e:
        raise Exception(f"PDF extraction error: {str(e)}")


def extract_from_docx(file_path: str) -> str:
    """Extract text from DOCX file"""
    try:
        doc = Document(file_path)
        text = []
        
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text.append(paragraph.text)
        
        return "\n\n".join(text)
    except Exception as e:
        raise Exception(f"DOCX extraction error: {str(e)}")


def extract_from_txt(file_path: str) -> str:
    """Extract text from TXT file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise Exception(f"TXT extraction error: {str(e)}")